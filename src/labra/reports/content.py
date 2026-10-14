"""What a report shows (design §7, §7.0).

`snapshot` reads the visit's records once and keeps everything the PDF prints as plain JSON
values: the patient band, each test as a panel with its rows, tiers, critical-value lines and
footnote marks, what is still pending, and who signs. Release stores it, so every later copy
(print, selected tests, A5) is drawn from the same values as the stored PDF.

`view` turns a snapshot into what one output prints: only the chosen tests, and what
depends on them (the NABL number, the outside-lab and research footnotes).
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


def _panel(db: Session, ordered: OrderTest, samples: dict[uuid.UUID, Sample]) -> dict[str, Any]:
    sheet = load_sheet(db, ordered.id)
    test = sheet.test
    sample = samples.get(ordered.sample_id) if ordered.sample_id else None
    specimen_id = (sample.specimen_type_id if sample else None) or test.specimen_type_id
    specimen = db.get(SpecimenType, specimen_id) if specimen_id else None
    department = db.get_one(Department, test.department_id)
    rows, tiers, critical = _rows(db, sheet)
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
) -> dict[str, Any]:
    """Everything the report prints for `tests`, signed by `signatory`. `pending` are the
    visit's tests not yet signed off, listed with their expected time."""
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
    panels = sorted((_panel(db, t, samples) for t in tests), key=lambda p: p["sort"])
    names = (
        {
            t.id: name
            for t, name in db.execute(
                select(OrderTest, CatalogTest.name)
                .join(CatalogTest, CatalogTest.id == OrderTest.test_id)
                .where(OrderTest.id.in_([p.id for p in pending]))
            )
        }
        if pending
        else {}
    )
    return {
        "schema": SCHEMA,
        "report_no": report_no,
        "version": version,
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
        "research": any(p["research"] for p in panels),
        "selected": (
            f"Selected tests only: {len(panels)} of {len(every)} on this report"
            if len(panels) < len(every)
            else ""
        ),
        "signatory": signatory | {"signature": f"{FILE}{signature}" if signature else ""},
        "footer_text": content["footer_text"],
    }
