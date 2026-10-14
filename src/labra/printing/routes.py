from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import current_principal
from labra.auth.principal import Principal
from labra.core.db import get_session
from labra.core.errors import PermissionDeniedError, ValidationFailedError
from labra.core.files import MAX_BYTES
from labra.core.registry import get_platform
from labra.printing import service
from labra.printing.preview import data_uri, page_pngs
from labra.web.forms import RowVersion, as_uuid
from labra.web.templating import page, render

router = APIRouter(prefix="/admin/letterheads")

DB = Annotated[Session, Depends(get_session)]
MANUAL = "admin/letterhead-and-margins"


def _letterhead_admin(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    """Someone who may set the letterhead of at least one branch; the service checks the
    branch named in the address."""
    if not principal.branches_with("letterhead.edit"):
        raise PermissionDeniedError()
    return principal


_letterhead_admin.__guard__ = "letterhead.edit"  # type: ignore[attr-defined]
Admin = Annotated[Principal, Depends(_letterhead_admin)]


def _layout_input(
    margin_top_mm: str,
    margin_bottom_mm: str,
    margin_left_mm: str,
    margin_right_mm: str,
    signature_area_mm: str,
    font_size_pt: str,
    apply_on: str,
) -> service.LayoutInput:
    return service.LayoutInput(
        margin_top_mm,
        margin_bottom_mm,
        margin_left_mm,
        margin_right_mm,
        signature_area_mm,
        font_size_pt,
        apply_on,
    )


def _url(branch_id: object, doc_kind: str) -> str:
    return f"/admin/letterheads/{branch_id}/{doc_kind}"


@router.get("", response_class=HTMLResponse)
@page(MANUAL, "printing/letterheads.html")
def letterheads(request: Request, db: DB, principal: Admin) -> Response:
    return render(request, "printing/letterheads.html", {"rows": service.overview(db, principal)})


def _editor(
    request: Request,
    db: Session,
    principal: Principal,
    branch_id: str,
    doc_kind: str,
    *,
    values: service.LayoutInput | None = None,
    errors: dict[str, str] | None = None,
    removed: dict[str, int] | None = None,
    status: int = 200,
) -> Response:
    editor = service.editor(db, principal, as_uuid(branch_id), doc_kind)
    return render(
        request,
        "printing/letterhead.html",
        {
            "editor": editor,
            "values": values or service.LayoutInput.of(editor.current),
            "errors": errors or {},
            "removed": removed or {},
            "url": _url(editor.branch.id, editor.doc_kind),
            "file_labels": service.FILE_LABELS,
        },
        status_code=status,
    )


@router.get("/{branch_id}/{doc_kind}", response_class=HTMLResponse)
@page(MANUAL, "printing/letterhead.html")
def letterhead(
    request: Request, branch_id: str, doc_kind: str, db: DB, principal: Admin
) -> Response:
    return _editor(request, db, principal, branch_id, doc_kind)


LayoutForm = Annotated[str, Form()]


@router.post("/{branch_id}/{doc_kind}/draft")
def draft_save(
    request: Request,
    branch_id: str,
    doc_kind: str,
    db: DB,
    principal: Admin,
    margin_top_mm: LayoutForm = "",
    margin_bottom_mm: LayoutForm = "",
    margin_left_mm: LayoutForm = "",
    margin_right_mm: LayoutForm = "",
    signature_area_mm: LayoutForm = "",
    font_size_pt: LayoutForm = "",
    apply_on: LayoutForm = "all",
    row_version: RowVersion = 0,
) -> Response:
    data = _layout_input(
        margin_top_mm,
        margin_bottom_mm,
        margin_left_mm,
        margin_right_mm,
        signature_area_mm,
        font_size_pt,
        apply_on,
    )
    try:
        layout = service.save_draft(db, principal, as_uuid(branch_id), doc_kind, data, row_version)
    except ValidationFailedError as exc:
        db.rollback()
        return _editor(
            request, db, principal, branch_id, doc_kind, values=data, errors=exc.errors, status=422
        )
    db.commit()
    return RedirectResponse(_url(layout.branch_id, layout.doc_kind), status_code=303)


@router.post("/{branch_id}/{doc_kind}/upload")
def upload(
    request: Request,
    branch_id: str,
    doc_kind: str,
    db: DB,
    principal: Admin,
    file: UploadFile | None = None,
    row_version: RowVersion = 0,
) -> Response:
    # One byte past the cap is enough to know the file is too large.
    data = file.file.read(MAX_BYTES + 1) if file is not None else b""
    name = (file.filename or "") if file is not None else ""
    try:
        _, removed = service.upload(
            db,
            get_platform().filestore,
            principal,
            as_uuid(branch_id),
            doc_kind,
            data,
            name,
            row_version,
        )
    except ValidationFailedError as exc:
        db.rollback()
        return _editor(request, db, principal, branch_id, doc_kind, errors=exc.errors, status=422)
    db.commit()
    if removed:
        # Shown once, on the page itself, so the admin sees what the sanitiser took out.
        return _editor(request, db, principal, branch_id, doc_kind, removed=removed)
    return RedirectResponse(_url(branch_id, doc_kind), status_code=303)


@router.post("/{branch_id}/{doc_kind}/remove-file")
def remove_file(
    branch_id: str, doc_kind: str, db: DB, principal: Admin, row_version: RowVersion = 0
) -> Response:
    service.remove_file(db, principal, as_uuid(branch_id), doc_kind, row_version)
    db.commit()
    return RedirectResponse(_url(branch_id, doc_kind), status_code=303)


@router.post("/{branch_id}/{doc_kind}/preview", response_class=HTMLResponse)
def preview(
    request: Request,
    branch_id: str,
    doc_kind: str,
    db: DB,
    principal: Admin,
    margin_top_mm: LayoutForm = "",
    margin_bottom_mm: LayoutForm = "",
    margin_left_mm: LayoutForm = "",
    margin_right_mm: LayoutForm = "",
    signature_area_mm: LayoutForm = "",
    font_size_pt: LayoutForm = "",
    apply_on: LayoutForm = "all",
    sample: LayoutForm = "",
) -> Response:
    """Page images of a sample document on the values typed so far, not yet saved."""
    data = _layout_input(
        margin_top_mm,
        margin_bottom_mm,
        margin_left_mm,
        margin_right_mm,
        signature_area_mm,
        font_size_pt,
        apply_on,
    )
    try:
        rendered = service.preview(
            db, get_platform().filestore, principal, as_uuid(branch_id), doc_kind, data, sample
        )
    except ValidationFailedError as exc:
        return render(request, "printing/_preview.html", {"pages": [], "errors": exc.errors})
    pages = [data_uri(png) for png in page_pngs(rendered.pdf)]
    return render(
        request,
        "printing/_preview.html",
        {"pages": pages, "total": rendered.pages, "errors": {}},
    )


@router.get("/{branch_id}/{doc_kind}/calibration")
@page(MANUAL, "printing/letterhead.html")
def calibration(branch_id: str, doc_kind: str, db: DB, principal: Admin) -> Response:
    """The print output with guides, shown in the browser's PDF viewer to print at 100%."""
    rendered = service.calibration(
        db, get_platform().filestore, principal, as_uuid(branch_id), doc_kind
    )
    return Response(
        rendered.pdf,
        media_type="application/pdf",
        headers={"content-disposition": f'inline; filename="calibration-{doc_kind}.pdf"'},
    )


@router.post("/{branch_id}/{doc_kind}/publish")
def publish(
    branch_id: str, doc_kind: str, db: DB, principal: Admin, row_version: RowVersion = 0
) -> Response:
    service.publish(db, principal, as_uuid(branch_id), doc_kind, row_version)
    db.commit()
    return RedirectResponse(_url(branch_id, doc_kind), status_code=303)


@router.post("/{branch_id}/{doc_kind}/discard")
def discard(
    branch_id: str, doc_kind: str, db: DB, principal: Admin, row_version: RowVersion = 0
) -> Response:
    service.discard(db, principal, as_uuid(branch_id), doc_kind, row_version)
    db.commit()
    return RedirectResponse(_url(branch_id, doc_kind), status_code=303)
