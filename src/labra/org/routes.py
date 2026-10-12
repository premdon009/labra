import uuid
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core import lab_settings
from labra.core.db import get_session
from labra.core.errors import NotFoundError, ValidationFailedError
from labra.core.registry import get_platform
from labra.org import service
from labra.org.models import BRANCH_KINDS
from labra.web.templating import page, render

router = APIRouter(prefix="/admin")

DB = Annotated[Session, Depends(get_session)]


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise NotFoundError() from None


# Branches


@router.get("/branches", response_class=HTMLResponse)
@page("admin/branches", "org/branches.html")
def branches(
    request: Request, db: DB, principal: Annotated[Principal, Depends(require("branch.view"))]
) -> Response:
    return render(
        request,
        "org/branches.html",
        {
            "branches": service.list_branches(db, principal),
            "can_edit": principal.can("branch.edit"),
        },
    )


def _branch_form(
    request: Request, branch: object, errors: dict[str, str], status: int = 200
) -> Response:
    return render(
        request,
        "org/branch_form.html",
        {"branch": branch, "errors": errors, "kinds": BRANCH_KINDS},
        status_code=status,
    )


@router.get("/branches/new", response_class=HTMLResponse)
@page("admin/branches", "org/branch_form.html")
def branch_new(
    request: Request, principal: Annotated[Principal, Depends(require("branch.edit"))]
) -> Response:
    return _branch_form(request, None, {})


@router.get("/branches/{branch_id}", response_class=HTMLResponse)
@page("admin/branches", "org/branch_form.html")
def branch_edit(
    request: Request,
    branch_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("branch.edit"))],
) -> Response:
    return _branch_form(request, service.get_branch(db, principal, _uuid(branch_id)), {})


@router.post("/branches")
def branch_save(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("branch.edit"))],
    code: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    kind: Annotated[str, Form()] = "",
    address: Annotated[str, Form()] = "",
    state_code: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    gstin: Annotated[str, Form()] = "",
    is_active: Annotated[bool, Form()] = False,
    branch_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    data = service.BranchInput(
        code,
        name.strip(),
        kind,
        address.strip(),
        state_code.strip(),
        phone.strip(),
        email.strip(),
        gstin,
        is_active or not branch_id,
    )
    try:
        if branch_id:
            service.update_branch(db, principal, _uuid(branch_id), data, row_version)
        else:
            service.create_branch(db, principal, data)
    except ValidationFailedError as exc:
        db.rollback()
        # Keep the record's ID and version, so the corrected form still edits that record.
        values = SimpleNamespace(**vars(data), id=branch_id, row_version=row_version)
        return _branch_form(request, values, exc.errors, status=422)
    db.commit()
    return RedirectResponse("/admin/branches", status_code=303)


# Staff


@router.get("/users", response_class=HTMLResponse)
@page("admin/users-and-roles", "org/users.html")
def users(
    request: Request, db: DB, principal: Annotated[Principal, Depends(require("user.view"))]
) -> Response:
    return render(
        request,
        "org/users.html",
        {"users": service.list_users(db, principal), "can_edit": principal.can("user.edit")},
    )


def _user_form(
    request: Request,
    db: DB,
    principal: Principal,
    user: object,
    chosen: set[tuple[uuid.UUID, uuid.UUID]],
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    return render(
        request,
        "org/user_form.html",
        {
            "user": user,
            "chosen": {f"{b}:{r}" for b, r in chosen},
            "branches": service.list_branches(db, principal),
            "roles": service.list_roles(db),
            "password_login": get_platform().identity.kind == "password",
            "errors": errors,
        },
        status_code=status,
    )


@router.get("/users/new", response_class=HTMLResponse)
@page("admin/users-and-roles", "org/user_form.html")
def user_new(
    request: Request, db: DB, principal: Annotated[Principal, Depends(require("user.edit"))]
) -> Response:
    return _user_form(request, db, principal, None, set(), {})


@router.get("/users/{user_id}", response_class=HTMLResponse)
@page("admin/users-and-roles", "org/user_form.html")
def user_edit(
    request: Request,
    user_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("user.edit"))],
) -> Response:
    user = service.get_user(db, principal, _uuid(user_id))
    return _user_form(request, db, principal, user, service.user_roles(db, user.id), {})


def _parse_roles(values: list[str]) -> set[tuple[uuid.UUID, uuid.UUID]]:
    pairs = set()
    for v in values:
        b, _, r = v.partition(":")
        pairs.add((_uuid(b), _uuid(r)))
    return pairs


