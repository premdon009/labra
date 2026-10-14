"""Letterhead layouts: the draft an admin edits, uploads to it, and publishing (design §7.2).

A branch has one draft per document kind at most. It starts as a copy of the latest
published version, so a change to the margins keeps the file and the other way round.
Publishing turns the draft into the next numbered version, which the database keeps
unchanged; a document is always reprinted on the version it was made with.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.core import audit
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.files import read_file, save_file
from labra.core.ids import utcnow
from labra.core.lab_settings import get_value
from labra.core.models import StoredFile
from labra.core.ports import FileStore
from labra.core.svg import SvgRefusedError, sanitise_svg
from labra.core.uploads import IMAGES, JPEG, PDF, PNG, SVG, WEBP, check_upload
from labra.org.models import Branch
from labra.org.service import stale
from labra.printing.images import optimise_raster
from labra.printing.letterhead import (
    BUILTIN,
    OUTPUTS,
    PageSpec,
    compose,
    prepare_pdf_letterhead,
)
from labra.printing.models import APPLY_ON, DOC_KINDS, LetterheadLayout
from labra.printing.pdf import FileReader, Rendered
from labra.printing.samples import FOR_KIND, SAMPLES
from labra.printing.templates import render_html

DOC_LABELS = {"report_a4": "Report (A4)", "bill_a4": "Bill of supply (A4)"}
FILE_LABELS = {"svg": "SVG drawing", "pdf": "PDF", "raster": "Picture"}
UPLOAD_TYPES = frozenset({PDF, SVG, PNG, JPEG, WEBP})
_SUFFIX = {SVG: "svg", PDF: "pdf", PNG: "png", JPEG: "jpg"}


def _check(principal: Principal, branch_id: uuid.UUID) -> None:
    if not principal.can("letterhead.edit", branch_id):
        raise PermissionDeniedError()


def _kind(doc_kind: str) -> str:
    if doc_kind not in DOC_KINDS:
        raise NotFoundError()
    return doc_kind


# Reading layouts


def published(
    db: Session, branch_id: uuid.UUID, doc_kind: str, at: datetime | None = None
) -> LetterheadLayout | None:
    """The latest published layout, or the one in force at `at` (a bill's issue time)."""
    stmt = select(LetterheadLayout).where(
        LetterheadLayout.branch_id == branch_id,
        LetterheadLayout.doc_kind == doc_kind,
        LetterheadLayout.status == "published",
    )
    if at is not None:
        stmt = stmt.where(LetterheadLayout.published_at <= at)
    return db.scalar(stmt.order_by(LetterheadLayout.version.desc()).limit(1))


def draft(db: Session, branch_id: uuid.UUID, doc_kind: str) -> LetterheadLayout | None:
    return db.scalar(
        select(LetterheadLayout).where(
            LetterheadLayout.branch_id == branch_id,
            LetterheadLayout.doc_kind == doc_kind,
            LetterheadLayout.status == "draft",
        )
    )


def spec_of(layout: LetterheadLayout | None) -> PageSpec:
    """The content box and file of a layout; the built-in one when there is none."""
    if layout is None:
        return BUILTIN
    return PageSpec(
        margin_top_mm=layout.margin_top_mm,
        margin_bottom_mm=layout.margin_bottom_mm,
        margin_left_mm=layout.margin_left_mm,
        margin_right_mm=layout.margin_right_mm,
        signature_area_mm=layout.signature_area_mm,
        font_size_pt=layout.font_size_pt,
        file_id=layout.letterhead_file_id,
        file_type=layout.file_type,
        apply_on=layout.apply_on,
    )


def file_reader(db: Session, store: FileStore) -> FileReader:
    """Stored files for the renderer, checked against their recorded hash."""

    def read(file_id: uuid.UUID) -> tuple[str, bytes]:
        row, data = read_file(db, store, file_id)
        return row.mime, data

    return read


def builtin_header(db: Session, branch: Branch) -> dict[str, object]:
    """The header printed when no letterhead file is drawn: lab and branch, from settings."""
    name = get_value(db, "lab.display_name")
    lines = [branch.name if branch.name != name else "", " ".join(branch.address.split())]
    if branch.phone:
        lines.append(f"Phone {branch.phone}")
    return {"name": name, "lines": [line for line in lines if line]}


def printer_offset(db: Session, branch_id: uuid.UUID) -> tuple[Decimal, Decimal]:
    return (
        Decimal(get_value(db, "print.offset_x_mm", branch_id)),
        Decimal(get_value(db, "print.offset_y_mm", branch_id)),
    )


# Screens


@dataclass
class KindRow:
    doc_kind: str
    label: str
    published: LetterheadLayout | None
    draft: LetterheadLayout | None


@dataclass
class BranchRow:
    branch: Branch
    kinds: list[KindRow]


def overview(db: Session, principal: Principal) -> list[BranchRow]:
    """Each branch the admin may edit, with its published version and draft per kind."""
    allowed = principal.branches_with("letterhead.edit")
    if not allowed:
        raise PermissionDeniedError()
    branches = db.scalars(
        select(Branch).where(Branch.id.in_(allowed), Branch.is_active).order_by(Branch.code)
    )
    return [
        BranchRow(
            b,
            [
                KindRow(k, DOC_LABELS[k], published(db, b.id, k), draft(db, b.id, k))
                for k in DOC_KINDS
            ],
        )
        for b in branches
    ]


@dataclass
class Editor:
    branch: Branch
    doc_kind: str
    label: str
    published: LetterheadLayout | None
    draft: LetterheadLayout | None
    original: StoredFile | None
    optimised: StoredFile | None
    samples: list[tuple[str, str]]

    @property
    def current(self) -> LetterheadLayout | None:
        """What the form shows: the draft, else the published version."""
        return self.draft or self.published


def get_branch(db: Session, principal: Principal, branch_id: uuid.UUID) -> Branch:
    _check(principal, branch_id)
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise NotFoundError()
    return branch


def editor(db: Session, principal: Principal, branch_id: uuid.UUID, doc_kind: str) -> Editor:
    branch = get_branch(db, principal, branch_id)
    kind = _kind(doc_kind)
    pub, drf = published(db, branch.id, kind), draft(db, branch.id, kind)
    current = drf or pub
    original = optimised = None
    if current is not None and current.letterhead_file_id is not None:
        original = db.get(StoredFile, current.original_file_id)
        optimised = db.get(StoredFile, current.letterhead_file_id)
    return Editor(
        branch,
        kind,
        DOC_LABELS[kind],
        pub,
        drf,
        original,
        optimised,
        [(code, SAMPLES[code].label) for code in FOR_KIND[kind]],
    )


# Editing the draft


@dataclass
class LayoutInput:
    """The editor's fields as typed."""

    margin_top_mm: str = "40"
    margin_bottom_mm: str = "25"
    margin_left_mm: str = "15"
    margin_right_mm: str = "15"
    signature_area_mm: str = "30"
    font_size_pt: str = "10"
    apply_on: str = "all"

    @classmethod
    def of(cls, layout: LetterheadLayout | None) -> "LayoutInput":
        if layout is None:
            return cls()
        return cls(
            **{
                f.name: _plain(getattr(layout, f.name)) for f in fields(cls) if f.name != "apply_on"
            },
            apply_on=layout.apply_on,
        )

    def parsed(self) -> dict[str, object]:
        """The values to store, or ValidationFailedError naming each field that is wrong."""
        limits = {
            "margin_top_mm": (0, 120, "mm"),
            "margin_bottom_mm": (0, 120, "mm"),
            "margin_left_mm": (0, 60, "mm"),
            "margin_right_mm": (0, 60, "mm"),
            "signature_area_mm": (0, 80, "mm"),
            "font_size_pt": (7, 14, "pt"),
        }
        values: dict[str, object] = {}
        problems: dict[str, str] = {}
        for name, (low, high, unit) in limits.items():
            raw = getattr(self, name).strip()
            try:
                value = Decimal(raw).quantize(Decimal("0.1"))
            except InvalidOperation:
                value = None
            if value is None or not value.is_finite() or not low <= value <= high:
                problems[name] = f"Enter a number from {low} to {high} {unit}."
            else:
                values[name] = value
        if self.apply_on not in APPLY_ON:
            problems["apply_on"] = "Choose every page or the first page only."
        values["apply_on"] = self.apply_on
        if problems:
            raise ValidationFailedError(problems)
        return values


def _plain(value: Decimal) -> str:
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


_COPIED = (
    "original_file_id",
    "letterhead_file_id",
    "file_type",
    "raster_dpi",
    "original_bytes",
    "optimised_bytes",
    "converted_from",
    "apply_on",
    "margin_top_mm",
    "margin_bottom_mm",
    "margin_left_mm",
    "margin_right_mm",
    "signature_area_mm",
    "font_size_pt",
)


def _editable_draft(
    db: Session, principal: Principal, branch_id: uuid.UUID, doc_kind: str, row_version: int
) -> tuple[LetterheadLayout, bool]:
    """The draft to change, and whether it was just started. `row_version` 0 means the form
    was opened without a draft, so one is started from the latest published version; anything
    else must match the draft's."""
    current = draft(db, branch_id, doc_kind)
    if current is not None:
        if current.row_version != row_version:
            raise stale(db, current)
        return current, False
    if row_version != 0:
        raise ConflictError(
            "This draft was published or discarded since you opened it. Reload to see the"
            " letterhead as it is now."
        )
    base = published(db, branch_id, doc_kind)
    copied = {name: getattr(base, name) for name in _COPIED} if base is not None else {}
    new = LetterheadLayout(
        branch_id=branch_id, doc_kind=doc_kind, created_by=principal.user_id, **copied
    )
    db.add(new)
    db.flush()
    return new, True


def save_draft(
    db: Session,
    principal: Principal,
    branch_id: uuid.UUID,
    doc_kind: str,
    data: LayoutInput,
    row_version: int,
) -> LetterheadLayout:
    branch = get_branch(db, principal, branch_id)
    kind = _kind(doc_kind)
    values = data.parsed()
    layout, created = _editable_draft(db, principal, branch.id, kind, row_version)
    changed = [k for k, v in values.items() if getattr(layout, k) != v]
    for k in changed:
        setattr(layout, k, values[k])
    if changed or created:
        layout.updated_by = principal.user_id
        db.flush()
        audit.record(
            db,
            "letterhead.draft",
            "letterhead_layout",
            layout.id,
            {"doc_kind": kind, "fields": changed},
            user_id=principal.user_id,
            branch_id=branch.id,
        )
    return layout


@dataclass(frozen=True)
class Prepared:
    original_mime: str
    data: bytes
    mime: str
    file_type: str
    raster_dpi: int | None
    removed: dict[str, int]


def prepare_upload(db: Session, data: bytes) -> Prepared:
    """The file to draw, rebuilt from the upload: a sanitised SVG, the first page of a PDF,
    or an image re-encoded at A4."""
    mime = check_upload(data, allowed=UPLOAD_TYPES)
    if mime == SVG:
        try:
            clean = sanitise_svg(data)
        except SvgRefusedError as exc:
            raise ValidationFailedError({"file": str(exc)}) from exc
        return Prepared(mime, clean.data, SVG, "svg", None, clean.removed)
    if mime == PDF:
        return Prepared(mime, prepare_pdf_letterhead(data), PDF, "pdf", None, {})
    if mime in IMAGES:
        dpi = int(get_value(db, "letterhead.raster_dpi"))
        image = optimise_raster(data, dpi)
        return Prepared(mime, image.data, image.mime, "raster", dpi, {})
    raise ValidationFailedError({"file": "Upload an SVG, PDF, PNG, JPEG or WebP file."})


def upload(
    db: Session,
    store: FileStore,
    principal: Principal,
    branch_id: uuid.UUID,
    doc_kind: str,
    data: bytes,
    filename: str,
    row_version: int,
) -> tuple[LetterheadLayout, dict[str, int]]:
    """Put a letterhead file on the draft. Returns the draft and what the SVG sanitiser
    removed, so the screen can say so."""
    branch = get_branch(db, principal, branch_id)
    kind = _kind(doc_kind)
    prepared = prepare_upload(db, data)
    layout, _ = _editable_draft(db, principal, branch.id, kind, row_version)
    original = save_file(
        db, store, data, filename or "letterhead", prepared.original_mime, principal.user_id
    )
    drawn = save_file(
        db,
        store,
        prepared.data,
        f"letterhead-{branch.code.lower()}-{kind}.{_SUFFIX[prepared.mime]}",
        prepared.mime,
        principal.user_id,
    )
    layout.original_file_id = original.id
    layout.letterhead_file_id = drawn.id
    layout.file_type = prepared.file_type
    layout.raster_dpi = prepared.raster_dpi
    layout.original_bytes = len(data)
    layout.optimised_bytes = len(prepared.data)
    layout.converted_from = "none"
    layout.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "letterhead.upload",
        "letterhead_layout",
        layout.id,
        {
            "doc_kind": kind,
            "file_type": prepared.file_type,
            "original_bytes": len(data),
            "optimised_bytes": len(prepared.data),
            "removed": prepared.removed,
        },
        user_id=principal.user_id,
        branch_id=branch.id,
    )
    return layout, prepared.removed


