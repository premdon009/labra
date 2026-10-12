"""Core tables against real Postgres: migrations, audit log, numbering, settings, files,
outbox and the seed."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from labra.core import audit, lab_settings, outbox
from labra.core.db import Base
from labra.core.errors import ConfigError, NotFoundError, ValidationFailedError
from labra.core.files import read_file, save_file
from labra.core.migrate import current_revisions, head_revisions
from labra.core.models import AuditLog, NumberSeries
from labra.core.numbering import next_number
from labra.core.registry import Platform
from labra.org.models import AppUser, Branch
from labra.seed import seed

# Migrations


@pytest.mark.item("W04")
def test_migrations_match_models(pg_engine: Engine) -> None:
    with pg_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert current_revisions(conn) == head_revisions()
    assert diff == []


# Audit log


@pytest.mark.item("M15")
def test_audit_chain_verifies(db: Session) -> None:
    for i in range(3):
        audit.record(db, "branch.update", "branch", str(i), {"step": i})
    result = audit.verify(db)
    assert result.ok
    assert result.checked >= 3


@pytest.mark.item("M15")
@pytest.mark.parametrize(
    "statement",
    [
        "update audit_log set action = 'changed'",
        "delete from audit_log",
        "truncate audit_log",
    ],
)
def test_audit_log_is_append_only(db: Session, statement: str) -> None:
    audit.record(db, "branch.create", "branch", "1")
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(text(statement))


@pytest.mark.item("EC-C01")
@pytest.mark.parametrize(
    "statement",
    [
        "update consent_notice set body_text = 'changed'",
        "delete from consent_notice",
        "truncate consent_notice cascade",
    ],
)
def test_consent_notice_is_append_only(db: Session, statement: str) -> None:
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(text(statement))


@pytest.mark.item("M15")
def test_audit_tamper_detected(db: Session) -> None:
    audit.record(db, "setting.change", "setting", "a", {"value": 1})
    audit.record(db, "setting.change", "setting", "b", {"value": 2})
    db.flush()
    target = db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert target is not None
    # Someone with superuser rights switches the guard off and edits a row.
    db.execute(text("alter table audit_log disable trigger audit_log_no_change"))
    db.execute(
        text("update audit_log set detail = '{\"value\": 99}' where id = :id"), {"id": target.id}
    )
    db.expire_all()
    result = audit.verify(db)
    assert not result.ok
    assert result.first_bad_id == target.id


# Numbering


def _series(db: Session, doc_type: str, fmt: str, fin_year: int, branch_id=None) -> None:
    db.add(NumberSeries(branch_id=branch_id, doc_type=doc_type, format=fmt, fin_year=fin_year))
    db.flush()


@pytest.mark.item("W04")
def test_numbers_are_sequential_and_reset_each_year(db: Session) -> None:
    _series(db, "visit", "{BR}/V/{FY2}/{SEQ:5}", 2026)
    day = date(2027, 3, 31)
    assert next_number(db, "visit", None, "B2", day) == "B2/V/2627/00001"
    assert next_number(db, "visit", None, "B2", day) == "B2/V/2627/00002"
    assert next_number(db, "visit", None, "B2", date(2027, 4, 1)) == "B2/V/2728/00001"


@pytest.mark.item("W04")
@pytest.mark.item("M03")
def test_patient_series_does_not_reset_on_1_april(db: Session) -> None:
    _series(db, "patient", "{BR}/P/{SEQ:6}", 2026)
    assert next_number(db, "patient", None, "B2", date(2027, 3, 31)) == "B2/P/000001"
    assert next_number(db, "patient", None, "B2", date(2027, 4, 1)) == "B2/P/000002"


@pytest.mark.item("W04")
def test_missing_series_refused(db: Session) -> None:
    with pytest.raises(NotFoundError):
        next_number(db, "refund", None, "B2", date(2026, 10, 9))


@pytest.mark.item("W04")
def test_overlong_gst_number_refused(db: Session) -> None:
    _series(db, "bos", "{BR}/BS/{FY}/{SEQ:6}", 2026)
    with pytest.raises(ConfigError):
        next_number(db, "bos", None, "MAIN", date(2026, 10, 9))


@pytest.mark.item("W04")
def test_parallel_numbers_have_no_gaps_or_repeats(pg_engine: Engine) -> None:
    doc_type = f"test_{uuid.uuid4().hex[:8]}"
    day = date(2026, 10, 9)
    with Session(pg_engine) as s:
        _series(s, doc_type, "{SEQ:4}", 2026)
        s.commit()

    def issue(_: int) -> str:
        with Session(pg_engine) as s:
            number = next_number(s, doc_type, None, "B2", day)
            s.commit()
            return number

    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            numbers = list(pool.map(issue, range(20)))
        assert sorted(numbers) == [f"{n:04d}" for n in range(1, 21)]
    finally:
        with Session(pg_engine) as s:
            s.execute(delete(NumberSeries).where(NumberSeries.doc_type == doc_type))
            s.commit()


# Settings


@pytest.mark.item("W04")
def test_branch_setting_overrides_lab_setting(db: Session) -> None:
    branch = Branch(code="T1", name="Test Branch", kind="collection_centre")
    other = Branch(code="T2", name="Other Branch", kind="collection_centre")
    db.add_all([branch, other])
    db.flush()
    key = "visit.default_tat_hours"
    default = lab_settings.DEFINITIONS[key].default
    assert lab_settings.get_value(db, key, branch.id) == default
    lab_settings.set_value(db, key, "48", None)
    lab_settings.set_value(db, key, "6", None, branch.id)
    assert lab_settings.get_value(db, key) == 48
    assert lab_settings.get_value(db, key, branch.id) == 6
    assert lab_settings.get_value(db, key, other.id) == 48
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity == "setting")).all()
    assert actions.count("setting.change") >= 2


@pytest.mark.item("W04")
def test_lab_wide_setting_refuses_branch_value(db: Session) -> None:
    with pytest.raises(ValidationFailedError):
        lab_settings.set_value(db, "lab.display_name", "X", None, uuid.uuid4())


# Files


@pytest.mark.item("W04")
def test_file_round_trip_and_damage_detected(db: Session, platform: Platform) -> None:
    stored = save_file(
        db, platform.filestore, b"%PDF synthetic", "report.pdf", "application/pdf", None
    )
    meta, data = read_file(db, platform.filestore, stored.id)
    assert data == b"%PDF synthetic"
    assert meta.filename == "report.pdf"
    blobs = platform.filestore.blobs  # type: ignore[attr-defined]
    blobs[stored.storage_key] = b"changed on disk"
    with pytest.raises(NotFoundError):
        read_file(db, platform.filestore, stored.id)


# Outbox


@pytest.mark.item("W04")
def test_outbox_claim_done_and_retry(db: Session) -> None:
    done = outbox.emit(db, "test.done", {"id": "1"})
    failed = outbox.emit(db, "test.failed", {"id": "2"})
    claimed = {e.id for e in outbox.claim(db)}
    assert {done.id, failed.id} <= claimed
    outbox.mark_done(done)
    outbox.mark_failed(failed, "synthetic error")
    db.flush()
    again = {e.id for e in outbox.claim(db)}
    assert done.id not in again
    assert failed.id not in again  # waits before the retry
    assert failed.attempts == 1


# Seed


@pytest.mark.item("W05")
def test_seed_is_idempotent(seeded: Session, platform: Platform) -> None:
    count = len(seeded.scalars(select(AppUser)).all())
    seed(seeded, platform.identity, date(2026, 10, 9))
    assert len(seeded.scalars(select(AppUser)).all()) == count
    codes = set(seeded.scalars(select(Branch.code)))
    assert {"MAIN", "B2", "B3"} <= codes


@pytest.mark.item("W05")
def test_seed_refuses_a_real_database(db: Session, platform: Platform) -> None:
    db.add(AppUser(username="someone.real", full_name="Not In The Cast"))
    db.flush()
    with pytest.raises(ConfigError):
        seed(db, platform.identity, date(2026, 10, 9))
