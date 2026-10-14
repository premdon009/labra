"""What a report shows (design §7, §7.0).

`snapshot` reads the visit's records once and keeps everything the PDF prints as plain JSON
values: the patient band, each test as a panel with its rows, tiers, critical-value lines and
footnote marks, what is still pending, and who signs. Release stores it, so every later copy
(print, selected tests, A5) is drawn from the same values as the stored PDF.

`view` turns a snapshot into what one output prints: only the chosen tests, and what
depends on them (the NABL number, the outside-lab and research footnotes, the outside labs'
PDFs added after the last page).

An outside test with no typed values is reported by the lab's own PDF: its panel says so and
the PDF's pages follow the report. A forwarded report (separate mode) is a cover page for one
outside document: every test on it is reported that way.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.catalog import units
from labra.catalog.models import Department, SpecimenType, TestMethod
from labra.catalog.models import Test as CatalogTest
from labra.core.ids import IST
from labra.core.lab_settings import get_value
from labra.extlabs.models import ExternalLab
from labra.org.models import AppUser, Branch
from labra.patients.age import age_text
from labra.patients.models import Patient, Referrer
from labra.printing.pdf import FILE
from labra.printing.reportpage import barcode, qr
from labra.printing.service import builtin_header
from labra.results.models import ExternalDocument, ExternalDocumentTest
from labra.results.worklist import Sheet, bands_of, load_sheet, range_text, shown, told_about
from labra.visits.models import OrderTest, Sample, Visit

SCHEMA = 1
PAPERS = ("A4", "A5")
# Flags that make a value bold and print in the flag column; N (inside the range) does not.
FLAGGED = ("L", "H", "LL", "HH", "A")
NOT_CALCULABLE = "Not calculable"
OUTSIDE_MARK = "*"
RESEARCH_MARK = "†"
SEXES = {"F": "F", "M": "M", "O": "O"}
TITLE = "Laboratory report"
FORWARD_TITLE = "Outside laboratory report"


def when(at: datetime | None) -> str:
    """A time as the report prints it, in India time."""
    return at.astimezone(IST).strftime("%d %b %Y %H:%M") if at is not None else ""


@dataclass(frozen=True)
class Options:
    """The choices for one copy: paper size, the reference column, and which tests (all
    when empty)."""

    paper: str = "A4"
    reference: bool = True
    tests: frozenset[str] = field(default_factory=frozenset)


def stored_options(content: dict[str, Any]) -> Options:
    """The choices the stored copy was made with; reports from before they were recorded
    were made on A4 with the reference column."""
    stored = content.get("stored", {})
    return Options(stored.get("paper", "A4"), stored.get("reference", True))


# Building the snapshot


def _method(db: Session, ordered: OrderTest) -> str:
    """The method chosen for this test, else the test's default one."""
    if ordered.method_id is not None:
        chosen = db.get(TestMethod, ordered.method_id)
        if chosen is not None:
            return chosen.name
    default = db.scalar(
        select(TestMethod.name).where(
            TestMethod.test_id == ordered.test_id, TestMethod.is_default, TestMethod.is_active
        )
    )
    return default or ""


