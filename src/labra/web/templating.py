"""Jinja rendering, the `page` decorator that ties a screen to its manual page, and the
links to vendored assets."""

import json
from collections.abc import Callable
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from labra import __version__
from labra.auth.deps import csrf_cookie, csrf_token
from labra.core.config import get_settings

PACKAGE = Path(str(files("labra")))
TEMPLATES = PACKAGE / "templates"

templates = Jinja2Templates(directory=TEMPLATES)


@lru_cache
def vendor_manifest() -> dict[str, dict[str, str]]:
    return json.loads((PACKAGE / "static" / "vendor" / "manifest.json").read_text())


def vendor_url(prefix: str) -> str:
    """URL of the vendored file whose name starts with `prefix` (e.g. "htmx-")."""
    for name in vendor_manifest():
        if name.startswith(prefix):
            return f"/static/vendor/{name}"
    raise KeyError(prefix)


templates.env.globals.update(
    app_version=__version__,
    vendor_url=vendor_url,
)


def page(manual_page: str, template: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a route as a screen. `scripts/check_manual.py` checks that
    `docs/manual/<manual_page>.md` exists and changes whenever the template does."""

    def mark(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__manual_page__ = manual_page  # type: ignore[attr-defined]
        fn.__template__ = template  # type: ignore[attr-defined]
        return fn

    return mark


def manual_url(request: Request) -> str | None:
    """Link to this screen's manual page, for the help button."""
    name = getattr(request.scope.get("endpoint"), "__manual_page__", None)
    if name is None:
        return None
    return f"{get_settings().manual_url.rstrip('/')}/{name}/"


def render(
    request: Request, template: str, context: dict[str, Any] | None = None, status_code: int = 200
) -> HTMLResponse:
    ctx: dict[str, Any] = {
        "csrf_token": csrf_token(request),
        "principal": getattr(request.state, "principal", None),
        "manual_url": manual_url(request),
        **(context or {}),
    }
    response = templates.TemplateResponse(request, template, ctx, status_code=status_code)
    new = getattr(request.state, "new_csrf", None)
    if new is not None:
        response.set_cookie(
            csrf_cookie(),
            new,
            httponly=True,
            secure=get_settings().cookie_secure,
            samesite="lax",
            path="/",
        )
    return response
