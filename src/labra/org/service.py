"""Branches, staff and roles. Every function takes the acting Principal and checks it, so a
route can't forget to."""

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.auth.service import end_all_sessions
from labra.core import audit, consent
from labra.core.db import TrackedMixin
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.files import save_file
from labra.core.ids import IST, lab_today, utcnow
from labra.core.models import ConsentNotice, NumberSeries
from labra.core.numbering import DOC_LABELS, ensure_series, format_problems
from labra.core.paging import Page, page_of
from labra.core.ports import FileStore, IdentityProvider
from labra.core.uploads import PNG
from labra.org.models import BRANCH_KINDS, AppUser, Branch, Role, RolePermission, UserBranchRole
from labra.org.permissions import SYSTEM_ROLES

_CODE_RE = re.compile(r"^[A-Z0-9]{1,4}$")
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,40}$")
_PHONE_RE = re.compile(r"^[6-9]\d{9}$")
_GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_STATE_RE = re.compile(r"^\d{2}$")
_CERT_RE = re.compile(r"^[A-Z0-9][A-Z0-9/ -]{0,39}$")


def _check(principal: Principal, permission: str, branch_id: uuid.UUID | None = None) -> None:
    if not principal.can(permission, branch_id):
        raise PermissionDeniedError()


def stale(db: Session, record: TrackedMixin) -> ConflictError:
    """The error for an edit made on an old copy of `record`: says who changed it since."""
    who = db.get(AppUser, record.updated_by) if record.updated_by else None
    name = who.full_name if who else "Someone"
    at = record.updated_at.astimezone(IST)
    return ConflictError(
        f"{name} changed this record at {at:%H:%M}. Reload to see their changes, then make"
        " yours again."
    )


# Branches


@dataclass
class BranchInput:
    code: str
    name: str
    kind: str
    address: str = ""
    state_code: str = ""
    phone: str = ""
    email: str = ""
    gstin: str = ""
    is_active: bool = True
    nabl_cert_no: str = ""

    def problems(self) -> dict[str, str]:
        p: dict[str, str] = {}
        if not _CODE_RE.match(self.code):
            p["code"] = "Use 1 to 4 capital letters or digits, for example B2."
        if not self.name.strip():
            p["name"] = "Enter the branch name."
        if self.kind not in BRANCH_KINDS:
            p["kind"] = "Choose main lab or collection centre."
        if self.state_code and not _STATE_RE.match(self.state_code):
            p["state_code"] = "Two digits, for example 27."
        if self.phone and not _PHONE_RE.match(self.phone):
            p["phone"] = "Ten digits, starting with 6 to 9."
        if self.gstin and not _GSTIN_RE.match(self.gstin):
            p["gstin"] = "A GSTIN has 15 characters, for example 27ABCDE1234F1Z5."
        if self.nabl_cert_no and not _CERT_RE.match(self.nabl_cert_no):
            p["nabl_cert_no"] = "Up to 40 letters, digits, dashes or slashes, for example MC-1234."
        return p


def list_branches(db: Session, principal: Principal) -> list[Branch]:
    visible = principal.branches_with("branch.view")
    if not visible:
        return []
    return list(db.scalars(select(Branch).where(Branch.id.in_(visible)).order_by(Branch.code)))


def branch_page(db: Session, principal: Principal, page: int) -> Page[Branch]:
    visible = principal.branches_with("branch.view")
    return page_of(db, select(Branch).where(Branch.id.in_(visible)).order_by(Branch.code), page)


def get_branch(db: Session, principal: Principal, branch_id: uuid.UUID) -> Branch:
    """Branches outside the user's scope are reported as not found, not forbidden."""
    branch = db.get(Branch, branch_id)
    if branch is None or not principal.can("branch.view", branch_id):
        raise NotFoundError()
    return branch


def _validate_branch(db: Session, data: BranchInput, exclude: uuid.UUID | None) -> None:
    data.code = data.code.strip().upper()
    data.gstin = data.gstin.strip().upper()
    data.nabl_cert_no = data.nabl_cert_no.strip().upper()
    problems = data.problems()
    clash = db.scalar(select(Branch.id).where(Branch.code == data.code))
    if clash is not None and clash != exclude:
        problems["code"] = f"Branch code {data.code} is already used."
    if data.kind == "main_lab":
        main = db.scalar(select(Branch.id).where(Branch.kind == "main_lab"))
        if main is not None and main != exclude:
            problems["kind"] = "There is already a main lab."
    if problems:
        raise ValidationFailedError(problems)


