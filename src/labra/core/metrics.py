"""Prometheus metrics at `/metrics` (ADR-0008). Any scraper that speaks the Prometheus text
format can read them: Prometheus itself, Grafana Alloy, VictoriaMetrics, an OTel collector.

Labels are the route template, method and status only, never a URL or anything a patient
typed, so the series count stays small and no personal data reaches the monitor.
"""

import hmac
import ipaddress
import time

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram
from prometheus_client.exposition import generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from labra.core.config import Settings, get_settings
from labra.core.errors import NotFoundError

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "labra_http_requests_total",
    "HTTP requests handled.",
    ["route", "method", "status"],
    registry=REGISTRY,
)
HTTP_SECONDS = Histogram(
    "labra_http_request_duration_seconds",
    "Time to handle an HTTP request.",
    ["route", "method"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=REGISTRY,
)
JOB_RUNS = Counter(
    "labra_job_runs_total",
    "Background job runs (backups, verifies), by outcome.",
    ["job", "ok"],
    registry=REGISTRY,
)
ERRORS = Counter(
    "labra_unhandled_errors_total",
    "Errors shown to staff with a reference number.",
    registry=REGISTRY,
)

UNMATCHED = "<unmatched>"


def route_template(scope: Scope) -> str:
    route = scope.get("route")
    return getattr(route, "path", UNMATCHED)


class MetricsMiddleware:
    """Counts every HTTP request by route template, method and final status."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route, method = route_template(scope), scope["method"]
            HTTP_REQUESTS.labels(route, method, str(status)).inc()
            HTTP_SECONDS.labels(route, method).observe(time.perf_counter() - started)


def scrape_allowed(settings: Settings, client_ip: str | None, authorization: str | None) -> bool:
    """A scrape is allowed with the bearer token, or from an internal network when no token
    is set."""
    token = settings.metrics_token
    if token is not None:
        expected = f"Bearer {token.get_secret_value()}"
        return authorization is not None and hmac.compare_digest(authorization, expected)
    if client_ip is None:
        return False
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(net) for net in settings.internal_networks)


router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    settings = get_settings()
    client_ip = request.client.host if request.client else None
    if settings.metrics == "off" or not scrape_allowed(
        settings, client_ip, request.headers.get("authorization")
    ):
        # 404, not 403: an outsider learns nothing about what's here.
        raise NotFoundError()
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


def count_job(job: str, ok: bool) -> None:
    JOB_RUNS.labels(job, "true" if ok else "false").inc()


def count_error() -> None:
    ERRORS.inc()