def remove_file(
    db: Session, principal: Principal, branch_id: uuid.UUID, doc_kind: str, row_version: int
) -> LetterheadLayout:
    """Take the file off the draft: the built-in header prints instead."""
    branch = get_branch(db, principal, branch_id)
    kind = _kind(doc_kind)
    layout, _ = _editable_draft(db, principal, branch.id, kind, row_version)
    for name in ("original_file_id", "letterhead_file_id", "file_type", "raster_dpi"):
        setattr(layout, name, None)
    layout.original_bytes = layout.optimised_bytes = 0
    layout.converted_from = "none"
    layout.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "letterhead.draft",
        "letterhead_layout",
        layout.id,
        {"doc_kind": kind, "fields": ["file"]},
        user_id=principal.user_id,
        branch_id=branch.id,
    )
    return layout


def _the_draft(
    db: Session, branch_id: uuid.UUID, doc_kind: str, row_version: int
) -> LetterheadLayout:
    current = draft(db, branch_id, doc_kind)
    if current is None:
        raise ConflictError("There is no draft to publish or discard. Reload the page.")
    if current.row_version != row_version:
        raise stale(db, current)
    return current


def publish(
    db: Session, principal: Principal, branch_id: uuid.UUID, doc_kind: str, row_version: int
) -> LetterheadLayout:
    """Make the draft the next version. From now on new documents use it; documents made
    before keep the version they were made with."""
    branch = get_branch(db, principal, branch_id)
    kind = _kind(doc_kind)
    layout = _the_draft(db, branch.id, kind, row_version)
    last = db.scalar(
        select(func.max(LetterheadLayout.version)).where(
            LetterheadLayout.branch_id == branch.id, LetterheadLayout.doc_kind == kind
        )
    )
    layout.status = "published"
    layout.version = (last or 0) + 1
    layout.published_at = utcnow()
    layout.published_by = principal.user_id
    layout.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "letterhead.publish",
        "letterhead_layout",
        layout.id,
        {"doc_kind": kind, "version": layout.version},
        user_id=principal.user_id,
        branch_id=branch.id,
    )
    return layout


