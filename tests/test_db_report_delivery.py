"""Copies of a released report and handing it over (design §7): the stored PDF when it is the
full digital copy, otherwise made again from what was released; a due on the bill needs a
tick; every copy and hand-over is logged, and a hand-over reaches the tests' timeline."""

import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.billing import service as billing
from labra.billing.models import Bill
from labra.billing.service import PaymentInput
from labra.core import lab_settings
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.files import read_file
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.org.models import AppUser
from labra.reports import delivery, service
from labra.reports.content import Options, stored_options
from labra.reports.models import Report, ReportDelivery, ReportPrint
from labra.results.models import OrderTestEvent
from labra.visits.models import Visit
from tests import test_db_report_content as content
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, post, sign_in
from tests.test_db_report_content import _day, _ordered, _pages
from tests.test_db_report_release import _release, _tsh

lab = content.lab

RECEIVED_BY = "Synthetic Relative"


def _flat(pdf: bytes) -> str:
    return " ".join(" ".join(_pages(pdf)).split())


def _copy(
    db: Session, platform: Platform, report: Report, output: str = "digital", **chosen: object
) -> bytes:
    priya = as_user(db, platform, "priya")
    _, data = delivery.make_copy(
        db,
        platform.filestore,
        priya,
        report.id,
        output,
        True,
        **chosen,  # type: ignore[arg-type]
    )
    return data


def _last_print(db: Session) -> ReportPrint:
    return db.scalars(select(ReportPrint).order_by(ReportPrint.printed_at.desc()).limit(1)).one()


def _staff(db: Session, username: str) -> uuid.UUID:
    return db.scalars(select(AppUser.id).where(AppUser.username == username)).one()


def _settle(db: Session, platform: Platform, visit: Visit) -> None:
    bill = db.scalars(select(Bill).where(Bill.visit_id == visit.id)).one()
    priya = as_user(db, platform, "priya")
    payment = PaymentInput("cash", bill.due)
    billing.take_payment(db, priya, bill.id, payment, uuid.uuid4(), SEED_DAY)
    db.flush()
    db.refresh(bill)


@pytest.mark.item("M21")
@pytest.mark.item("M20")
def test_a_copy_needs_the_dues_tick_and_is_logged(lab: Session, platform: Platform) -> None:
    visit = _day(lab, platform)
    report = _release(lab, platform, visit)
    priya = as_user(lab, platform, "priya")
    due = delivery.due_on(lab, visit.id)
    assert due > 0

    with pytest.raises(ValidationFailedError) as refused:
        delivery.make_copy(lab, platform.filestore, priya, report.id, "digital", False)
    assert refused.value.errors == {"dues": delivery.DUES}
    assert lab.scalars(select(ReportPrint)).all() == []

    # The full digital copy is the stored file itself.
    data = _copy(lab, platform, report)
    assert hashlib.sha256(data).hexdigest() == report.sha256
    logged = _last_print(lab)
    assert logged.output == "digital" and logged.order_test_ids == []
    assert logged.options == {"paper": "A4", "reference": True}
    assert logged.dues_at_print == due and logged.printed_by == priya.user_id
    # So is a copy with every test ticked.
    lipid, hb = _ordered(lab, visit, "lipid"), _ordered(lab, visit, "hb")
    every = _copy(lab, platform, report, tests=[str(lipid.id), str(hb.id)])
    assert hashlib.sha256(every).hexdigest() == report.sha256

    # Anything else is made again from what was released, and says what it holds.
    # With no letterhead or printer offset set, the print copy has the same words; it can be the
    # same bytes too, since the PDF engine renders the same input the same way.
    printed = _copy(lab, platform, report, "print")
    assert _flat(printed) == _flat(data) and _last_print(lab).output == "print"
    one = _flat(_copy(lab, platform, report, tests=[str(lipid.id)]))
    assert "Selected tests only: 1 of 2 on this report" in one and "Haemoglobin" not in one
    assert _last_print(lab).order_test_ids == [str(lipid.id)]
    hidden = _copy(lab, platform, report, reference="0", paper="A5")
    assert "Bio. ref. interval" not in _flat(hidden) and "Bio. ref. interval" in _flat(data)
    assert _last_print(lab).options == {"paper": "A5", "reference": False}
    assert len(lab.scalars(select(ReportPrint)).all()) == 5

    with pytest.raises(NotFoundError):
        delivery.make_copy(lab, platform.filestore, priya, report.id, "sideways", True)
    with pytest.raises(NotFoundError):
        b3desk = as_user(lab, platform, "b3desk")
        delivery.make_copy(lab, platform.filestore, b3desk, report.id, "digital", True)

    # Once the bill is paid no tick is needed, and nothing was due then.
    _settle(lab, platform, visit)
    delivery.make_copy(lab, platform.filestore, priya, report.id, "digital", False)
    assert _last_print(lab).dues_at_print == 0


@pytest.mark.item("M20")
def test_the_stored_copy_follows_the_reference_setting(lab: Session, platform: Platform) -> None:
    anil = as_user(lab, platform, "anil")
    lab_settings.set_value(lab, "report.reference_column", "hide", anil.user_id)
    visit = _day(lab, platform)

    report = _release(lab, platform, visit)

    assert report.content["stored"] == {"paper": "A4", "reference": False}
    _, data = read_file(lab, platform.filestore, report.file_id)
    assert "Bio. ref. interval" not in _flat(data)
    assert stored_options(report.content) == Options("A4", False)
    # A copy with nothing chosen is the stored one; reports from before were made with it.
    assert _copy(lab, platform, report) == data
    assert stored_options({}) == Options("A4", True)


