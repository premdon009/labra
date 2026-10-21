"""The user manual inside the app: each screen's help page, the contents and the PDF."""

import re
import tomllib
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from markupsafe import escape
from pypdf import PdfReader

from labra import __version__
from labra.help import service

ROOT = Path(__file__).resolve().parent.parent


def _screens(app: FastAPI) -> set[str]:
    return {
        getattr(c.endpoint, "__manual_page__", None) or ""
        for c in iter_route_contexts(app.routes)
        if isinstance(c.original_route, APIRoute)
    } - {""}


@pytest.mark.item("M25.3")
def test_every_screen_has_its_help_page_in_the_app(app: FastAPI, client: TestClient) -> None:
    screens = _screens(app)
    assert len(screens) > 20
    for name in sorted(screens):
        response = client.get(f"/manual/{name}/")
        assert response.status_code == 200, name
        assert "<h1" in response.text, name
        # Signed out, the page gets the wide column, not the narrow sign-in one.
        assert 'class="app-alone app-alone-wide"' in response.text, name


@pytest.mark.item("M25.3")
def test_every_link_between_manual_pages_opens(client: TestClient) -> None:
    targets = set()
    for page in service.pages().values():
        for href in re.findall(r'href="(/manual/[^"#]*)', page.html):
            targets.add(href)
        assert not re.search(r'href="[^"#:]*\.md', page.html), page.name
    assert targets
    for href in sorted(targets):
        assert client.get(href).status_code == 200, href


@pytest.mark.item("M25.3")
@pytest.mark.item("M25.4")
def test_links_resolve_to_the_app_or_the_documentation_site() -> None:
    link = service._link
    # Between the manual and the runbooks: inside the app.
    assert link("manual/admin/system.md", "../../runbooks/restore-from-backup.md", "#x") == (
        "/manual/runbooks/restore-from-backup/#x"
    )
    assert link("manual/admin/system.md", "../lab/worklist.md", "") == "/manual/lab/worklist/"
    assert link("manual/admin/system.md", "alerts-and-checks.md", "") == (
        "/manual/admin/alerts-and-checks/"
    )
    assert link("runbooks/disk-full.md", "../manual/admin/system.md", "") == "/manual/admin/system/"
    assert (
        link("runbooks/disk-full.md", "laptop-dead.md", "#a") == "/manual/runbooks/laptop-dead/#a"
    )
    # Anything else the app doesn't carry: the documentation site.
    assert link("runbooks/disk-full.md", "../install/laptop.md", "#4-docker") == (
        "https://premdon009.github.io/labra/install/laptop/#4-docker"
    )
    assert link("manual/admin/system.md", "../../ENTERPRISE_CHECKLIST.md", "") == (
        "https://premdon009.github.io/labra/ENTERPRISE_CHECKLIST/"
    )


def _runbooks() -> list[str]:
    nav = tomllib.loads((ROOT / "zensical.toml").read_text())["project"]["nav"]
    paths = next(entry["Runbooks"] for entry in nav if "Runbooks" in entry)
    return [p.removesuffix(".md") for p in paths]


@pytest.mark.item("M25.4")
def test_every_runbook_opens_inside_the_app(client: TestClient) -> None:
    runbooks = _runbooks()
    assert len(runbooks) >= 6
    assert {p.name for p in service.pages().values() if p.section == "Runbooks"} == set(runbooks)
    for name in runbooks:
        response = client.get(f"/manual/{name}/")
        assert response.status_code == 200, name
        assert "<h1" in response.text, name
    restore = service.pages()["runbooks/restore-from-backup"]
    assert restore.title == "Restore from backup"
    assert 'href="/manual/admin/backups-and-restore/"' in restore.html


@pytest.mark.item("M25.4")
def test_the_contents_lists_the_runbooks(client: TestClient) -> None:
    html = client.get("/manual/").text
    assert "<h2>Runbooks</h2>" in html
    for name in _runbooks():
        assert f'href="/manual/{name}/"' in html, name


@pytest.mark.item("M25.3")
def test_the_contents_lists_every_page_in_the_site_order(client: TestClient) -> None:
    html = client.get("/manual/").text
    titles = [p.title for p in service.pages().values()]
    positions = [html.index(f">{escape(t)}</a>") for t in titles]
    assert positions == sorted(positions)
    assert 'href="/manual/labra-manual.pdf"' in html


@pytest.mark.item("M25.3")
@pytest.mark.parametrize("name", ["nowhere", "../../pyproject", "admin/../../README", "_template"])
def test_only_manual_pages_are_served(client: TestClient, name: str) -> None:
    assert client.get(f"/manual/{name}/").status_code == 404


@pytest.mark.item("M25.3")
def test_the_help_button_and_alt_h_open_this_screens_page_inside_the_app(
    client: TestClient,
) -> None:
    html = client.get("/login").text
    assert re.search(
        r'<a [^>]*href="/manual/getting-started/login/"[^>]*data-shortcut="alt\+h"', html
    )


@pytest.mark.item("M25.3")
def test_the_manual_pdf_holds_every_page_and_fetches_nothing(client: TestClient) -> None:
    service.manual_pdf.cache_clear()
    response = client.get("/manual/labra-manual.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    text = " ".join(p.extract_text() or "" for p in PdfReader(BytesIO(response.content)).pages)
    text = re.sub(r"\s+", " ", text)
    assert __version__ in text
    for page in service.pages().values():
        assert page.title in text, page.title
    assert "Restore from backup" in text
