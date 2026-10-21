"""`labra set-password`: the way back in when the only administrator forgets their password."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from labra.auth.models import UserSession
from labra.auth.service import login
from labra.cli import main
from labra.core.config import get_settings
from labra.core.db import get_engine
from labra.core.ids import utcnow
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.org.models import AppUser

FIRST = "first-password-1"
NEW = "second-password-2"


@pytest.fixture
def labra_db(committed_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    """`labra` commands pointed at a database of their own, with a main lab and an admin."""
    monkeypatch.setenv(
        "LABRA_DATABASE_URL", committed_engine.url.render_as_string(hide_password=False)
    )
    get_settings.cache_clear()
    get_engine.cache_clear()
    _typed(monkeypatch, FIRST, FIRST)
    assert _labra("add-branch", "--code", "MAIN", "--name", "Main lab") == 0
    assert _labra("create-admin", "--username", "admin", "--full-name", "Admin User") == 0
    yield committed_engine
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _typed(monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
    """What is typed at the password prompts, in order."""
    queue = list(answers)
    monkeypatch.setattr("labra.cli.getpass.getpass", lambda _prompt: queue.pop(0))


def _labra(*args: str) -> int:
    with pytest.raises(SystemExit) as done:
        main(list(args))
    return int(done.value.code or 0)


def _admin(db: Session) -> AppUser:
    return db.scalars(select(AppUser).where(AppUser.username == "admin")).one()


@pytest.mark.item("EC-L03")
def test_a_new_password_works_the_old_one_doesnt_and_sessions_end(
    labra_db: Engine,
    platform: Platform,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with Session(labra_db) as db:
        login(db, platform.identity, "admin", FIRST, "192.0.2.10", utcnow())
    _typed(monkeypatch, NEW, NEW)
    capsys.readouterr()

    assert _labra("set-password", "--username", " Admin ") == 0
    assert "Password changed for admin." in capsys.readouterr().out
    with Session(labra_db) as db:
        admin = _admin(db)
        assert platform.identity.verify_password(db, admin.id, NEW)
        assert not platform.identity.verify_password(db, admin.id, FIRST)
        sessions = db.scalars(select(UserSession).where(UserSession.user_id == admin.id)).all()
        assert sessions
        assert all(s.ended_at is not None for s in sessions)
        reset = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "user.password_reset", AuditLog.entity_id == str(admin.id)
            )
        ).one()
        assert reset.detail == {"via": "cli"}


@pytest.mark.item("EC-L03")
@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ((NEW, "something-else-3"), "The passwords don't match."),
        (("short", "short"), "10 characters"),
    ],
)
def test_a_refused_password_changes_nothing(
    labra_db: Engine,
    platform: Platform,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    answers: tuple[str, str],
    message: str,
) -> None:
    _typed(monkeypatch, *answers)
    capsys.readouterr()
    assert _labra("set-password", "--username", "admin") == 1
    assert message in capsys.readouterr().out
    with Session(labra_db) as db:
        assert platform.identity.verify_password(db, _admin(db).id, FIRST)


@pytest.mark.item("EC-L03")
def test_an_unknown_or_switched_off_user_is_refused_before_any_prompt(
    labra_db: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _typed(monkeypatch)  # any prompt would fail on the empty queue
    capsys.readouterr()
    assert _labra("set-password", "--username", "nobody") == 1
    assert "There is no user nobody." in capsys.readouterr().out

    with Session(labra_db) as db:
        db.execute(update(AppUser).where(AppUser.username == "admin").values(can_login=False))
        db.commit()
    assert _labra("set-password", "--username", "admin") == 1
    assert "can't sign in at all" in capsys.readouterr().out
