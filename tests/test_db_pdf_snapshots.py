"""PDF snapshots (design §7.0, §7.2): the words of a 3-page report and of a bill, and where
each one sits, are kept in `tests/goldens/`. A change to a template, the CSS or the PDF
engine that moves text shows up here as a diff to look at, not as a surprise on paper.

Positions are compared with a small tolerance, so a different build of the text shaping
library doesn't fail the test while a moved column or a new line does. After a deliberate
change, write the goldens again with `LABRA_WRITE_GOLDENS=1 uv run pytest
tests/test_db_pdf_snapshots.py` and review the diff of the JSON files.
"""

import io
import json
import os
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pdfplumber
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from labra.billing import service as billing
from labra.billing.routes import _printed
from labra.core.registry import Platform
from labra.printing import samples
from labra.printing.letterhead import PageSpec, compose
from labra.printing.service import BUILTIN
from labra.web.documents import document_html
from tests.test_db_visits_web import _full_bill

GOLDENS = Path(__file__).parent / "goldens"
# Points; a column or a line moved by a character's width or more is caught.
TOLERANCE = 1.5
# The 3-page report as a lab with a letterhead would set it up: the editor's defaults.
SPEC = PageSpec(
    margin_top_mm=Decimal(40),
    margin_bottom_mm=Decimal(25),
    margin_left_mm=Decimal(15),
    margin_right_mm=Decimal(15),
    signature_area_mm=Decimal(30),
    font_size_pt=Decimal(10),
)
# A report on the counter PC must be ready well before the patient has paid.
RENDER_BUDGET_S = 2.0

Words = list[list[list[Any]]]


def _words(pdf: bytes) -> Words:
    """Each page's words in reading order, with the left edge and top in points."""
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return [
            [[w["text"], round(w["x0"], 1), round(w["top"], 1)] for w in page.extract_words()]
            for page in doc.pages
        ]


def _matches(name: str, got: Words) -> None:
    path = GOLDENS / f"{name}.json"
    if os.environ.get("LABRA_WRITE_GOLDENS") == "1":
        GOLDENS.mkdir(exist_ok=True)
        lines = ",\n".join(json.dumps(page, ensure_ascii=False) for page in got)
        path.write_text(f"[\n{lines}\n]\n", encoding="utf-8")
        pytest.fail(f"wrote {path.name}; review its diff, then run again without the variable")
    want: Words = json.loads(path.read_text(encoding="utf-8"))
    assert len(got) == len(want), f"{name}: {len(got)} pages, the golden has {len(want)}"
    for number, (page, golden) in enumerate(zip(got, want, strict=True), start=1):
        assert [w[0] for w in page] == [w[0] for w in golden], f"{name} page {number}: words"
        moved = [
            (w[0], (g[1], g[2]), (w[1], w[2]))
            for w, g in zip(page, golden, strict=True)
            if abs(w[1] - g[1]) > TOLERANCE or abs(w[2] - g[2]) > TOLERANCE
        ]
        assert moved == [], f"{name} page {number}: moved (word, golden, now)"


@pytest.mark.item("EC-H03")
@pytest.mark.item("M12")
def test_the_report_matches_its_snapshot() -> None:
    _matches("report_three_pages", _words(samples.render("three_pages", SPEC, "digital").pdf))


@pytest.mark.item("EC-H03")
@pytest.mark.item("M17")
def test_the_bill_matches_its_snapshot(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    db = seeded
    bill = _full_bill(db, platform, db_client)
    lines = billing.bill_lines(db, bill.id)
    payments = billing.bill_payments(db, bill.id)
    db.expunge_all()
    # What changes from run to run (numbers carry the financial year, dates are today) is
    # pinned; everything else is the bill as the counter made it.
    bill.bill_no, bill.bill_date = "B2/B/2627/000001", date(2026, 10, 14)
    snap = dict(bill.print_snapshot)
    snap["visit_no"] = "B2/V/2627/000001"
    snap["recipient"] = dict(snap["recipient"]) | {"patient_no": "P-000001"}
    snap["sample_nos"] = [f"S{n:07d}" for n in range(1, len(snap["sample_nos"]) + 1)]
    bill.print_snapshot = snap
    for n, payment in enumerate(payments, start=1):
        payment.receipt_no = f"B2/RC/2627/{n:06d}"
        payment.received_at = datetime(2026, 10, 14, 4, 30, tzinfo=UTC)
    context = _printed(db, bill) | {"lines": lines, "payments": payments, "refund": None}

    pdf = compose(document_html("pdf/bill.html", context), BUILTIN, "digital").pdf

    _matches("bill", _words(pdf))


@pytest.mark.item("EC-H03")
@pytest.mark.item("M12")
def test_a_three_page_report_renders_within_its_budget() -> None:
    samples.render("short", SPEC, "digital")  # fonts loaded once per process
    started = time.perf_counter()
    rendered = samples.render("three_pages", SPEC, "digital")
    took = time.perf_counter() - started
    assert len(_words(rendered.pdf)) == 3
    assert took < RENDER_BUDGET_S, f"{took:.2f} s"
