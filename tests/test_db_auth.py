"""Sign-in, sessions and branch scoping against real Postgres, using the demo cast."""

import re
from datetime import timedelta

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.adapters.identity_local import LocalCredential, LocalIdentity
from labra.auth import service
from labra.auth.deps import session_cookie
from labra.core.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from labra.core.ids import utcnow
from labra.core.registry import Platform
from labra.org import service as org
from labra.org.models import AppUser, Branch
from labra.seed import DEMO_PASSWORD

IDLE = timedelta(minutes=30)
ABSOLUTE = timedelta(hours=12)


def _user(db: Session, username: str) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.username == username))
    assert user is not None
    return user


def _branch(db: Session, code: str) -> Branch:
    branch = db.scalar(select(Branch).where(Branch.code == code))
    assert branch is not None
    return branch


# Service level


@pytest.mark.item("M01")
def test_login_and_resolve(seeded: Session, platform: Platform) -> None:
    now = utcnow()
    signed = service.login(seeded, platform.identity, " Priya ", DEMO_PASSWORD, "10.0.0.5", now)
    assert service.resolve(seeded, signed.token, now, IDLE, ABSOLUTE) is not None
    assert signed.session.branch_id == _branch(seeded, "B2").id
    assert signed.session.token_hash != signed.token


@pytest.mark.item("M01")
def test_wrong_password_and_unknown_user_look_alike(seeded: Session, platform: Platform) -> None:
    now = utcnow()
    with pytest.raises(AuthenticationError) as wrong:
        service.login(seeded, platform.identity, "priya", "not-the-password", "10.0.0.5", now)
    with pytest.raises(AuthenticationError) as unknown:
        service.login(seeded, platform.identity, "nobody", "not-the-password", "10.0.0.5", now)
    assert wrong.value.public_message == unknown.value.public_message


@pytest.mark.item("EC-A02")
def test_lockout_after_five_failures(seeded: Session, platform: Platform) -> None:
    now = utcnow()
    for _ in range(service.LOCKOUT_FAILURES):
        with pytest.raises(AuthenticationError):
            service.login(seeded, platform.identity, "priya", "wrong-password", "10.0.0.5", now)
    with pytest.raises(AuthenticationError) as locked:
        service.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.5", now)
    assert locked.value.public_message == service.LOCKED
    # Another address isn't locked out, and the lock lifts after the window.
    service.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.6", now)
    later = now + service.LOCKOUT_WINDOW + timedelta(seconds=1)
    service.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.5", later)


@pytest.mark.item("EC-A03")
def test_sessions_expire_when_idle_and_after_absolute_limit(
    seeded: Session, platform: Platform
) -> None:
    now = utcnow()
    first = service.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.5", now)
    assert (
        service.resolve(seeded, first.token, now + IDLE + timedelta(seconds=1), IDLE, ABSOLUTE)
        is None
    )
    # Ended for good, even if asked again sooner.
    assert service.resolve(seeded, first.token, now, IDLE, ABSOLUTE) is None

    second = service.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.5", now)
    # Active every 20 minutes, so never idle, until the absolute limit passes.
    t = now
    while t + timedelta(minutes=20) < now + ABSOLUTE:
        t += timedelta(minutes=20)
        assert service.resolve(seeded, second.token, t, IDLE, ABSOLUTE) is not None
    late = now + ABSOLUTE + timedelta(minutes=1)
    assert service.resolve(seeded, second.token, late, IDLE, ABSOLUTE) is None


@pytest.mark.item("M01.2")
def test_staff_without_sign_in_refused(seeded: Session, platform: Platform) -> None:
    staff = _user(seeded, "staff1")
    assert not staff.can_login
    platform.identity.set_password(seeded, staff.id, "a-long-password-1")
    with pytest.raises(AuthenticationError):
        service.login(
            seeded, platform.identity, "staff1", "a-long-password-1", "10.0.0.5", utcnow()
        )


