"""Per-request context: request ID, access log line, security headers."""

import re
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from labra.core.logging import get_logger, request_id_var
from labra.core.metrics import route_template

log = get_logger("labra.http")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")

# The app sets these itself, so every proxy (or none) gives the same headers.
SECURITY_HEADERS = {
    "content-security-policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    ),
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


ErrorHandler = Callable[[Request, Exception], Awaitable[Response]]


class RequestContextMiddleware:
    """Outermost app middleware. Unexpected errors are turned into a response here, inside
    the request context, so the error page still carries the request ID and headers."""

    def __init__(self, app: ASGIApp, on_error: ErrorHandler | None = None) -> None:
        self.app = app
        self.on_error = on_error

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = 500
        started_response = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status, started_response
            if message["type"] == "http.response.start":
                started_response = True
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers["x-request-id"] = rid
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if scope["path"] != "/static" and not scope["path"].startswith("/static/"):
                    headers.setdefault("cache-control", "no-store")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if started_response or self.on_error is None:
                raise
            response = await self.on_error(Request(scope, receive), exc)
            await response(scope, receive, send_wrapper)
        finally:
            route = route_template(scope)
            if route not in {"/healthz", "/readyz", "/metrics"}:
                log.info(
                    "request",
                    method=scope["method"],
                    route=route,
                    status=status,
                    ms=round((time.perf_counter() - started) * 1000, 1),
                )
            request_id_var.reset(token)