def discard(
    db: Session, principal: Principal, branch_id: uuid.UUID, doc_kind: str, row_version: int
) -> None:
    branch = get_branch(db, principal, branch_id)
    kind = _kind(doc_kind)
    layout = _the_draft(db, branch.id, kind, row_version)
    audit.record(
        db,
        "letterhead.discard",
        "letterhead_layout",
        layout.id,
        {"doc_kind": kind},
        user_id=principal.user_id,
        branch_id=branch.id,
    )
    db.delete(layout)
    db.flush()


# Preview and calibration


def render_sample(
    db: Session,
    store: FileStore,
    branch: Branch,
    spec: PageSpec,
    sample: str,
    output: str,
    *,
    guides: str = "",
) -> Rendered:
    """A made-up document on this layout, for the preview or the calibration page."""
    chosen = SAMPLES[sample]
    html = render_html(
        chosen.template,
        sample=chosen.data,
        guides=guides,
        builtin_header=builtin_header(db, branch) if spec.file_id is None else None,
    )
    offset = printer_offset(db, branch.id) if output == "print" else (Decimal(0), Decimal(0))
    return compose(html, spec, output, files=file_reader(db, store), offset_mm=offset)


def preview(
    db: Session,
    store: FileStore,
    principal: Principal,
    branch_id: uuid.UUID,
    doc_kind: str,
    data: LayoutInput,
    sample: str,
) -> Rendered:
    """The typed values, not yet saved, on the draft's (or published) file, with guides."""
    branch = get_branch(db, principal, branch_id)
    kind = _kind(doc_kind)
    values = data.parsed()
    base = spec_of(draft(db, branch.id, kind) or published(db, branch.id, kind))
    spec = replace(base, **values)  # type: ignore[arg-type]
    code = sample if sample in FOR_KIND[kind] else FOR_KIND[kind][0]
    return render_sample(db, store, branch, spec, code, "digital", guides="preview")


