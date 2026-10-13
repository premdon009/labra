"""The front desk in a real browser, keys only: what the markup tests can't prove.

Needs Postgres and a Chromium installed with `uv run playwright install chromium`. Without
the browser the test is skipped with the reason "no browser for e2e tests", and
`scripts/ci_local.sh` reports the test stage as WARN (unchecked).
"""

import re
import socket
import threading
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from labra.core.config import get_settings
from labra.core.db import get_session
from labra.core.registry import Platform
from labra.org.models import AppUser
from labra.seed import DEMO_PASSWORD, seed
from labra.visits.models import Sample
from tests.conftest import SEED_DAY

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

NO_BROWSER = "no browser for e2e tests"
UTR = "426112345678"
# A common counter laptop: 1366x768 with the browser's own bars taken off.
VIEWPORT = {"width": 1366, "height": 657}
# The print window can't be driven, so it is only counted.
COUNT_PRINTS = "window.print = function () { window.printed = (window.printed || 0) + 1; };"


@pytest.fixture
def live_url(
    app: FastAPI,
    committed_engine: Engine,
    platform: Platform,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    """The app on a local port over plain HTTP, on a database of its own with the demo data."""
    monkeypatch.setenv("LABRA_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    with Session(committed_engine) as setup:
        seed(setup, platform.identity, SEED_DAY, with_catalog=True, with_people=True)
        setup.commit()
    sessions = sessionmaker(committed_engine)

    def session() -> Iterator[Session]:
        with sessions() as db:
            yield db

    app.dependency_overrides[get_session] = session
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=20)
        app.dependency_overrides.clear()


@pytest.fixture
def page(live_url: str) -> Iterator["Page"]:
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as tools:
        try:
            browser = tools.chromium.launch()
        except Error:
            pytest.skip(NO_BROWSER)
        context = browser.new_context(viewport=VIEWPORT, base_url=live_url)  # type: ignore[arg-type]
        context.add_init_script(COUNT_PRINTS)
        context.set_default_timeout(10_000)
        yield context.new_page()
        browser.close()


@pytest.mark.e2e
@pytest.mark.item("M18")
@pytest.mark.item("M08")
@pytest.mark.item("EC-J01")
@pytest.mark.item("EC-J02")
@pytest.mark.item("EC-J03")
def test_front_desk_day_with_keys_only(page: "Page", committed_engine: Engine) -> None:
    from playwright.sync_api import expect

    keys = page.keyboard

    page.goto("/login")
    page.fill("[name=username]", "priya")
    page.fill("[name=password]", DEMO_PASSWORD)
    keys.press("Enter")
    page.wait_for_url("**/")

    # Alt+D is the browser's address-bar key and Alt+F its menu key; here they reach the page.
    keys.press("Alt+KeyD")
    page.wait_for_url("**/frontdesk/dues")
    keys.press("Alt+KeyF")
    page.wait_for_url("**/frontdesk/patients")
    keys.press("Alt+KeyN")
    page.wait_for_url("**/frontdesk/visits/new")

    # A new patient: the phone box has the focus, and Enter there looks the number up.
    expect(page.locator("#f-phone")).to_be_focused()
    keys.type("9000000050")
    keys.press("Enter")
    expect(page.locator("#patient-match")).to_contain_text("No patient here has this number")
    assert page.url.endswith("/frontdesk/visits/new")
    page.locator("#f-full_name").focus()
    keys.type("Sunita Testcase")
    keys.press("Tab")
    keys.type("F")
    page.locator("#f-age_years").focus()
    keys.type("34")

    # The search shows that it is working while the server is asked.
    def slowly(route: "Route") -> None:
        time.sleep(0.6)
        route.continue_()

    page.route("**/frontdesk/visits/new/tests*", slowly)
    busy = page.locator("#code-busy")
    expect(busy).to_be_hidden()
    box = page.locator("#f-q")
    box.focus()
    keys.type("sf")
    expect(busy).to_be_visible()
    expect(page.locator("#code-match")).to_contain_text("fbs · Glucose, fasting")
    expect(busy).to_be_hidden()
    page.unroute("**/frontdesk/visits/new/tests*")

    # Enter adds the typed code, empties the box and keeps the focus there for the next one.
    lines = page.locator("#visit-order .visit-lines tbody tr")
    keys.press("Enter")
    expect(lines.first).to_contain_text("Glucose, fasting")
    for count, code in enumerate(("lipid", "urm", "vitd"), start=2):
        expect(box).to_have_value("")
        expect(box).to_be_focused()
        keys.type(code)
        keys.press("Enter")
        expect(lines).to_have_count(count)
    expect(lines.nth(3)).to_contain_text("outsourced ★")
    assert page.url.endswith("/frontdesk/visits/new")

    page.locator("#f-discount_value").focus()
    keys.type("10")
    keys.press("Tab")
    keys.type("P")  # Per cent
    keys.press("Tab")
    keys.type("Senior citizen")
    expect(page.locator("#visit-net")).to_have_text("₹1,737.00")
    page.locator("#f-pay_mode").focus()
    keys.type("U")  # UPI
    expect(page.locator("#f-pay_mode")).to_have_value("upi")
    keys.press("Tab")
    keys.type("1000")
    keys.press("Tab")
    keys.type(UTR)
    page.locator("[name=consent]").focus()
    keys.press("Space")

    # With four tests ordered, Save is still on screen and nothing scrolls sideways.
    save = page.locator("#visit-save").bounding_box()
    assert save is not None and save["y"] + save["height"] <= VIEWPORT["height"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    # Save prints the bill, then the labels, then shows the visit.
    keys.press("Alt+KeyS")
    page.wait_for_url(re.compile(r"/frontdesk/bills/[^/]+/print\?auto=1&then=labels$"))
    expect(page.locator("body")).to_have_attribute("data-autoprint", "")
    expect(page.locator(".sheet")).to_contain_text("₹1,737.00")
    assert page.evaluate("window.printed") == 1
    page.evaluate("window.dispatchEvent(new Event('afterprint'))")
    page.wait_for_url(re.compile(r"/frontdesk/visits/[^/]+/labels\?print=1$"))
    expect(page.locator("section.label")).to_have_count(3)
    expect(page.locator("section.label svg rect").first).to_be_attached()
    assert page.evaluate("window.printed") == 1
    page.evaluate("window.dispatchEvent(new Event('afterprint'))")
    page.wait_for_url(re.compile(r"/frontdesk/visits/[^/?]+$"))
    expect(page.locator("#bill-due")).to_have_text("₹737.00")

    # A scanner types the number and sends Enter.
    with Session(committed_engine) as db:
        sample_no = db.scalars(select(Sample.sample_no).order_by(Sample.sample_no)).first()
        walker = db.scalars(select(AppUser).where(AppUser.username == "staff1")).one()
    assert sample_no is not None
    page.goto("/frontdesk/collect")
    page.select_option("#f-collected_by", str(walker.id))
    expect(page.locator("#f-sample_no")).to_be_focused()
    keys.type(sample_no)
    keys.press("Enter")
    expect(page.locator("[role=status]").first).to_contain_text(f"Collected: {sample_no}")
    expect(page.locator("#f-sample_no")).to_be_focused()
    expect(page.locator("#f-sample_no")).to_have_value("")
    expect(page.locator("#f-collected_by")).to_have_value(str(walker.id))
    with Session(committed_engine) as db:
        collected = db.scalars(select(Sample).where(Sample.sample_no == sample_no)).one()
        assert (collected.status, collected.collected_by) == ("collected", walker.id)
