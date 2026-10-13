"""Turns exceptions into responses in one place. Unexpected errors get a reference number
that staff can read out to support (EC-E03); the details go to the ErrorReporter."""

import secrets
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

from labra.core.errors import AuthenticationError, ConflictError, LabraError
from labra.core.logging import request_id_var
from labra.core.metrics import count_error, route_template
from labra.core.registry import get_platform
from labra.web.templating import render


def new_reference() -> str:
    """Short enough to read over the phone: E-7F3K9Q2M."""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "E-" + "".join(secrets.choice(alphabet) for _ in range(8))


def wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "") or "hx-request" in request.headers


def _error_response(request: Request, status: int, message: str, ref: str | None) -> Response:
    if wants_html(request):
        return render(
            request,
            "errors/error.html",
            {"status": status, "message": message, "reference": ref},
            status_code=status,
        )
    body = {"error": message} | ({"reference": ref} if ref else {})
    return JSONResponse(body, status_code=status)


def _login_redirect(request: Request) -> Response:
    target = request.url.path
    if request.url.query:
        target += "?" + request.url.query
    url = "/login?next=" + quote(target, safe="")
    if "hx-request" in request.headers:
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


async def labra_error(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, LabraError):
        raise exc
    if isinstance(exc, AuthenticationError) and request.method == "GET" and wants_html(request):
        return _login_redirect(request)
    return _error_response(request, exc.status_code, exc.public_message, None)


async def http_error(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    message = "Not found." if exc.status_code == 404 else str(exc.detail)
    return _error_response(request, exc.status_code, message, None)


async def validation_error(request: Request, exc: Exception) -> Response:
    return _error_response(request, 422, "Some of the submitted values are not valid.", None)


async def conflict_error(request: Request, exc: Exception) -> Response:
    """Two people saved the same thing at once and the database kept the first. Nothing
    of the second was saved, so reloading and trying again is safe."""
    message = ConflictError.public_message
    if isinstance(exc, IntegrityError):
        message = "This clashes with something saved a moment ago. Reload and try again."
    return _error_response(request, ConflictError.status_code, message, None)


async def unexpected_error(request: Request, exc: Exception) -> Response:
    ref = new_reference()
    count_error()
    get_platform().errors.report(
        exc,
        ref,
        {
            "route": route_template(request.scope),
            "method": request.method,
            "request_id": request_id_var.get() or "",
        },
    )
    return _error_response(
        request, 500, "Something went wrong. Tell support this reference number.", ref
    )


def install(app: FastAPI) -> None:
    """Expected errors only; unexpected ones reach `unexpected_error` through
    RequestContextMiddleware."""
    app.add_exception_handler(LabraError, labra_error)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(IntegrityError, conflict_error)
    app.add_exception_handler(StaleDataError, conflict_error)
