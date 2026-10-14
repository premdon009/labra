"""The browser rules the app sets itself (design §19.3): a Content-Security-Policy with no
inline code and no eval, so htmx and Alpine run only their CSP-safe paths, and the same
headers on every kind of response, including the public check page and the PDFs."""

import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import labra
from labra.core.registry import Platform
from labra.web.middleware import SECURITY_HEADERS
from tests import test_db_report_content as content
from tests.frontdesk import sign_in
from tests.test_db_report_content import _day
from tests.test_db_report_release import _release
from tests.test_db_visits_web import _full_bill

lab = content.lab

APP_DIR = Path(labra.__file__).resolve().parent
TEMPLATES = APP_DIR / "templates"
OWN_SCRIPTS = sorted((APP_DIR / "static").glob("*.js"))

# What would need inline code or eval in the browser, which the policy refuses: htmx 4
# evaluates hx-on handlers, js: values and [filters] in triggers with new Function().
NEEDS_UNSAFE = {
    "inline script": re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE),
    "style block": re.compile(r"<style\b", re.IGNORECASE),
    "style attribute": re.compile(r"\sstyle\s*=", re.IGNORECASE),
    "event handler attribute": re.compile(r"\son[a-z]+\s*=", re.IGNORECASE),
    "htmx handler": re.compile(r"\s(data-)?hx-on", re.IGNORECASE),
    "script URL or js: value": re.compile(r"(javascript|js):", re.IGNORECASE),
    "htmx trigger filter": re.compile(r"hx-trigger\s*=\s*[\"'][^\"']*\["),
}


def _assert_headers(response_headers: Mapping[str, str], what: str) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert response_headers[name] == value, (what, name)


@pytest.mark.item("EC-A06")
def test_the_policy_allows_no_inline_code_and_no_eval() -> None:
    policy = dict(
        part.strip().split(" ", 1)
        for part in SECURITY_HEADERS["content-security-policy"].split(";")
    )
    assert policy["script-src"] == "'self'" and policy["style-src"] == "'self'"
    assert policy["default-src"] == "'self'" and policy["object-src"] == "'none'"
    assert policy["frame-ancestors"] == "'none'"
    assert "unsafe" not in SECURITY_HEADERS["content-security-policy"]


@pytest.mark.item("EC-A06")
def test_no_template_or_script_needs_inline_code_or_eval() -> None:
    found = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        found += [(path.name, why) for why, rule in NEEDS_UNSAFE.items() if rule.search(text)]
    for path in OWN_SCRIPTS:
        text = path.read_text(encoding="utf-8")
        if re.search(r"\beval\(|new Function\(|setTimeout\(\s*[\"']", text):
            found.append((path.name, "eval"))
    assert found == []
    assert len(OWN_SCRIPTS) >= 2 and len(list(TEMPLATES.rglob("*.html"))) > 50


@pytest.mark.item("EC-A06")
def test_the_rules_catch_what_they_are_for() -> None:
    samples = {
        "inline script": "<script>alert(1)</script>",
        "style block": "<style>p{}</style>",
        "style attribute": '<p style="color:red">',
        "event handler attribute": '<button onclick="go()">',
        "htmx handler": '<div hx-on:click="go()">',
        "script URL or js: value": '<a href="javascript:go()">',
        "htmx trigger filter": "<input hx-trigger=\"keyup[key=='Enter']\">",
    }
    for why, sample in samples.items():
        assert NEEDS_UNSAFE[why].search(sample), why
    assert not any(
        r.search('<script src="/static/x.js" defer></script>') for r in NEEDS_UNSAFE.values()
    )


@pytest.mark.item("EC-A06")
def test_the_headers_are_on_the_report_and_owner_responses(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _day(lab, platform)
    report = _release(lab, platform, visit)
    lab.commit()

    public = db_client.get(f"/v/{report.verify_token}")
    assert public.status_code == 200
    _assert_headers(public.headers, "public check page")
    _assert_headers(db_client.get("/v/" + "A" * 22).headers, "unknown token")

    sign_in(db_client, "priya")
    pdf = db_client.get(f"/reports/{report.id}/pdf", params={"dues": "yes"})
    assert pdf.headers["content-type"] == "application/pdf"
    _assert_headers(pdf.headers, "report PDF")
    assert pdf.headers["cache-control"] == "no-store"
    _assert_headers(db_client.get(f"/reports/{report.id}").headers, "report screen")
    _assert_headers(db_client.get("/owner/daily").headers, "owner refused")

    sign_in(db_client, "anil")
    for path in ("/owner/daily", "/owner/dues", "/owner/pending", "/owner/outsourcing"):
        page = db_client.get(path)
        assert page.status_code == 200, path
        _assert_headers(page.headers, path)
        assert page.headers["cache-control"] == "no-store"


@pytest.mark.item("EC-A06")
def test_the_headers_are_on_the_bill_pdf(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    bill = _full_bill(seeded, platform, db_client)
    pdf = db_client.get(f"/frontdesk/bills/{bill.id}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    _assert_headers(pdf.headers, "bill PDF")
