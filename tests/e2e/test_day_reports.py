"""The end of the day in a real browser: the signatory releases the report, the front desk
prints it and hands it over with money still due, and the owner checks the day's figures.

Needs Postgres and a Chromium installed with `uv run playwright install chromium`. Without
the browser the test is skipped with the reason "no browser for e2e tests".
"""

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from labra.billing.models import Bill
from labra.core.registry import Platform
from labra.reports.models import Report, ReportDelivery, ReportPrint
from labra.results.models import OrderTestEvent
from labra.visits.models import OrderTest
from tests.e2e.conftest import sign_in
from tests.test_db_report_content import _day, _ready

if TYPE_CHECKING:
    from playwright.sync_api import Page, Response

RECEIVED_BY = "Synthetic Relative"


@pytest.mark.e2e
@pytest.mark.item("M12")
@pytest.mark.item("M21")
@pytest.mark.item("M13")
@pytest.mark.item("EC-H03")
def test_release_print_hand_over_and_the_owners_evening_check(
    page: "Page", committed_engine: Engine, platform: Platform
) -> None:
    from playwright.sync_api import expect

    # Lipid and haemoglobin signed off at Branch 2, TSH still in the lab, nothing paid.
    with Session(committed_engine) as db:
        _ready(db, platform)
        visit = _day(db, platform)
        visit_id, visit_no = visit.id, visit.visit_no
        net = db.scalars(select(Bill.net).where(Bill.visit_id == visit_id)).one()
        db.commit()
    due = f"₹{net:,.2f}"

    # The signatory releases what is ready; the report is partial while TSH is pending.
    sign_in(page, "meera")
    page.goto("/reports")
    page.get_by_role("row", name=visit_no).get_by_role("link", name="Release").click()
    page.wait_for_url(f"**/reports/visits/{visit_id}")
    release = page.get_by_role("button", name="Release")
    expect(page.get_by_role("heading", name="Pending")).to_be_visible()
    release.click()
    expect(page.locator(".field-error")).to_be_visible()
    page.get_by_label("as a partial report").check()
    page.get_by_role("button", name="Release").click()
    versions = page.get_by_role("region", name="Released versions")
    expect(versions).to_contain_text("v1")
    expect(versions).to_contain_text("Partial")
    expect(versions).to_contain_text("Current")

    # The front desk finds it waiting to be handed over; the bill is unpaid, so a tick first.
    page.context.clear_cookies()
    sign_in(page, "priya")
    page.goto("/reports")
    page.get_by_role("row", name=visit_no).get_by_role("link", name="Print or hand over").click()
    expect(page.get_by_role("alert").first).to_contain_text(f"Due {due} on the bill")

    def pdf(response: "Response") -> bool:
        return "/pdf" in response.url and response.request.method == "GET"

    copy = page.get_by_role("form", name="Download or print")
    copy.get_by_label("Go ahead although").check()
    with page.context.expect_event("response", pdf) as printed:
        copy.get_by_role("button", name="PDF to print").click()
    assert printed.value.status == 200
    assert printed.value.headers["content-type"] == "application/pdf"

    handover = page.get_by_role("form", name="Hand over")
    handover.get_by_label("Received by").fill(RECEIVED_BY)
    handover.get_by_label("How").select_option("counter")
    handover.get_by_role("button", name="Record the hand-over").click()
    expect(page.get_by_role("form", name="Hand over")).to_contain_text("Tick the box")
    page.get_by_role("form", name="Hand over").get_by_label("Hand over although").check()
    page.get_by_role("form", name="Hand over").get_by_role(
        "button", name="Record the hand-over"
    ).click()
    log = page.get_by_role("region", name="Hand-overs and copies")
    expect(log).to_contain_text("Handed over at the counter")
    expect(log).to_contain_text("PDF to print")
    expect(log).to_contain_text(RECEIVED_BY)
    page.goto("/reports")
    expect(page.get_by_role("row", name=visit_no)).to_have_count(0)

    with Session(committed_engine) as db:
        report = db.scalars(select(Report).where(Report.visit_id == visit_id)).one()
        assert report.is_partial and report.status == "released"
        handed = db.scalars(select(ReportDelivery).where(ReportDelivery.report_id == report.id))
        assert [(d.delivered_to, d.dues_at_delivery) for d in handed] == [(RECEIVED_BY, net)]
        assert db.scalars(select(ReportPrint.output)).all() == ["print"]
        tests = select(OrderTest.id).where(OrderTest.visit_id == visit_id)
        events = db.scalars(
            select(OrderTestEvent.event).where(OrderTestEvent.order_test_id.in_(tests))
        ).all()
        assert events.count("released") == 2 and events.count("delivered") == 2

    # In the evening the owner sees the bill still owed and TSH still pending. (The helper
    # dates the visit to the seed day, but its bill was issued today, so today owes it.)
    page.context.clear_cookies()
    sign_in(page, "anil")
    page.get_by_role("link", name="Owner figures").click()
    page.wait_for_url("**/owner/daily")
    bills = page.get_by_role("region", name="Bills")
    expect(bills.get_by_role("row", name="Owed at the end of the day")).to_contain_text(
        f"1 bill · {due}"
    )
    page.get_by_role("link", name="Pending tests").click()
    expect(page.get_by_role("main")).to_contain_text(visit_no)