def create_branch(db: Session, principal: Principal, data: BranchInput) -> Branch:
    _check(principal, "branch.edit")
    _validate_branch(db, data, None)
    branch = Branch(**vars(data), created_by=principal.user_id)
    db.add(branch)
    db.flush()
    # Roles are held per branch, so without this nobody could see the new branch. The creator
    # gets only the roles that already let them edit branches: no one gains access this way.
    editing_roles = db.scalars(
        select(UserBranchRole.role_id)
        .join(RolePermission, RolePermission.role_id == UserBranchRole.role_id)
        .where(
            UserBranchRole.user_id == principal.user_id,
            RolePermission.permission == "branch.edit",
        )
        .distinct()
    )
    for role_id in editing_roles:
        db.add(UserBranchRole(user_id=principal.user_id, branch_id=branch.id, role_id=role_id))
    db.flush()
    ensure_series(db, branch.id, branch.code, lab_today())
    audit.record(
        db, "branch.create", "branch", branch.id, {"code": branch.code}, user_id=principal.user_id
    )
    return branch


def update_branch(
    db: Session, principal: Principal, branch_id: uuid.UUID, data: BranchInput, row_version: int
) -> Branch:
    _check(principal, "branch.edit")
    branch = get_branch(db, principal, branch_id)
    if branch.row_version != row_version:
        raise stale(db, branch)
    _validate_branch(db, data, branch.id)
    if data.code != branch.code:
        # The code is part of every number the branch issues, so a longer one can push a
        # format that fitted past what a bill number may be.
        for series in db.scalars(select(NumberSeries).where(NumberSeries.branch_id == branch.id)):
            problems = format_problems(series.doc_type, series.format, data.code)
            if problems:
                label = DOC_LABELS.get(series.doc_type, series.doc_type).lower()
                raise ValidationFailedError(
                    {
                        "code": f"With this code the {label} no longer fits. {problems[0]} "
                        "Use a shorter code, or change the format under Numbering first."
                    }
                )
    changed = [k for k, v in vars(data).items() if getattr(branch, k) != v]
    for k in changed:
        setattr(branch, k, getattr(data, k))
    branch.updated_by = principal.user_id
    db.flush()
    if changed:
        audit.record(
            db, "branch.update", "branch", branch.id, {"fields": changed}, user_id=principal.user_id
        )
    return branch


# Number series


@dataclass(frozen=True)
class SeriesRow:
    series: NumberSeries
    branch: Branch
    label: str


def list_series(db: Session, principal: Principal) -> list[SeriesRow]:
    _check(principal, "setting.view")
    order = list(DOC_LABELS)
    found = db.execute(
        select(NumberSeries, Branch).join(Branch, Branch.id == NumberSeries.branch_id)
    ).all()
    rows = [SeriesRow(s, b, DOC_LABELS.get(s.doc_type, s.doc_type)) for s, b in found]
    rank = {doc_type: i for i, doc_type in enumerate(order)}
    rows.sort(key=lambda r: (r.branch.code, rank.get(r.series.doc_type, len(order))))
    return rows


def set_series_format(
    db: Session, principal: Principal, series_id: uuid.UUID, fmt: str, was: str
) -> bool:
    """Change one series' format; numbering carries on from the next value. `was` is the
    format the user saw, so two admins editing at once don't overwrite each other.
    Issuing numbers bumps `row_version`, so that can't be the check here."""
    _check(principal, "setting.edit")
    found = db.execute(
        select(NumberSeries, Branch)
        .join(Branch, Branch.id == NumberSeries.branch_id)
        .where(NumberSeries.id == series_id)
    ).first()
    if found is None:
        raise NotFoundError()
    series, branch = found
    if series.format != was:
        raise ConflictError("Someone changed this number format. Reload, then try again.")
    fmt = fmt.strip()
    if fmt == series.format:
        return False
    problems = format_problems(series.doc_type, fmt, branch.code)
    if problems:
        raise ValidationFailedError({str(series.id): " ".join(problems)})
    series.format = fmt
    series.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "number_series.update",
        "number_series",
        series.id,
        {"doc_type": series.doc_type, "format": fmt},
        user_id=principal.user_id,
    )
    return True