@pytest.mark.item("M21")
def test_handing_over_records_who_and_reaches_the_timeline(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    report = _release(lab, platform, visit)
    priya = as_user(lab, platform, "priya")
    due = delivery.due_on(lab, visit.id)
    # Staff who never sign in can be named, here a home-collection phlebotomist.
    runner = _staff(lab, "staff1")
    assert runner in {u.id for u in delivery.staff(lab, visit.branch_id)}

    with pytest.raises(ValidationFailedError) as refused:
        delivery.deliver(
            lab, priya, report.id, delivery.DeliveryInput("  ", "fax", None, "x" * 301), False
        )
    assert set(refused.value.errors) == {"delivered_to", "mode", "staff_id", "note", "dues"}
    assert refused.value.errors["dues"] == delivery.DUES
    with pytest.raises(PermissionDeniedError):
        suresh = as_user(lab, platform, "suresh")
        data = delivery.DeliveryInput(RECEIVED_BY, "counter", suresh.user_id)
        delivery.deliver(lab, suresh, report.id, data, True)

    data = delivery.DeliveryInput(f"  {RECEIVED_BY} ", "home", runner, "Left at the door")
    handed = delivery.deliver(lab, priya, report.id, data, True)

    assert handed.delivered_to == RECEIVED_BY and handed.staff_id == runner
    assert handed.delivered_by == priya.user_id and handed.dues_at_delivery == due
    events = lab.scalars(select(OrderTestEvent).where(OrderTestEvent.event == "delivered")).all()
    tests = {_ordered(lab, visit, "lipid").id, _ordered(lab, visit, "hb").id}
    assert {e.order_test_id for e in events} == tests
    assert {e.note for e in events} == {f"Report {report.report_no} v1"}
    entry = lab.scalars(select(AuditLog).where(AuditLog.action == "report.deliver")).one()
    assert entry.detail == {
        "visit_id": str(visit.id),
        "version": 1,
        "mode": "home",
        "due": str(due),
    }
    assert RECEIVED_BY not in str(entry.detail)
    assert service.released(lab, priya) == []

    # A new version is handed over again; the old one can't be.
    _tsh(lab, platform, visit)
    second = _release(lab, platform, visit)
    assert [r.report_id for r in service.released(lab, priya)] == [second.id]
    with pytest.raises(ConflictError):
        delivery.deliver(lab, priya, report.id, data, True)
    screen = delivery.screen(lab, priya, report.id)
    assert screen.current == second and [line.what for line in screen.log] == ["home"]
    assert screen.log[0].by == lab.get_one(AppUser, runner).full_name


@pytest.mark.item("M21")
@pytest.mark.item("M20")
def test_the_report_screen(lab: Session, platform: Platform, db_client: TestClient) -> None:
    visit = _day(lab, platform)
    report = _release(lab, platform, visit)
    lab.commit()
    screen, pdf, deliver = (
        f"/reports/{report.id}",
        f"/reports/{report.id}/pdf",
        f"/reports/{report.id}/deliver",
    )

    sign_in(db_client, "priya")
    page = db_client.get("/reports")
    assert f'href="{screen}"' in page.text
    page = db_client.get(screen)
    assert page.status_code == 200
    assert "Hand over" in page.text and "Due ₹" in page.text and "Not handed over" in page.text
    refused = db_client.get(pdf)
    assert refused.status_code == 422 and delivery.DUES in refused.text
    copy = db_client.get(pdf, params={"dues": "yes"})
    assert copy.status_code == 200 and copy.headers["content-type"] == "application/pdf"
    name = f"report-{report.report_no.replace('/', '-')}-v1"
    assert copy.headers["content-disposition"] == f'inline; filename="{name}.pdf"'
    printed = db_client.get(pdf, params={"dues": "yes", "output": "print"})
    assert printed.headers["content-disposition"] == f'inline; filename="{name}-print.pdf"'
    assert db_client.get(pdf, params={"dues": "yes", "output": "fax"}).status_code == 404

    missing = post(db_client, deliver, {"mode": "counter"})
    assert missing.status_code == 422 and "Say who received the report." in missing.text
    assert lab.scalars(select(ReportDelivery)).all() == []
    me = str(as_user(lab, platform, "priya").user_id)
    done = post(
        db_client,
        deliver,
        {"delivered_to": RECEIVED_BY, "mode": "counter", "staff_id": me, "dues": "yes"},
    )
    assert done.status_code == 303
    page = db_client.get(screen).text
    assert "Handed over at the counter" in page and "PDF to send" in page and RECEIVED_BY in page
    assert report.report_no not in db_client.get("/reports").text

    sign_in(db_client, "suresh")
    assert "Record the hand-over" not in db_client.get(screen).text
    assert post(db_client, deliver, {"delivered_to": RECEIVED_BY}).status_code == 403
    assert "Report handed over" in db_client.get(f"/lab/visits/{visit.id}").text

    sign_in(db_client, "b3desk")
    assert db_client.get(screen).status_code == 404
    assert db_client.get(f"/reports/{uuid.uuid4()}").status_code == 404
