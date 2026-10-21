"""Changing my own password: the current one first, then a new one twice, against real Postgres."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.auth import service as auth
from labra.auth.models import LoginAttempt, UserSession
from labra.core.errors import AuthenticationError
from labra.core.ids import utcnow
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.org.models import AppUser
from labra.seed import DEMO_PASSWORD

NEW_PASSWORD = "brand-new-password-7"
URL = "/account/password"


def _token(html: str) -> str:
    token = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert token is not None
    return token.group(1)


def _sign_in(client: TestClient, username: str, password: str = DEMO_PASSWORD) -> int:
    client.cookies.clear()
    form = {
        "username": username,
        "password": password,
        "csrf_token": _token(client.get("/login").text),
    }
    return client.post("/login", data=form, follow_redirects=False).status_code


def _change(client: TestClient, current: str, new: str, again: str | None = None):
    form = {
        "current": current,
        "new": new,
        "again": new if again is None else again,
        "csrf_token": _token(client.get(URL).text),
    }
    return client.post(URL, data=form, follow_redirects=False)


def _failures(db: Session, username: str) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                LoginAttempt.username == username, LoginAttempt.ok.is_(False)
            )
        )
        or 0
    )


@pytest.mark.item("M27")
def test_a_new_password_replaces_the_old_and_ends_my_other_sessions(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    other = auth.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.9", utcnow())
    assert _sign_in(db_client, "priya") == 303
    page = db_client.get(URL)
    assert page.status_code == 200
    assert 'name="current"' in page.text
    assert 'autocomplete="new-password"' in page.text

    r = _change(db_client, DEMO_PASSWORD, NEW_PASSWORD)
    assert r.status_code == 303
    assert r.headers["location"] == f"{URL}?changed=1"
    assert "Your password is changed" in db_client.get(r.headers["location"]).text
    # This browser stays signed in; the other one is signed out.
    assert db_client.get("/").status_code == 200
    seeded.refresh(other.session)
    assert other.session.ended_at is not None
    live = seeded.scalar(
        select(func.count()).where(
            UserSession.user_id == other.session.user_id, UserSession.ended_at.is_(None)
        )
    )
    assert live == 1

    user = seeded.scalar(select(AppUser).where(AppUser.username == "priya"))
    assert user is not None
    actions = list(
        seeded.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == str(user.id)).order_by(AuditLog.id)
        )
    )
    assert actions[-1] == "user.password_change"
    assert not platform.identity.verify_password(seeded, user.id, DEMO_PASSWORD)
    assert platform.identity.verify_password(seeded, user.id, NEW_PASSWORD)
    with pytest.raises(AuthenticationError):
        auth.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.8", utcnow())
    assert _sign_in(db_client, "priya", NEW_PASSWORD) == 303


@pytest.mark.item("M27")
def test_a_wrong_current_password_counts_towards_the_lockout(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    assert _sign_in(db_client, "suresh") == 303
    for tries in range(1, auth.LOCKOUT_FAILURES + 1):
        r = _change(db_client, "not-my-password", NEW_PASSWORD)
        assert r.status_code == 422
        assert "isn&#39;t your current password" in r.text
        assert _failures(seeded, "suresh") == tries
    # Locked: even the right password is refused now, here and at the sign-in screen.
    r = _change(db_client, DEMO_PASSWORD, NEW_PASSWORD)
    assert r.status_code == 422
    assert "Too many failed attempts" in r.text
    user = seeded.scalar(select(AppUser).where(AppUser.username == "suresh"))
    assert user is not None
    assert platform.identity.verify_password(seeded, user.id, DEMO_PASSWORD)
    assert _sign_in(db_client, "suresh") == 401
    assert (
        "auth.locked"
        in seeded.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(user.id))).all()
    )


@pytest.mark.item("M27")
@pytest.mark.parametrize(
    ("new", "again", "field", "message"),
    [
        ("short", "short", "new", "at least 10 characters"),
        (NEW_PASSWORD, NEW_PASSWORD + "x", "again", "don&#39;t match"),
        (DEMO_PASSWORD, DEMO_PASSWORD, "new", "differ from the current one"),
    ],
)
def test_a_weak_mismatched_or_unchanged_password_is_refused(
    seeded: Session,
    platform: Platform,
    db_client: TestClient,
    new: str,
    again: str,
    field: str,
    message: str,
) -> None:
    assert _sign_in(db_client, "meera") == 303
    r = _change(db_client, DEMO_PASSWORD, new, again)
    assert r.status_code == 422
    assert re.search(rf'id="e-{field}">[^<]*{message}', r.text), r.text
    user = seeded.scalar(select(AppUser).where(AppUser.username == "meera"))
    assert user is not None
    assert platform.identity.verify_password(seeded, user.id, DEMO_PASSWORD)
    assert _failures(seeded, "meera") == 0
    assert "user.password_change" not in seeded.scalars(select(AuditLog.action)).all()


@pytest.mark.item("M27")
def test_signed_out_the_page_sends_me_to_sign_in(seeded: Session, db_client: TestClient) -> None:
    db_client.cookies.clear()
    r = db_client.get(URL, headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=%2Faccount%2Fpassword"


@pytest.mark.item("M27")
def test_the_header_links_to_my_password(seeded: Session, db_client: TestClient) -> None:
    assert _sign_in(db_client, "b3desk") == 303
    assert re.search(r'<a [^>]*href="/account/password"[^>]*>Password</a>', db_client.get("/").text)