# Consent notice


def publish_consent_notice(
    db: Session, principal: Principal, body_text: str, was_version: int
) -> ConsentNotice | None:
    """Publish new wording as the next version; None when the text is unchanged.
    `was_version` is the version the user edited, so a newer one is never overwritten."""
    _check(principal, "setting.edit")
    current = consent.current_notice(db)
    if current.version != was_version:
        raise ConflictError("Someone published a new consent notice. Reload, then try again.")
    text = body_text.replace("\r\n", "\n").strip()
    if not text:
        raise ValidationFailedError({"body_text": "Write the notice patients agree to."})
    if len(text) > consent.MAX_NOTICE_LENGTH:
        raise ValidationFailedError(
            {"body_text": f"Keep the notice to {consent.MAX_NOTICE_LENGTH} characters."}
        )
    if text == current.body_text:
        return None
    notice = consent.publish_notice(db, text)
    audit.record(
        db,
        "consent_notice.publish",
        "consent_notice",
        notice.id,
        {"version": notice.version},
        user_id=principal.user_id,
    )
    return notice


# Roles


def sync_system_roles(db: Session) -> None:
    """Make the system roles match the code: add missing roles and permissions, and drop
    permissions a release removed. Custom roles are left alone."""
    for sr in SYSTEM_ROLES.values():
        role = db.scalar(select(Role).where(Role.code == sr.code))
        if role is None:
            role = Role(code=sr.code, name=sr.name, is_system=True)
            db.add(role)
            db.flush()
        have = set(
            db.scalars(select(RolePermission.permission).where(RolePermission.role_id == role.id))
        )
        for perm in sr.permissions - have:
            db.add(RolePermission(role_id=role.id, permission=perm))
        if have - sr.permissions:
            db.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission.in_(have - sr.permissions),
                )
            )
    db.flush()


def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.name)))


# Staff


@dataclass
class UserInput:
    username: str
    full_name: str
    phone: str = ""
    email: str = ""
    can_login: bool = True
    is_active: bool = True
    # (branch_id, role_id) pairs.
    roles: set[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=set)
    # Printed under a signatory's name on reports.
    qualification: str = ""
    council_reg_no: str = ""

    def problems(self) -> dict[str, str]:
        p: dict[str, str] = {}
        if not _USERNAME_RE.match(self.username):
            p["username"] = "3 to 40 characters: small letters, digits, dot, dash, underscore."
        if not self.full_name.strip():
            p["full_name"] = "Enter the full name."
        if self.phone and not _PHONE_RE.match(self.phone):
            p["phone"] = "Ten digits, starting with 6 to 9."
        if self.email and "@" not in self.email:
            p["email"] = "Enter a valid email address."
        if len(self.qualification) > 80:
            p["qualification"] = "Up to 80 characters."
        if len(self.council_reg_no) > 40:
            p["council_reg_no"] = "Up to 40 characters."
        return p


def user_page(db: Session, principal: Principal, page: int) -> Page[AppUser]:
    _check(principal, "user.view")
    return page_of(db, select(AppUser).order_by(AppUser.full_name, AppUser.id), page)


def get_user(db: Session, principal: Principal, user_id: uuid.UUID) -> AppUser:
    _check(principal, "user.view")
    user = db.get(AppUser, user_id)
    if user is None:
        raise NotFoundError()
    return user


def user_roles(db: Session, user_id: uuid.UUID) -> set[tuple[uuid.UUID, uuid.UUID]]:
    rows = db.execute(
        select(UserBranchRole.branch_id, UserBranchRole.role_id).where(
            UserBranchRole.user_id == user_id
        )
    )
    return {(b, r) for b, r in rows}


