"""The lab bench in a real browser: a panel typed with the keyboard, each value saved as the
cell is left.

Needs Postgres and a Chromium installed with `uv run playwright install chromium`. Without
the browser the test is skipped with the reason "no browser for e2e tests".
"""

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from labra.core.registry import Platform
from labra.results.models import Result
from tests.e2e.conftest import sign_in
from tests.test_db_lab_entry import _approve, _in_lab, _param

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


def _lipid_in_lab(engine: Engine, platform: Platform) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """A lipid panel received at the main lab: its id and its parameters by code."""
    with Session(engine) as db:
        _approve(db, platform, "lipid")
        test = _in_lab(db, platform)
        codes = ("TC", "TG", "HDL", "VLDL", "LDL", "NONHDL", "TC_HDL", "LDL_HDL")
        parameters = {code: _param(db, "lipid", code).id for code in codes}
        db.commit()
        return test.id, parameters


@pytest.mark.e2e
@pytest.mark.item("M11")
@pytest.mark.item("M11.1")
@pytest.mark.item("M11.2")
def test_a_lipid_panel_typed_with_the_keyboard(
    page: "Page", committed_engine: Engine, platform: Platform
) -> None:
    from playwright.sync_api import expect

    test_id, parameters = _lipid_in_lab(committed_engine, platform)

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