def calibration(
    db: Session, store: FileStore, principal: Principal, branch_id: uuid.UUID, doc_kind: str
) -> Rendered:
    """The print output of the draft (or published) layout with the content box, corner marks
    and a 100 mm line, to print at actual size and check against the letterhead paper."""
    branch = get_branch(db, principal, branch_id)
    kind = _kind(doc_kind)
    spec = spec_of(draft(db, branch.id, kind) or published(db, branch.id, kind))
    return render_sample(db, store, branch, spec, FOR_KIND[kind][0], "print", guides="calibration")


# Documents on a branch's letterhead


def render_document(
    db: Session,
    store: FileStore,
    branch_id: uuid.UUID,
    doc_kind: str,
    output: str,
    build: Callable[[dict[str, object] | None], str],
    *,
    at: datetime | None = None,
) -> Rendered:
    """A document on the layout the branch had published at `at`, or now. `build` is given
    the built-in header, which it prints when that layout has no letterhead file, and returns
    the document's HTML."""
    kind = _kind(doc_kind)
    if output not in OUTPUTS:
        raise NotFoundError()
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise NotFoundError()
    spec = spec_of(published(db, branch.id, kind, at=at))
    html = build(builtin_header(db, branch) if spec.file_id is None else None)
    offset = printer_offset(db, branch.id) if output == "print" else (Decimal(0), Decimal(0))
    return compose(html, spec, output, files=file_reader(db, store), offset_mm=offset)
