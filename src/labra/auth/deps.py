"""Request dependencies: who is signed in, what they may do, and CSRF.

Every route either names a guard (`signed_in` or `require(...)`) or is listed in
`PUBLIC_PATHS`; a test fails for any route that does neither.
"""

import hmac
import secrets
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from labra.auth import service
from labra.auth.models import UserSession
from labra.auth.principal import Principal
from labra.core.config import get_settings
from labra.core.db import get_session
from labra.core.errors import AuthenticationError, PermissionDeniedError
from labra.core.ids import utcnow

PUBLIC_PATHS = frozenset(
    {
        "/login",
        "/healthz",
        "/readyz",
        "/metrics",
        "/static",
        "/v/{token}",
        "/manual/",
        "/manual/labra-manual.pdf",
        "/manual/{name:path}/",
    }
)
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_FAILED = "This form has expired. Reload the page and try again."


def cookie_name(base: str) -> str:
    """`__Host-` cookies are refused by browsers unless Secure, host-only and path /."""
    return f"__Host-{base}" if get_settings().cookie_secure else base


def session_cookie() -> str:
    return cookie_name("labra_session")


def csrf_cookie() -> str:
    return cookie_name("labra_csrf")


def _load_session(request: Request, db: Session) -> UserSession | None:
    if not hasattr(request.state, "user_session"):
        token = request.cookies.get(session_cookie())
        found = None
        if token:
            s = get_settings()
            found = service.resolve(
                db,
                token,
                utcnow(),
                timedelta(minutes=s.session_idle_minutes),
                timedelta(hours=s.session_absolute_hours),
            )
        request.state.user_session = found
    return request.state.user_session


def optional_session(
    request: Request, db: Annotated[Session, Depends(get_session)]
) -> UserSession | None:
    return _load_session(request, db)


def current_principal(request: Request, db: Annotated[Session, Depends(get_session)]) -> Principal:
    session = _load_session(request, db)
    if session is None:
        raise AuthenticationError()
    principal = service.principal_for(db, session)
    request.state.principal = principal
    return principal


def signed_in(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    return principal


signed_in.__guard__ = "signed_in"  # type: ignore[attr-defined]


def require(permission: str) -> Callable[..., Principal]:
    """A dependency that refuses the request unless the user holds `permission`
    (in their current branch, for branch-scoped permissions)."""

    def check(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        if not principal.can(permission):
            raise PermissionDeniedError()
        return principal

    check.__guard__ = permission  # type: ignore[attr-defined]
    return check


def tokens_match(expected: str | None, submitted: str | None) -> bool:
    if not expected or not submitted:
        return False
    return hmac.compare_digest(expected.encode(), submitted.encode())


def csrf_token(request: Request) -> str:
    """The token to put in forms: the session's own when signed in, otherwise the
    anonymous cookie's (issued here if missing; the renderer sets the cookie)."""
    session = getattr(request.state, "user_session", None)
    if session is not None:
        return session.csrf_token
    token = request.cookies.get(csrf_cookie()) or getattr(request.state, "new_csrf", None)
    if token is None:
        token = secrets.token_urlsafe(32)
        request.state.new_csrf = token
    return token


async def csrf_protect(request: Request, db: Annotated[Session, Depends(get_session)]) -> None:
    """Refuse unsafe requests whose token doesn't match. Applied to every route."""
    if request.method not in UNSAFE_METHODS:
        return
    submitted = request.headers.get("x-csrf-token")
    if submitted is None:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
            value = (await request.form()).get("csrf_token")
            submitted = value if isinstance(value, str) else None
    session = await run_in_threadpool(_load_session, request, db)
    expected = session.csrf_token if session else request.cookies.get(csrf_cookie())
    if not tokens_match(expected, submitted):
        raise PermissionDeniedError(CSRF_FAILED)


def parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
