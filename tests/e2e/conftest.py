"""A real browser against the app on a local port, on a database of its own."""

import socket
import threading
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from labra.core.config import get_settings
from labra.core.db import get_session
from labra.core.registry import Platform
from labra.seed import DEMO_PASSWORD, seed
from tests.conftest import SEED_DAY

if TYPE_CHECKING:
    from playwright.sync_api import Page

NO_BROWSER = "no browser for e2e tests"
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


def sign_in(page: "Page", username: str = "priya") -> None:
    page.goto("/login")
    page.fill("[name=username]", username)
    page.fill("[name=password]", DEMO_PASSWORD)
    page.keyboard.press("Enter")
    page.wait_for_url("**/")
