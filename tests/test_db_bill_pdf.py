"""The bill of supply as a PDF on the branch's bill letterhead: the same content as the print
page, the letterhead on the copy to send and not on the copy for pre-printed paper, and a
reprint on the layout that was in force when the bill was issued."""

import io

import pdfplumber
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.billing.models import Payment
from labra.core import lab_settings
from labra.core.registry import Platform
from labra.printing import service as letterheads
from tests.frontdesk import as_user, billed, branch, sign_in
from tests.test_db_visits_web import UTR, _full_bill
from tests.test_letterhead import _images, _picture

pytestmark = [pytest.mark.item("M17"), pytest.mark.item("M07")]
MM = 72 / 25.4


def _text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def _top_mm(pdf: bytes) -> float:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return min(c["top"] for c in doc.pages[0].chars) / MM


def _publish(db: Session, platform: Platform, code: str, top: str, picture: bool = False) -> None:
    anil = as_user(db, platform, "anil")
    where = branch(db, code).id
    data = letterheads.LayoutInput(margin_top_mm=top)
    layout = letterheads.save_draft(db, anil, where, "bill_a4", data, 0)
    if picture:
        layout, _ = letterheads.upload(
            db, platform.filestore, anil, where, "bill_a4", _picture(), "lh.png", layout.row_version
        )
    letterheads.publish(db, anil, where, "bill_a4", layout.row_version)


def test_the_bill_pdf_carries_what_the_print_page_shows(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    bill = _full_bill(seeded, platform, db_client)
    payment = seeded.scalars(select(Payment).where(Payment.bill_id == bill.id)).one()
    supplier = bill.print_snapshot["supplier"]

    response = db_client.get(f"/frontdesk/bills/{bill.id}/pdf?output=digital")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    name = bill.bill_no.replace("/", "-")
    assert response.headers["content-disposition"] == f'inline; filename="bill-{name}.pdf"'
    assert response.headers["cache-control"] == "no-store"
    text = _text(response.content)
    for expected in (
        "Bill of Supply",
        supplier["legal_name"],
        f"Bill number: {bill.bill_no}",
        "Patient: Sunita Testcase",
        "Glucose, fasting",
        "Vitamin D",
        "Discount: Senior citizen",
        "1,737.00",
        f"Receipt {payment.receipt_no}",
        f"UTR {UTR}",
        "Balance due",
        "₹737.00",
        "Authorised signatory",
        "Fasting sample taken at 8 am",
    ):
        assert expected in text, expected
    assert "Called twice about the due" not in text

    summary = db_client.get(f"/frontdesk/visits/{bill.visit_id}").text
    assert f'href="/frontdesk/bills/{bill.id}/pdf"' in summary
    assert f'href="/frontdesk/bills/{bill.id}/pdf?output=digital"' in summary


def test_the_letterhead_is_on_the_copy_to_send_and_off_the_copy_for_printed_paper(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    _publish(seeded, platform, "B2", "50", picture=True)
    priya = as_user(seeded, platform, "priya")
    bill = billed(seeded, priya)
    sign_in(db_client, "priya")
    url = f"/frontdesk/bills/{bill.id}/pdf"

    digital = db_client.get(f"{url}?output=digital").content
    printed = db_client.get(f"{url}?output=print").content
    assert len(_images(digital)) == 1 and not _images(printed)
    assert _top_mm(digital) == pytest.approx(_top_mm(printed), abs=0.1)
    assert _top_mm(digital) >= 50 - 0.5

    # No choice: the branch's usual one, which starts as the copy for printed paper.
    assert not _images(db_client.get(url).content)
    b2 = branch(seeded, "B2").id
    anil = as_user(seeded, platform, "anil")
    lab_settings.set_value(seeded, "print.default_mode", "digital", anil.user_id, branch_id=b2)
    assert _images(db_client.get(url).content)

    lab_settings.set_value(seeded, "print.offset_y_mm", "6", anil.user_id, branch_id=b2)
    shifted = db_client.get(f"{url}?output=print").content
    assert _top_mm(shifted) - _top_mm(printed) == pytest.approx(6, abs=0.1)
    assert _top_mm(db_client.get(f"{url}?output=digital").content) == pytest.approx(
        _top_mm(digital), abs=0.1
    )


def test_a_reprint_uses_the_layout_published_when_the_bill_was_issued(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    priya = as_user(seeded, platform, "priya")
    before_any = billed(seeded, priya)
    _publish(seeded, platform, "B2", "50")
    first = billed(seeded, priya)
    _publish(seeded, platform, "B2", "80")
    second = billed(seeded, priya)
    sign_in(db_client, "priya")

    def top(bill_id: object) -> float:
        return _top_mm(db_client.get(f"/frontdesk/bills/{bill_id}/pdf?output=print").content)

    assert top(before_any.id) == pytest.approx(15, abs=3)  # the built-in margins
    assert top(first.id) == pytest.approx(50, abs=3)
    assert top(second.id) == pytest.approx(80, abs=3)


def test_a_bill_pdf_follows_the_bill_permission_and_branch(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    bill = billed(seeded, as_user(seeded, platform, "priya"))
    sign_in(db_client, "b3desk")
    assert db_client.get(f"/frontdesk/bills/{bill.id}/pdf").status_code == 404
    sign_in(db_client, "priya")
    assert db_client.get(f"/frontdesk/bills/{bill.id}/pdf?output=fax").status_code == 404
    db_client.cookies.clear()
    assert db_client.get(f"/frontdesk/bills/{bill.id}/pdf").status_code in {303, 401}
