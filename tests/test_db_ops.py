"""The run log of the scheduled jobs against real Postgres."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from labra.core.errors import ValidationFailedError
from labra.core.ids import utcnow
from labra.ops.models import KINDS
from labra.ops.service import DETAIL_MAX, last_runs, record_run


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