@router.post("/users")
def user_save(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("user.edit"))],
    username: Annotated[str, Form()] = "",
    full_name: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    can_login: Annotated[bool, Form()] = False,
    is_active: Annotated[bool, Form()] = False,
    password: Annotated[str, Form()] = "",
    role: Annotated[list[str], Form()] = [],  # noqa: B006
    user_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    roles = _parse_roles(role)
    data = service.UserInput(
        username,
        full_name.strip(),
        phone.strip(),
        email.strip(),
        can_login,
        is_active or not user_id,
        roles,
    )
    identity = get_platform().identity
    try:
        if user_id:
            uid = _uuid(user_id)
            service.update_user(db, principal, uid, data, row_version)
            if password:
                service.reset_password(db, principal, identity, uid, password)
        else:
            service.create_user(db, principal, identity, data, password or None)
    except ValidationFailedError as exc:
        db.rollback()
        values = SimpleNamespace(**vars(data), id=user_id, row_version=row_version)
        return _user_form(request, db, principal, values, roles, exc.errors, status=422)
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


# Settings


@router.get("/settings", response_class=HTMLResponse)
@page("admin/settings", "org/settings.html")
def settings_page(
    request: Request, db: DB, principal: Annotated[Principal, Depends(require("setting.view"))]
) -> Response:
    return _settings_form(request, db, principal, {})


def _settings_form(
    request: Request, db: DB, principal: Principal, errors: dict[str, str], status: int = 200
) -> Response:
    rows = [
        {
            "def": d,
            "value": lab_settings.get_value(db, d.key, principal.branch_id),
            "is_int": d.type is int,
        }
        for d in lab_settings.DEFINITIONS.values()
    ]
    return render(
        request,
        "org/settings.html",
        {
            "rows": rows,
            "can_edit_lab": principal.can("setting.edit"),
            "can_edit_branch": principal.can("setting.edit_branch"),
            "errors": errors,
        },
        status_code=status,
    )


@router.post("/settings")
def settings_save(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("setting.view"))],
    key: Annotated[list[str], Form()] = [],  # noqa: B006
    value: Annotated[list[str], Form()] = [],  # noqa: B006
) -> Response:
    errors: dict[str, str] = {}
    for k, raw in zip(key, value, strict=False):
        d = lab_settings.DEFINITIONS.get(k)
        if d is None:
            continue
        try:
            new = lab_settings.coerce(d, raw)
        except ValidationFailedError as exc:
            errors.update(exc.errors)
            continue
        if new == lab_settings.get_value(db, k, principal.branch_id):
            continue
        # Per-branch settings are saved for the user's current branch, others lab-wide.
        branch = principal.branch_id if d.per_branch else None
        allowed = principal.can("setting.edit") or (
            branch is not None and principal.can("setting.edit_branch", branch)
        )
        if not allowed:
            errors[k] = "You can't change this setting."
            continue
        lab_settings.set_value(db, k, new, principal.user_id, branch)
    if errors:
        db.rollback()
        return _settings_form(request, db, principal, errors, status=422)
    db.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@router.get("/settings/numbering", response_class=HTMLResponse)
@page("admin/settings", "org/numbering.html")
def numbering_page(
    request: Request, db: DB, principal: Annotated[Principal, Depends(require("setting.view"))]
) -> Response:
    return _numbering_form(request, db, principal, {}, {})


def _numbering_form(
    request: Request,
    db: DB,
    principal: Principal,
    entered: dict[str, str],
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    return render(
        request,
        "org/numbering.html",
        {
            "rows": service.list_series(db, principal),
            "can_edit": principal.can("setting.edit"),
            "entered": entered,
            "errors": errors,
        },
        status_code=status,
    )


@router.post("/settings/numbering")
def numbering_save(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("setting.edit"))],
    series: Annotated[list[str], Form()] = [],  # noqa: B006
    was: Annotated[list[str], Form()] = [],  # noqa: B006
    fmt: Annotated[list[str], Form()] = [],  # noqa: B006
) -> Response:
    errors: dict[str, str] = {}
    for sid, old, new in zip(series, was, fmt, strict=False):
        try:
            service.set_series_format(db, principal, _uuid(sid), new, old)
        except ValidationFailedError as exc:
            errors.update(exc.errors)
    if errors:
        db.rollback()
        entered = dict(zip(series, fmt, strict=False))
        return _numbering_form(request, db, principal, entered, errors, status=422)
    db.commit()
    return RedirectResponse("/admin/settings/numbering", status_code=303)
