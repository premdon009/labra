"""The web shell without a database: health, metrics, errors, headers, guards and CSRF."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

from labra.auth.deps import PUBLIC_PATHS
from labra.auth.routes import safe_next
from labra.core.config import Settings
from labra.core.db import get_session
from labra.core.metrics import scrape_allowed
from labra.core.registry import Platform
from labra.web.middleware import SECURITY_HEADERS


@pytest.mark.item("W16")
def test_healthz_needs_no_database(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


class _DeadSession:
    def execute(self, *_args: object) -> None:
        raise OperationalError("select 1", {}, Exception("connection refused"))

    def close(self) -> None:
        pass


@pytest.mark.item("W16")
def test_readyz_503_without_database(app: FastAPI) -> None:
    app.dependency_overrides[get_session] = lambda: _DeadSession()
    with TestClient(app, base_url="https://testserver") as c:
        r = c.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "error"
    assert body["checks"]["database"] == "unreachable"
    assert body["checks"]["migrations"] == "unknown"


@pytest.mark.item("W16")
def test_metrics_hidden_without_token_from_outside(client: TestClient) -> None:
    # TestClient's peer address is not an IP, so it counts as outside.
    assert client.get("/metrics").status_code == 404


@pytest.mark.item("W16")
def test_metrics_with_token(monkeypatch: pytest.MonkeyPatch, platform: Platform) -> None:
    monkeypatch.setenv("LABRA_METRICS_TOKEN", "scrape-secret")
    from labra.app import create_app

    with TestClient(create_app(), base_url="https://testserver") as c:
        c.get("/healthz")
        assert c.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 404
        r = c.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})
    assert r.status_code == 200
    assert "labra_http_requests_total" in r.text
    # Labels are route templates and status codes, never raw paths or identifiers.
    assert 'route="/healthz"' in r.text


@pytest.mark.item("W16")
@pytest.mark.parametrize(
    ("ip", "token", "auth", "allowed"),
    [
        ("10.1.2.3", None, None, True),
        ("192.168.1.20", None, None, True),
        ("203.0.113.5", None, None, False),
        ("not-an-ip", None, None, False),
        (None, None, None, False),
        ("10.1.2.3", "t0ken", None, False),
        ("203.0.113.5", "t0ken", "Bearer t0ken", True),
    ],
)
def test_scrape_allowed(ip: str | None, token: str | None, auth: str | None, allowed: bool) -> None:
    settings = Settings(metrics_token=SecretStr(token) if token else None)
    assert scrape_allowed(settings, ip, auth) is allowed


@pytest.mark.item("W16")
def test_metrics_off(monkeypatch: pytest.MonkeyPatch, platform: Platform) -> None:
    monkeypatch.setenv("LABRA_METRICS", "off")
    from labra.app import create_app

    paths = {r.path for r in api_routes(create_app())}
    assert "/healthz" in paths
    assert "/metrics" not in paths


@pytest.mark.item("EC-E03")
def test_unexpected_error_gives_reference(app: FastAPI, platform: Platform) -> None:
    def boom() -> None:
        raise RuntimeError("synthetic failure")

    app.add_api_route("/boom", boom)
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as c:
        r = c.get("/boom", headers={"X-Request-ID": "req-abc123"})
    assert r.status_code == 500
    ref = r.json()["reference"]
    assert ref.startswith("E-")
    assert "synthetic failure" not in r.text
    assert r.headers["x-request-id"] == "req-abc123"
    assert r.headers["x-content-type-options"] == "nosniff"
    reports: Any = platform.errors
    assert reports.reports[0][0] == ref
    assert reports.reports[0][2]["request_id"] == "req-abc123"


@pytest.mark.item("W04")
def test_bad_request_id_replaced(client: TestClient) -> None:
    r = client.get("/healthz", headers={"X-Request-ID": "bad id\nwith newline"})
    assert r.headers["x-request-id"] != "bad id\nwith newline"
    assert len(r.headers["x-request-id"]) == 32


@pytest.mark.item("EC-A06")
def test_security_headers_on_every_response(client: TestClient) -> None:
    r = client.get("/login")
    for name, value in SECURITY_HEADERS.items():
        assert r.headers[name] == value
    assert r.headers["cache-control"] == "no-store"
    assert "unsafe-inline" not in r.headers["content-security-policy"]


@pytest.mark.item("EC-A04")
def test_login_page_sets_csrf_cookie(client: TestClient) -> None:
    r = client.get("/login")
    assert r.status_code == 200
    assert "__Host-labra_csrf" in r.cookies or any(
        c.startswith("__Host-") for c in r.headers.get_list("set-cookie")
    )
    assert 'name="csrf_token"' in r.text


@pytest.mark.item("EC-A05")
def test_anonymous_page_redirects_to_login(client: TestClient) -> None:
    r = client.get("/admin/branches?x=1", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=%2Fadmin%2Fbranches%3Fx%3D1"


@pytest.mark.item("EC-A05")
def test_anonymous_htmx_gets_hx_redirect(client: TestClient) -> None:
    r = client.get("/admin/users", headers={"HX-Request": "true"})
    assert r.status_code == 204
    assert r.headers["hx-redirect"].startswith("/login?next=")


@pytest.mark.item("EC-A04")
def test_post_without_csrf_token_refused(client: TestClient) -> None:
    r = client.post("/login", data={"username": "anil", "password": "demo-password-1"})
    assert r.status_code == 403


@pytest.mark.item("EC-A04")
def test_post_with_wrong_csrf_header_refused(client: TestClient) -> None:
    client.get("/login")
    r = client.post("/logout", headers={"X-CSRF-Token": "not-the-token"})
    assert r.status_code == 403


@pytest.mark.item("M01")
@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/admin/users", "/admin/users"),
        (None, "/"),
        ("", "/"),
        ("https://evil.example/", "/"),
        ("//evil.example/", "/"),
        ("/\\evil.example", "/"),
        ("admin", "/"),
    ],
)
def test_safe_next(target: str | None, expected: str) -> None:
    assert safe_next(target) == expected


def api_routes(app: FastAPI) -> list[RouteContext]:
    """Every endpoint, including those in included routers (which FastAPI nests)."""
    return [c for c in iter_route_contexts(app.routes) if isinstance(c.original_route, APIRoute)]


def _guards(route: RouteContext) -> set[str]:
    found = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        guard = getattr(dep.call, "__guard__", None)
        if guard:
            found.add(guard)
        stack.extend(dep.dependencies)
    return found


@pytest.mark.item("EC-A05")
def test_every_route_is_guarded_or_public(app: FastAPI) -> None:
    routes = api_routes(app)
    assert len(routes) > 10
    unguarded = [r.path for r in routes if r.path not in PUBLIC_PATHS and not _guards(r)]
    assert unguarded == []


@pytest.mark.item("EC-A05")
def test_admin_routes_need_a_permission(app: FastAPI) -> None:
    for r in api_routes(app):
        if (r.path or "").startswith("/admin"):
            assert _guards(r) - {"signed_in"}, r.path


MACHINE_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


@pytest.mark.item("M25.1")
def test_every_html_page_names_its_manual_page(app: FastAPI) -> None:
    pages = [r for r in api_routes(app) if "GET" in (r.methods or set())]
    assert len(pages) > 5
    missing = [
        r.path
        for r in pages
        if r.path not in MACHINE_PATHS and not getattr(r.endpoint, "__manual_page__", None)
    ]
    assert missing == []
