"""The run log of the scheduled jobs against real Postgres."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from labra.cli import main
from labra.core import audit
from labra.core.config import get_settings
from labra.core.db import get_engine
from labra.core.errors import ValidationFailedError
from labra.core.ids import utcnow
from labra.core.registry import Platform
from labra.ops.models import KINDS
from labra.ops.service import DETAIL_MAX, last_runs, record_run
from tests.fakes import RecordingHeartbeat


@pytest.mark.item("M16")
def test_last_runs_names_the_newest_run_and_the_newest_good_one(db: Session) -> None:
    now = utcnow()
    good = record_run(db, "backup", now - timedelta(hours=1), ok=True, snapshot="drive:1a2b3c4d")
    failed = record_run(db, "backup", now - timedelta(minutes=15), ok=False, detail="USB missing")
    drill = record_run(db, "drill", now - timedelta(days=3), ok=True)

    runs = last_runs(db)
    assert set(runs) == set(KINDS)
    assert runs["backup"].last == failed
    assert runs["backup"].last_ok == good
    assert runs["drill"].last == runs["drill"].last_ok == drill
    assert runs["verify"].last is None
    assert runs["verify"].last_ok is None


@pytest.mark.item("M16")
def test_a_run_row_is_never_changed(db: Session) -> None:
    record_run(db, "verify", utcnow(), ok=True)
    for statement in ("update ops_run set ok = false", "delete from ops_run", "truncate ops_run"):
        with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
            db.execute(text(statement))


@pytest.mark.item("M16")
def test_a_run_of_an_unknown_job_is_refused_here_and_by_the_database(db: Session) -> None:
    with pytest.raises(ValidationFailedError, match="Unknown job"):
        record_run(db, "cleanup", utcnow(), ok=True)
    # The backup container writes with psql, past the service, so the table checks too.
    with pytest.raises(DBAPIError, match="ck_ops_run_kind"), db.begin_nested():
        db.execute(
            text(
                "insert into ops_run (kind, started_at, finished_at, ok)"
                " values ('cleanup', now(), now(), true)"
            )
        )


@pytest.mark.item("M16")
def test_a_long_detail_is_cut_to_fit(db: Session) -> None:
    run = record_run(db, "disk", utcnow(), ok=False, detail="x" * (DETAIL_MAX + 500))
    assert run.detail is not None
    assert len(run.detail) == DETAIL_MAX
    assert run.detail.endswith("…")


@pytest.mark.item("W07")
def test_audit_verify_checks_a_copy_by_name_and_leaves_the_ping_to_the_drill(
    pg_engine: Engine,
    committed_engine: Engine,
    platform: Platform,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with Session(committed_engine) as copy:
        audit.record(copy, "drill.test", "branch")
        audit.record(copy, "drill.test", "branch")
        copy.commit()
    url = pg_engine.url.render_as_string(hide_password=False)
    monkeypatch.setenv("LABRA_DATABASE_URL", url)
    get_settings.cache_clear()
    with pytest.raises(SystemExit) as done:
        main(["audit", "verify", "--database", str(committed_engine.url.database)])
    assert done.value.code == 0
    assert "Audit log intact: 2 rows checked." in capsys.readouterr().out
    assert isinstance(platform.heartbeat, RecordingHeartbeat)
    assert platform.heartbeat.pings == []


# The nightly audit check and the disk alert, as the host timers run them.


@pytest.fixture
def labra_db(
    committed_engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Engine]:
    """`labra` commands pointed at a database of their own, with the files folder in tmp_path."""
    monkeypatch.setenv(
        "LABRA_DATABASE_URL", committed_engine.url.render_as_string(hide_password=False)
    )
    monkeypatch.setenv("LABRA_FILES_DIR", str(tmp_path))
    monkeypatch.delenv("LABRA_EXPORT_DIR", raising=False)
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield committed_engine
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _runs(engine: Engine, kind: str) -> list[tuple[bool, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("select ok, detail from ops_run where kind = :kind order by id"), {"kind": kind}
        )
        return [(row.ok, row.detail) for row in rows]


def _labra(*args: str) -> int:
    with pytest.raises(SystemExit) as done:
        main(list(args))
    return int(done.value.code or 0)


def _disk(monkeypatch: pytest.MonkeyPatch, used: int, free: int) -> None:
    monkeypatch.setattr(
        "labra.core.health.shutil.disk_usage",
        lambda _: SimpleNamespace(total=used + free + 500, used=used, free=free),
    )


@pytest.mark.item("EC-B06")
def test_the_nightly_audit_check_logs_its_run_and_pings(
    labra_db: Engine, platform: Platform, capsys: pytest.CaptureFixture[str]
) -> None:
    with Session(labra_db) as db:
        audit.record(db, "nightly.test", "branch")
        db.commit()
    assert _labra("audit", "verify") == 0
    assert "Audit log intact: 1 rows checked." in capsys.readouterr().out
    assert _runs(labra_db, "verify") == [(True, "1 rows checked")]
    assert isinstance(platform.heartbeat, RecordingHeartbeat)
    assert platform.heartbeat.pings == [("audit_verify", True, "1 rows checked")]


@pytest.mark.item("EC-D05")
@pytest.mark.parametrize(
    ("used", "ok", "shown"),
    [(7_999, True, "79% used"), (8_000, False, "80% used"), (9_500, False, "95% used")],
)
def test_the_disk_alert_starts_at_80_percent_used(
    labra_db: Engine,
    platform: Platform,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    used: int,
    ok: bool,
    shown: str,
) -> None:
    _disk(monkeypatch, used=used, free=10_000 - used)
    assert _labra("check-disk") == (0 if ok else 1)
    out = capsys.readouterr().out
    assert out.startswith("Disk space OK: " if ok else "DISK SPACE LOW: ")
    assert shown in out
    assert ("(the alert is at 80%)" in out) is not ok
    [(logged_ok, detail)] = _runs(labra_db, "disk")
    assert logged_ok is ok and shown in detail
    assert isinstance(platform.heartbeat, RecordingHeartbeat)
    assert [(job, sent_ok) for job, sent_ok, _ in platform.heartbeat.pings] == [("disk", ok)]


@pytest.mark.item("EC-D05")
def test_the_disk_alert_level_can_be_raised(
    labra_db: Engine, platform: Platform, monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, used=8_500, free=1_500)
    assert _labra("check-disk", "--percent", "90") == 0
    assert _labra("check-disk", "--percent", "100") == 2


@pytest.mark.item("EC-D05")
def test_one_disk_is_reported_once_and_a_missing_folder_fails(
    labra_db: Engine,
    platform: Platform,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "export").mkdir()
    monkeypatch.setenv("LABRA_EXPORT_DIR", str(tmp_path / "export"))
    get_settings.cache_clear()
    assert _labra("check-disk") == 0
    assert capsys.readouterr().out.count("% used") == 1
    monkeypatch.setenv("LABRA_EXPORT_DIR", str(tmp_path / "unmounted"))
    get_settings.cache_clear()
    assert _labra("check-disk") == 1
    assert "unmounted: can't be read" in capsys.readouterr().out