@pytest.mark.item("EC-A01")
def test_old_password_hash_upgraded_on_login(seeded: Session) -> None:
    user = _user(seeded, "priya")
    LocalIdentity(PasswordHasher(time_cost=1, memory_cost=8192)).set_password(
        seeded, user.id, DEMO_PASSWORD
    )
    seeded.flush()
    service.login(seeded, LocalIdentity(), "priya", DEMO_PASSWORD, "10.0.0.5", utcnow())
    cred = seeded.get(LocalCredential, user.id)
    assert cred is not None
    assert not PasswordHasher().check_needs_rehash(cred.password_hash)


@pytest.mark.item("EC-A05")
def test_b2_user_cannot_see_b3(seeded: Session, platform: Platform) -> None:
    now = utcnow()
    signed = service.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.5", now)
    principal = service.principal_for(seeded, signed.session)
    b3 = _branch(seeded, "B3")
    assert [b.code for b in org.list_branches(seeded, principal)] == ["B2"]
    with pytest.raises(NotFoundError):
        org.get_branch(seeded, principal, b3.id)
    with pytest.raises(PermissionDeniedError):
        service.switch_branch(seeded, signed.session, b3.id)


@pytest.mark.item("M01.1")
def test_front_desk_cannot_edit_branches_or_staff(seeded: Session, platform: Platform) -> None:
    signed = service.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.5", utcnow())
    principal = service.principal_for(seeded, signed.session)
    with pytest.raises(PermissionDeniedError):
        org.list_users(seeded, principal)
    with pytest.raises(PermissionDeniedError):
        org.create_branch(
            seeded, principal, org.BranchInput(code="B9", name="New", kind="collection_centre")
        )


# Through the web


def _sign_in(client: TestClient, username: str) -> None:
    page = client.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert token is not None
    r = client.post(
        "/login",
        data={"username": username, "password": DEMO_PASSWORD, "csrf_token": token.group(1)},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


@pytest.mark.item("EC-A03")
def test_sign_in_sets_a_hardened_cookie(seeded: Session, db_client: TestClient) -> None:
    _sign_in(db_client, "anil")
    cookie = next(c for c in db_client.cookies.jar if c.name == session_cookie())
    assert cookie.name.startswith("__Host-")
    assert cookie.secure
    assert cookie.has_nonstandard_attr("HttpOnly")
    assert db_client.get("/").status_code == 200


@pytest.mark.item("M01.1")
def test_front_desk_gets_403_on_admin_pages(seeded: Session, db_client: TestClient) -> None:
    _sign_in(db_client, "priya")
    assert db_client.get("/admin/users").status_code == 403
    assert db_client.get("/admin/branches").status_code == 200


@pytest.mark.item("M02")
def test_admin_sees_every_branch(seeded: Session, db_client: TestClient) -> None:
    _sign_in(db_client, "anil")
    page = db_client.get("/admin/branches")
    assert page.status_code == 200
    for code in ("MAIN", "B2", "B3"):
        assert code in page.text


@pytest.mark.item("M02")
@pytest.mark.item("M01.1")
@pytest.mark.parametrize(
    ("url", "message"),
    [("/admin/branches", "Enter the branch name."), ("/admin/users", "Enter the full name.")],
)
def test_an_empty_form_shows_the_problems_on_the_page(
    seeded: Session, db_client: TestClient, url: str, message: str
) -> None:
    _sign_in(db_client, "anil")
    token = re.search(r'name="csrf_token" value="([^"]+)"', db_client.get(url).text)
    assert token is not None
    r = db_client.post(url, data={"csrf_token": token.group(1)}, follow_redirects=False)
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("text/html") and message in r.text


@pytest.mark.item("W16")
def test_readyz_ok_on_migrated_database(db_client: TestClient) -> None:
    r = db_client.get("/readyz")
    assert r.status_code == 200, r.json()
    assert r.json()["checks"] == {"database": "ok", "migrations": "ok", "disk": "ok"}
