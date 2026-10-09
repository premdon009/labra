"""Sign-in, sessions and lockout. Passwords are checked by the configured IdentityProvider;
everything after "this is user X" happens here."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.auth.models import LoginAttempt, UserSession
from labra.auth.principal import Principal
from labra.core import audit
from labra.core.errors import AuthenticationError, PermissionDeniedError
from labra.core.ports import IdentityProvider
from labra.org.models import AppUser, Branch, RolePermission, UserBranchRole

LOCKOUT_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=15)
# Write last_seen_at at most this often, so every page view isn't a database write.
TOUCH_EVERY = timedelta(minutes=1)

BAD_LOGIN = "Wrong username or password."
LOCKED = "Too many failed attempts. Wait 15 minutes, or ask an administrator."


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalise_username(username: str) -> str:
    return username.strip().lower()[:40]


def is_locked(db: Session, username: str, ip: str, now: datetime) -> bool:
    """Five failures for this username from this address since the last success, within
    the window, lock the pair."""
    last_ok = db.scalar(
        select(func.max(LoginAttempt.at)).where(
            LoginAttempt.username == username, LoginAttempt.ip == ip, LoginAttempt.ok
        )
    )
    since = now - LOCKOUT_WINDOW
    if last_ok is not None and last_ok > since:
        since = last_ok
    failures = db.scalar(
        select(func.count()).where(
            LoginAttempt.username == username,
            LoginAttempt.ip == ip,
            LoginAttempt.ok.is_(False),
            LoginAttempt.at > since,
        )
    )
    return (failures or 0) >= LOCKOUT_FAILURES


def grants_for(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, frozenset[str]]:
    rows = db.execute(
        select(UserBranchRole.branch_id, RolePermission.permission)
        .join(RolePermission, RolePermission.role_id == UserBranchRole.role_id)
        .where(UserBranchRole.user_id == user_id)
    )
    found: dict[uuid.UUID, set[str]] = {}
    for branch_id, permission in rows:
        found.setdefault(branch_id, set()).add(permission)
    return {b: frozenset(p) for b, p in found.items()}


@dataclass(frozen=True)
class SignedIn:
    token: str
    session: UserSession


def login(
    db: Session,
    identity: IdentityProvider,
    username: str,
    password: str,
    ip: str,
    now: datetime,
) -> SignedIn:
    name = normalise_username(username)
    if is_locked(db, name, ip, now):
        raise AuthenticationError(LOCKED)
    user = db.scalar(select(AppUser).where(AppUser.username == name))
    # Check a password even for an unknown user, so timing doesn't reveal which names exist.
    ok = identity.verify_password(db, user.id if user else uuid.uuid4(), password)
    ok = ok and user is not None and user.is_active and user.can_login
    db.add(LoginAttempt(username=name, ip=ip, at=now, ok=ok))
    if not ok or user is None:
        db.flush()
        if is_locked(db, name, ip, now):
            audit.record(db, "auth.locked", "app_user", user.id if user else None)
        db.commit()
        raise AuthenticationError(BAD_LOGIN)
    branches = sorted(grants_for(db, user.id))
    token = secrets.token_urlsafe(32)
    session = UserSession(
        token_hash=hash_token(token),
        user_id=user.id,
        branch_id=branches[0] if branches else None,
        csrf_token=secrets.token_urlsafe(32),
        ip=ip,
        created_at=now,
        last_seen_at=now,
    )
    db.add(session)
    user.last_login_at = now
    db.flush()
    audit.record(db, "auth.login", "app_user", user.id, user_id=user.id)
    db.commit()
    return SignedIn(token, session)


def resolve(
    db: Session, token: str, now: datetime, idle: timedelta, absolute: timedelta
) -> UserSession | None:
    """The live session for a cookie token, or None when it's unknown, ended or expired."""
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token), UserSession.ended_at.is_(None)
        )
    )
    if session is None:
        return None
    if now - session.last_seen_at > idle or now - session.created_at > absolute:
        session.ended_at = now
        db.commit()
        return None
    user = db.get(AppUser, session.user_id)
    if user is None or not user.is_active or not user.can_login:
        return None
    if now - session.last_seen_at > TOUCH_EVERY:
        session.last_seen_at = now
        db.commit()
    return session


def logout(db: Session, session: UserSession, now: datetime) -> None:
    session.ended_at = now
    audit.record(db, "auth.logout", "app_user", session.user_id, user_id=session.user_id)
    db.commit()


def end_all_sessions(db: Session, user_id: uuid.UUID, now: datetime) -> None:
    """Sign a user out everywhere, after a password reset or when access is removed."""
    for s in db.scalars(
        select(UserSession).where(UserSession.user_id == user_id, UserSession.ended_at.is_(None))
    ):
        s.ended_at = now


def principal_for(db: Session, session: UserSession) -> Principal:
    user = db.get(AppUser, session.user_id)
    if user is None:
        raise AuthenticationError()
    grants = grants_for(db, user.id)
    branch_id = session.branch_id if session.branch_id in grants else None
    labels = {
        b.id: f"{b.code} · {b.name}"
        for b in db.scalars(select(Branch).where(Branch.id.in_(grants)).order_by(Branch.code))
    }
    return Principal(user.id, user.username, user.full_name, branch_id, grants, labels)


def switch_branch(db: Session, session: UserSession, branch_id: uuid.UUID) -> None:
    if branch_id not in grants_for(db, session.user_id):
        raise PermissionDeniedError("You have no role at that branch.")
    session.branch_id = branch_id
    db.commit()