def _validate_user(db: Session, data: UserInput, exclude: uuid.UUID | None) -> None:
    data.username = data.username.strip().lower()
    problems = data.problems()
    clash = db.scalar(select(AppUser.id).where(AppUser.username == data.username))
    if clash is not None and clash != exclude:
        problems["username"] = "That username is taken."
    branches = {b for b, _ in data.roles}
    roles = {r for _, r in data.roles}
    known_b = set(db.scalars(select(Branch.id).where(Branch.id.in_(branches))))
    known_r = set(db.scalars(select(Role.id).where(Role.id.in_(roles))))
    if branches - known_b or roles - known_r:
        problems["roles"] = "A chosen branch or role no longer exists. Reload and try again."
    if problems:
        raise ValidationFailedError(problems)


def _set_roles(db: Session, user_id: uuid.UUID, wanted: set[tuple[uuid.UUID, uuid.UUID]]) -> bool:
    have = user_roles(db, user_id)
    for b, r in have - wanted:
        db.execute(
            delete(UserBranchRole).where(
                UserBranchRole.user_id == user_id,
                UserBranchRole.branch_id == b,
                UserBranchRole.role_id == r,
            )
        )
    for b, r in wanted - have:
        db.add(UserBranchRole(user_id=user_id, branch_id=b, role_id=r))
    return have != wanted


def create_user(
    db: Session,
    principal: Principal,
    identity: IdentityProvider,
    data: UserInput,
    password: str | None,
) -> AppUser:
    _check(principal, "user.edit")
    _validate_user(db, data, None)
    if data.can_login and identity.kind == "password":
        problems = identity.password_problems(password or "")
        if problems:
            raise ValidationFailedError({"password": " ".join(problems)})
    fields = {k: v for k, v in vars(data).items() if k != "roles"}
    user = AppUser(**fields, created_by=principal.user_id)
    db.add(user)
    db.flush()
    _set_roles(db, user.id, data.roles)
    if data.can_login and password:
        identity.set_password(db, user.id, password)
    db.flush()
    audit.record(
        db,
        "user.create",
        "app_user",
        user.id,
        {"roles": len(data.roles), "can_login": data.can_login},
        user_id=principal.user_id,
    )
    return user


def update_user(
    db: Session, principal: Principal, user_id: uuid.UUID, data: UserInput, row_version: int
) -> AppUser:
    _check(principal, "user.edit")
    user = get_user(db, principal, user_id)
    if user.row_version != row_version:
        raise stale(db, user)
    _validate_user(db, data, user.id)
    if user.id == principal.user_id and not (data.is_active and data.can_login):
        raise ValidationFailedError({"can_login": "You can't switch off your own sign-in."})
    fields = {k: v for k, v in vars(data).items() if k != "roles"}
    changed = [k for k, v in fields.items() if getattr(user, k) != v]
    for k in changed:
        setattr(user, k, fields[k])
    user.updated_by = principal.user_id
    if _set_roles(db, user.id, data.roles):
        changed.append("roles")
    db.flush()
    if changed:
        audit.record(
            db, "user.update", "app_user", user.id, {"fields": changed}, user_id=principal.user_id
        )
    return user


def reset_password(
    db: Session,
    principal: Principal,
    identity: IdentityProvider,
    user_id: uuid.UUID,
    password: str,
) -> None:
    _check(principal, "user.edit")
    user = get_user(db, principal, user_id)
    problems = identity.password_problems(password)
    if problems:
        raise ValidationFailedError({"password": " ".join(problems)})
    identity.set_password(db, user.id, password)
    end_all_sessions(db, user.id, utcnow())
    audit.record(db, "user.password_reset", "app_user", user.id, user_id=principal.user_id)


def set_signature(
    db: Session,
    store: FileStore,
    principal: Principal,
    user_id: uuid.UUID,
    png: bytes | None,
    row_version: int,
) -> AppUser:
    """Store the signature printed on the reports a signatory releases, or take it off with
    `png` None. The image is made by the caller, already re-encoded."""
    _check(principal, "user.edit")
    user = get_user(db, principal, user_id)
    if user.row_version != row_version:
        raise stale(db, user)
    if png is None:
        user.signature_file_id = None
    else:
        saved = save_file(db, store, png, f"signature-{user.username}.png", PNG, principal.user_id)
        user.signature_file_id = saved.id
    user.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "user.signature",
        "app_user",
        user.id,
        {"removed": png is None, "bytes": len(png or b"")},
        user_id=principal.user_id,
    )
    return user
