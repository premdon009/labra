"""The lab bench in a real browser: a panel typed with the keyboard, each value saved as the
cell is left, then signed off; and a test that an outside lab does, from sending to its PDF.

Needs Postgres and a Chromium installed with `uv run playwright install chromium`. Without
the browser the test is skipped with the reason "no browser for e2e tests".
"""

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from labra.core.registry import Platform
from labra.extlabs.models import ExternalLab
from labra.results.models import ExternalDocument, OrderTestEvent, Result
from labra.visits.models import OrderTest
from tests.e2e.conftest import sign_in
from tests.test_db_lab_entry import _approve, _in_lab, _param
from tests.test_uploads import SMALL_PDF

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


def _lipid_in_lab(
    engine: Engine, platform: Platform
) -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID]]:
    """A lipid panel received at the main lab: its id, its visit and its parameters by code."""
    with Session(engine) as db:
        _approve(db, platform, "lipid")
        test = _in_lab(db, platform)
        codes = ("TC", "TG", "HDL", "VLDL", "LDL", "NONHDL", "TC_HDL", "LDL_HDL")
        parameters = {code: _param(db, "lipid", code).id for code in codes}
        db.commit()
        return test.id, test.visit_id, parameters


@pytest.mark.e2e
@pytest.mark.item("M11")
@pytest.mark.item("M11.1")
@pytest.mark.item("M11.2")
def test_a_lipid_panel_typed_with_the_keyboard(
    page: "Page", committed_engine: Engine, platform: Platform
) -> None:
    from playwright.sync_api import expect

    test_id, visit_id, parameters = _lipid_in_lab(committed_engine, platform)

    def box(code: str) -> "Locator":
        return page.locator(f"#v-{test_id}-{parameters[code]}")

    def row(code: str) -> "Locator":
        return page.locator(f"#r-{test_id}-{parameters[code]}")

    keys = page.keyboard
    sign_in(page, "suresh")
    keys.press("Alt+w")
    page.wait_for_url("**/lab/worklist")
    page.get_by_role("link", name="Sunita Testcase").first.click()
    page.wait_for_url("**/lab/visits/*")

    # Three values, Enter after each; the rest of the panel is worked out by the server.
    box("TC").focus()
    keys.type("180")
    keys.press("Enter")
    expect(box("TG")).to_be_focused()
    keys.type("150")
    keys.press("Enter")
    expect(box("HDL")).to_be_focused()
    keys.type("45")
    keys.press("Enter")

    expect(row("TC")).to_have_class("result-row flag-normal")
    expect(box("VLDL")).to_have_text("30")
    expect(box("LDL")).to_have_text("105")
    expect(row("LDL")).to_have_class("result-row flag-high is-calculated")
    expect(row("LDL")).to_contain_text("↑ H")
    expect(box("TC_HDL")).to_have_text("4.0")

    # Shift+Enter goes back a row; Esc drops what was typed and nothing is sent.
    box("HDL").focus()
    keys.press("Shift+Enter")
    expect(box("TG")).to_be_focused()
    keys.type("9")
    keys.press("Escape")
    expect(box("TG")).to_have_value("150")

    # Past the limit of the formula, the rows built on it say so.
    box("TG").fill("450")
    keys.press("Enter")
    expect(row("LDL")).to_contain_text("Not calculable, measure directly")
    expect(box("LDL")).to_have_text("")
    box("TG").fill("150")
    keys.press("Enter")
    expect(box("LDL")).to_have_text("105")

    # A slip of the finger is refused, the cursor goes back to it, and a second look saves it.
    box("TC").fill("5")
    keys.press("Enter")
    expect(row("TC").get_by_role("alert")).to_be_visible()
    expect(box("TC")).to_be_focused()
    expect(box("TC")).to_have_value("5")
    expect(box("LDL")).to_have_text("105")
    box("TC").fill("185")
    keys.press("Enter")
    expect(box("LDL")).to_have_text("110")
    expect(row("TC").get_by_role("alert")).to_have_count(0)

    with Session(committed_engine) as db:
        saved = {
            code: db.scalars(
                select(Result.value_num).where(
                    Result.order_test_id == test_id, Result.parameter_id == parameters[code]
                )
            ).one()
            for code in ("TC", "TG", "HDL", "LDL")
        }
    assert saved == {"TC": 185, "TG": 150, "HDL": 45, "LDL": 110}

    # Off to the signatory, still without the mouse; only she gets the Verify button.
    foot = page.locator(f"#f-{test_id}")
    expect(page.get_by_role("button", name="Verify")).to_have_count(0)
    foot.get_by_role("button", name="Submit for verification").focus()
    keys.press("Enter")
    expect(foot).to_contain_text("Waiting for verification")
    expect(foot).to_contain_text("3 high")

    page.context.clear_cookies()
    sign_in(page, "meera")
    page.goto(f"/lab/visits/{visit_id}")
    expect(box("LDL")).to_have_text("110")
    foot.get_by_role("button", name="Verify").focus()
    keys.press("Enter")
    expect(foot).to_contain_text("Verified by Dr Meera Nair")
    expect(page.locator(f"#t-{test_id} input[type=text][id^='v-']")).to_have_count(0)
    with Session(committed_engine) as db:
        assert db.get_one(OrderTest, test_id).status == "verified"


