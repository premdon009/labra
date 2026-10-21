from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth import service
from labra.auth.deps import optional_session, parse_uuid, session_cookie, signed_in
from labra.auth.models import UserSession
from labra.auth.principal import Principal
from labra.core.config import get_settings
from labra.core.db import get_session
from labra.core.errors import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.ids import utcnow
from labra.core.registry import get_platform
from labra.web.templating import page, render

router = APIRouter()

DB = Annotated[Session, Depends(get_session)]


def safe_next(target: str | None) -> str:
    """Only same-site paths, so the login page can't be used to bounce users elsewhere."""
    if not target or not target.startswith("/") or target.startswith(("//", "/\\")):
        return "/"
    return target


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("/login", response_class=HTMLResponse)
@page("getting-started/login", "auth/login.html")
def login_page(
    request: Request,
    session: Annotated[UserSession | None, Depends(optional_session)],
    next: str = "/",
) -> Response:
    if session is not None:
        return RedirectResponse(safe_next(next), status_code=303)
    return render(request, "auth/login.html", {"next": safe_next(next), "error": None})


@router.post("/login")
def login(
    request: Request,
    db: DB,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/",
) -> Response:
    try:
        signed = service.login(
            db, get_platform().identity, username, password, client_ip(request), utcnow()
        )
    except AuthenticationError as exc:
        return render(
            request,
            "auth/login.html",
            {"next": safe_next(next), "error": exc.public_message, "username": username},
            status_code=401,
        )
    response = RedirectResponse(safe_next(next), status_code=303)
    settings = get_settings()
    response.set_cookie(
        session_cookie(),
        signed.token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
def logout(
    request: Request,
    db: DB,
    session: Annotated[UserSession | None, Depends(optional_session)],
    _: Annotated[Principal, Depends(signed_in)],
) -> Response:
    if session is not None:
        service.logout(db, session, utcnow())
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(session_cookie(), path="/")
    return response


@router.post("/branch")
def switch_branch(
    db: DB,
    session: Annotated[UserSession | None, Depends(optional_session)],
    _: Annotated[Principal, Depends(signed_in)],
    branch_id: Annotated[str, Form()],
) -> Response:
    target = parse_uuid(branch_id)
    if session is None or target is None:
        raise PermissionDeniedError()
    service.switch_branch(db, session, target)
    return RedirectResponse("/", status_code=303)


def _password_login() -> None:
    if get_platform().identity.kind != "password":
        raise NotFoundError("passwords are kept by the sign-in provider")


@router.get("/account/password", response_class=HTMLResponse)
@page("getting-started/change-password", "auth/change_password.html")
def change_password_page(
    request: Request, _: Annotated[Principal, Depends(signed_in)], changed: bool = False
) -> Response:
    _password_login()
    return render(request, "auth/change_password.html", {"errors": {}, "changed": changed})


@router.post("/account/password")
def change_password(
    request: Request,
    db: DB,
    session: Annotated[UserSession | None, Depends(optional_session)],
    _: Annotated[Principal, Depends(signed_in)],
    current: Annotated[str, Form()] = "",
    new: Annotated[str, Form()] = "",
    again: Annotated[str, Form()] = "",
) -> Response:
    _password_login()
    if session is None:
        raise AuthenticationError()
    try:
        service.change_own_password(
            db,
            get_platform().identity,
            session,
            current,
            new,
            again,
            client_ip(request),
            utcnow(),
        )
    except ValidationFailedError as exc:
        return render(
            request,
            "auth/change_password.html",
            {"errors": exc.errors, "changed": False},
            status_code=422,
        )
    return RedirectResponse("/account/password?changed=1", status_code=303)


@router.get("/", response_class=HTMLResponse)
@page("getting-started/screen-layout", "home.html")
def home(request: Request, principal: Annotated[Principal, Depends(signed_in)]) -> Response:
    return render(request, "home.html")