def _rows(
    db: Session, sheet: Sheet
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    """The test's printed rows, its tier boxes and its critical-value lines."""
    told = told_about(db, sheet)
    rows: list[dict[str, Any]] = []
    tiers: list[dict[str, str]] = []
    critical: list[str] = []
    for parameter in sheet.parameters:
        result = sheet.results.get(parameter.id)
        if not parameter.is_reportable or result is None:
            continue
        if result.not_calculable:
            value = NOT_CALCULABLE
        elif result.value_num is not None:
            value = shown(result.value_num, parameter.decimals)
        elif result.value_text:
            value = result.value_text
        else:
            continue
        flag = result.flag if result.flag in FLAGGED else ""
        unit = units.label(result.unit)
        rows.append(
            {
                "name": parameter.name,
                "calc": parameter.result_type == "calculated",
                "result": value,
                "flag": flag,
                "unit": unit,
                "range": result.ref_range_text,
                "note": result.comment,
                # Widal titres and microscopy text use the width the empty cells leave.
                "text_only": not unit and not result.ref_range_text and not flag,
            }
        )
        bands = bands_of(db, sheet.range_for(parameter.id))
        if bands and result.value_num is not None:
            tiers.append(
                {
                    "name": parameter.name,
                    "bands": " · ".join(
                        f"{range_text(b.low, b.high)} {b.label}".strip() for b in bands
                    ),
                    "this": result.band_label,
                }
            )
        note = told.get(result.id)
        if note is not None:
            critical.append(
                f"Critical value: {parameter.name} {value} {flag}, informed to"
                f" {note.informed_to} at {when(note.informed_at)}"
            )
    return rows, tiers, critical


def documents_of(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, ExternalDocument]:
    """The latest outside-lab PDF attached to each of these tests, where one is."""
    if not ids:
        return {}
    latest: dict[uuid.UUID, ExternalDocument] = {}
    for document, order_test_id in db.execute(
        select(ExternalDocument, ExternalDocumentTest.order_test_id)
        .join(
            ExternalDocumentTest, ExternalDocumentTest.external_document_id == ExternalDocument.id
        )
        .where(ExternalDocumentTest.order_test_id.in_(ids))
        .order_by(ExternalDocument.received_at, ExternalDocument.id)
    ):
        latest[order_test_id] = document
    return latest


def _panel(
    db: Session,
    ordered: OrderTest,
    samples: dict[uuid.UUID, Sample],
    document: ExternalDocument | None,
    forward: bool,
) -> dict[str, Any]:
    sheet = load_sheet(db, ordered.id)
    test = sheet.test
    sample = samples.get(ordered.sample_id) if ordered.sample_id else None
    specimen_id = (sample.specimen_type_id if sample else None) or test.specimen_type_id
    specimen = db.get(SpecimenType, specimen_id) if specimen_id else None
    department = db.get_one(Department, test.department_id)
    rows, tiers, critical = ([], [], []) if forward else _rows(db, sheet)
    # Reported by the outside lab's own pages: on a forwarded report always, otherwise when
    # nothing was typed from them.
    attached = document is not None and (forward or not rows)
    outside: dict[str, str] | None = None
    nabl = ""
    if ordered.route == "external" and ordered.external_lab_id is not None:
        lab = db.get_one(ExternalLab, ordered.external_lab_id)
        outside = {
            "lab": lab.name,
            "nabl": lab.nabl_cert_no,
            "accession": ordered.external_accession_no,
        }
    elif test.in_nabl_scope:
        nabl = db.get_one(Branch, ordered.perform_branch_id).nabl_cert_no
    return {
        "key": ordered.id.hex,
        "order_test_id": str(ordered.id),
        "department": department.name,
        "sort": [department.report_order, department.name, test.display_order, test.name],
        "name": test.name,
        "specimen": specimen.name if specimen else "",
        "sample_no": sample.sample_no if sample else "",
        "remarks": sample.remarks if sample else "",
        "method": _method(db, ordered),
        "research": test.research_use,
        "outside": outside,
        "attached": str(document.id) if attached and document is not None else None,
        # The performing branch's NABL number when the test is in its scope; blank otherwise.
        "nabl": nabl,
        "rows": rows,
        "tiers": tiers,
        "critical": critical,
        "interpretation": test.interpretation_text.strip(),
    }


def snapshot(
    db: Session,
    visit: Visit,
    tests: Sequence[OrderTest],
    pending: Sequence[OrderTest],
    signatory: AppUser,
    *,
    reported_at: datetime,
    report_no: str = "",
    version: int = 0,
    forward: ExternalDocument | None = None,
    separately: Sequence[OrderTest] = (),
    amended: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Everything the report prints for `tests`, signed by `signatory`. `pending` are the
    visit's tests not yet signed off, listed with their expected time. With `forward` the
    report is the cover for that outside document; `separately` are the outside tests that
    have a report of their own; `amended` says which version this one corrects, and why."""
    branch = db.get_one(Branch, visit.branch_id)
    patient = db.get_one(Patient, visit.patient_id)
    referrer = db.get(Referrer, visit.referrer_id) if visit.referrer_id else None
    sample_ids = {t.sample_id for t in tests if t.sample_id is not None}
    samples = (
        {s.id: s for s in db.scalars(select(Sample).where(Sample.id.in_(sample_ids)))}
        if sample_ids
        else {}
    )
    collected = min(
        (s.collected_at for s in samples.values() if s.collected_at), default=visit.visited_at
    )
    received = max((s.received_at for s in samples.values() if s.received_at), default=None)
    outside = [t.id for t in tests if t.route == "external"]
    if forward is not None:
        documents = dict.fromkeys(outside, forward)
    else:
        documents = documents_of(db, outside)
    panels = sorted(
        (_panel(db, t, samples, documents.get(t.id), forward is not None) for t in tests),
        key=lambda p: p["sort"],
    )
    attachments: dict[str, dict[str, Any]] = {}
    for panel in panels:
        if panel["attached"] is None or panel["outside"] is None:
            continue
        document = documents[uuid.UUID(panel["order_test_id"])]
        entry = attachments.setdefault(
            panel["attached"],
            {
                "document_id": panel["attached"],
                "file_id": str(document.file_id),
                "sha256": document.sha256,
                "lab": panel["outside"]["lab"],
                "tests": [],
            },
        )
        entry["tests"].append(panel["name"])
    listed = [*pending, *separately]
    names = (
        {
            t.id: name
            for t, name in db.execute(
                select(OrderTest, CatalogTest.name)
                .join(CatalogTest, CatalogTest.id == OrderTest.test_id)
                .where(OrderTest.id.in_([t.id for t in listed]))
            )
        }
        if listed
        else {}
    )
    return {
        "schema": SCHEMA,
        "report_no": report_no,
        "version": version,
        "title": FORWARD_TITLE if forward is not None else TITLE,
        "amended": amended,
        "header": builtin_header(db, branch),
        "patient": {
            "name": " ".join(part for part in (patient.title, patient.full_name) if part),
            "patient_no": patient.patient_no,
            "age_sex": f"{age_text(patient.dob, collected.astimezone(IST).date())}"
            f" / {SEXES.get(patient.sex, patient.sex)}",
        },
        "visit": {
            "visit_no": visit.visit_no,
            "branch": branch.name,
            "referrer": referrer.name if referrer else "Self",
            "collected": when(collected),
            "received": when(received),
            "reported": when(reported_at),
        },
        "panels": panels,
        "pending": [
            {"name": names[t.id], "expected": when(t.due_at)}
            for t in sorted(pending, key=lambda t: (t.due_at, names[t.id]))
        ],
        "separately": sorted(names[t.id] for t in separately),
        # Frozen with the report, so every later copy adds the same pages.
        "attachments": list(attachments.values()),
        "signatory": {
            "name": signatory.full_name,
            "qualification": signatory.qualification,
            "council_reg_no": signatory.council_reg_no,
            "signature_file_id": str(signatory.signature_file_id)
            if signatory.signature_file_id
            else None,
        },
        "footer_text": get_value(db, "report.footer_text"),
    }


# What one copy prints


def view(content: dict[str, Any], options: Options, *, preview: bool = False) -> dict[str, Any]:
    """The template's values for one copy of the report."""
    every = content["panels"]
    panels = [p for p in every if not options.tests or p["order_test_id"] in options.tests]
    departments: list[dict[str, Any]] = []
    for panel in panels:
        if not departments or departments[-1]["name"] != panel["department"]:
            departments.append({"name": panel["department"], "panels": []})
        departments[-1]["panels"].append(panel)
    outside: list[str] = []
    for panel in panels:
        lab = panel["outside"]
        if lab is None:
            continue
        line = f"{panel['name']}: performed by {lab['lab']}"
        if lab["nabl"]:
            line += f" (NABL {lab['nabl']})"
        if lab["accession"]:
            line += f", accession {lab['accession']}"
        outside.append(line)
    chosen = {p.get("attached") for p in panels} - {None}
    numbers = {p["nabl"] for p in panels}
    # Printed only when every test on this copy is in the scope of a NABL-accredited branch.
    nabl = ", ".join(sorted(numbers)) if panels and "" not in numbers else ""
    signatory = content["signatory"]
    signature = signatory["signature_file_id"]
    if preview:
        reference = "Preview, not released"
    else:
        reference = f"Report {content['report_no']} v{content['version']}"
    return {
        "preview": preview,
        "title": content.get("title", TITLE),
        "amended": content.get("amended"),
        "reference": reference,
        "header": content["header"],
        "patient": content["patient"],
        "visit": content["visit"],
        "barcode": barcode(content["visit"]["visit_no"]),
        # Set at release; a preview has none.
        "qr": qr(content["qr"]) if content.get("qr") else None,
        "nabl": nabl,
        "departments": departments,
        "show_reference": options.reference,
        "partial": bool(content["pending"]),
        "pending": content["pending"],
        "outside": outside,
        "separately": content.get("separately", []),
        "attachments": [a for a in content.get("attachments", []) if a["document_id"] in chosen],
        "research": any(p["research"] for p in panels),
        "selected": (
            f"Selected tests only: {len(panels)} of {len(every)} on this report"
            if len(panels) < len(every)
            else ""
        ),
        "signatory": signatory | {"signature": f"{FILE}{signature}" if signature else ""},
        "footer_text": content["footer_text"],
    }