@pytest.mark.e2e
@pytest.mark.item("M09")
@pytest.mark.item("M10")
@pytest.mark.item("M21")
def test_a_test_goes_to_an_outside_lab_and_comes_back_as_a_pdf(
    page: "Page", committed_engine: Engine, platform: Platform
) -> None:
    from playwright.sync_api import expect

    with Session(committed_engine) as db:
        test = _in_lab(db, platform, "vitd")
        test_id, visit_id = test.id, test.visit_id
        row_id = _param(db, "vitd", "VITD").id
        lab_id = db.scalars(
            select(ExternalLab.id).where(ExternalLab.name == "Demo Referral Lab B")
        ).one()
        db.commit()
    line = page.locator(f"#o-{test_id}")
    box = page.locator(f"#v-{test_id}-{row_id}")

    # The cheaper of the two labs, picked from the list that shows cost and margin.
    sign_in(page, "suresh")
    page.get_by_role("link", name="Outsourcing").click()
    page.wait_for_url("**/lab/outsourcing")
    choice = line.get_by_label("Done at")
    expect(choice.locator(f"option[value='lab:{lab_id}']")).to_have_text(
        "Demo Referral Lab B: cost ₹620.00, margin ₹580.00, 72 h"
    )
    choice.select_option(f"lab:{lab_id}")
    line.get_by_role("button", name="Move the test").click()

    # The sheet for the bag has the patient's name and the lab's own code, no phone.
    page.get_by_role("link", name="Demo Referral Lab B").click()
    expect(page.locator(".sheet")).to_contain_text("Sunita Testcase")
    expect(page.locator(".sheet")).to_contain_text("D-TOTAL")
    expect(page.locator(".sheet")).not_to_contain_text("90000")
    page.get_by_role("link", name="Back to outsourcing").click()

    line.get_by_label("Their number (optional)").fill("RL-2291")
    line.get_by_role("button", name="Mark sent").click()
    expect(line.get_by_label("Their number")).to_have_value("RL-2291")
    line.get_by_role("link", name="Attach the result").click()
    page.wait_for_url(f"**/lab/visits/{visit_id}#outside")

    # While the sample is away the row takes no value.
    expect(page.locator(f"input[id='v-{test_id}-{row_id}']")).to_have_count(0)
    scan = {"name": "scan from the lab.pdf", "mimeType": "application/pdf", "buffer": SMALL_PDF}
    page.get_by_label("Result PDF").set_input_files(scan)  # type: ignore[arg-type]
    page.get_by_role("button", name="Attach the PDF").click()
    with page.expect_download() as fetched:
        page.get_by_role("link", name="Result PDF").click()
    assert fetched.value.suggested_filename.startswith("external-result-")
    assert fetched.value.suggested_filename.endswith(".pdf")

    box.fill("32.5")
    page.keyboard.press("Enter")
    expect(box).to_have_value("32.5")

    steps = page.locator(f"#t-{test_id} details.timeline")
    steps.locator("summary").click()
    expect(steps.locator("li")).to_contain_text(
        [
            "Registered",
            "Sample collected",
            "Received in the lab",
            "Routed",
            "Sent to the outside lab",
            "Result received",
        ]
    )
    expect(steps).to_contain_text("To Demo Referral Lab B, their number RL-2291")
    expect(steps).to_contain_text("Suresh Iyer")

    foot = page.locator(f"#f-{test_id}")
    foot.get_by_role("button", name="Submit for verification").click()
    expect(foot).to_contain_text("Waiting for verification")
    page.context.clear_cookies()
    sign_in(page, "meera")
    page.goto(f"/lab/visits/{visit_id}")
    foot.get_by_role("button", name="Verify").click()
    expect(foot).to_contain_text("Verified by Dr Meera Nair")

    with Session(committed_engine) as db:
        ordered = db.get_one(OrderTest, test_id)
        assert (ordered.status, ordered.external_accession_no) == ("verified", "RL-2291")
        assert str(ordered.external_cost) == "620.00"
        typed = db.scalars(select(Result).where(Result.order_test_id == test_id)).one()
        assert (float(typed.value_num or 0), typed.source) == (32.5, "external_pdf")
        assert db.scalars(select(ExternalDocument.visit_id)).one() == visit_id
        events = db.scalars(
            select(OrderTestEvent.event)
            .where(OrderTestEvent.order_test_id == test_id)
            .order_by(OrderTestEvent.at, OrderTestEvent.id)
        ).all()
    assert events == ["received", "routed", "sent", "received_back", "resulted", "verified"]
