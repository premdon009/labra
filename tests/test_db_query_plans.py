"""EC-F02: the main list and search screens read through an index, never the whole table.
Each test runs the query the screen runs, catches the statement on its way to Postgres and
asks for its plan with sequential scans switched off, so a missing index shows as a
`Seq Scan` on the table."""

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from labra.billing import service as billing
from labra.core.registry import Platform
from labra.patients import service as patients
from labra.results import worklist
from labra.seed import seed
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, register
from tests.test_db_lab_entry import _approve, _in_lab


@contextmanager
def _caught(db: Session) -> Iterator[list[tuple[str, Any]]]:
    """Every SELECT the block sends, with its parameters."""
    connection = db.connection()
    sent: list[tuple[str, Any]] = []

    def grab(_c: object, _cur: object, statement: str, parameters: Any, *_: object) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            sent.append((statement, parameters))

    event.listen(connection, "before_cursor_execute", grab)
    try:
        yield sent
    finally:
        event.remove(connection, "before_cursor_execute", grab)


def _plan(db: Session, run: Callable[[], object], table: str) -> str:
    """The plan of the statement `run` sends that reads `table`."""
    db.execute(text("set local enable_seqscan = off"))
    with _caught(db) as sent:
        run()
    statements = [s for s in sent if re.search(rf"\bFROM {table}\b", s[0])]
    assert statements, f"no statement read {table}"
    statement, parameters = statements[0]
    rows = db.connection().exec_driver_sql("EXPLAIN " + statement, parameters)
    return "\n".join(r[0] for r in rows)


@pytest.fixture
def lab(db: Session, platform: Platform) -> Session:
    """The demo cast and the starter catalog, a lipid panel received at the main lab."""
    seed(db, platform.identity, SEED_DAY, with_catalog=True)
    _approve(db, platform, "lipid")
    _in_lab(db, platform)
    return db


def _patients(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    for n in range(20):
        register(seeded, priya, phone=f"98{n:08d}", full_name=f"Kavita Testcase {n}")


def _scans(plan: str, table: str) -> list[str]:
    return re.findall(rf"Seq Scan on {table}\b", plan)


@pytest.mark.item("EC-F02")
def test_a_phone_search_reads_the_phone_indexes(seeded: Session, platform: Platform) -> None:
    _patients(seeded, platform)
    priya = as_user(seeded, platform, "priya")
    plan = _plan(seeded, lambda: patients.find_patients(seeded, priya, "98000", 1), "patient")
    assert not _scans(plan, "patient"), plan
    assert "ix_patient_phone_prefix" in plan, plan
    assert "ix_patient_alt_phone_prefix" in plan, plan


@pytest.mark.item("EC-F02")
def test_a_name_search_reads_the_trigram_index(seeded: Session, platform: Platform) -> None:
    _patients(seeded, platform)
    priya = as_user(seeded, platform, "priya")
    plan = _plan(seeded, lambda: patients.find_patients(seeded, priya, "kavta", 1), "patient")
    assert not _scans(plan, "patient"), plan
    assert "ix_patient_full_name_trgm" in plan, plan


@pytest.mark.item("EC-F02")
def test_patients_by_visit_date_read_the_visit_date_index(
    seeded: Session, platform: Platform
) -> None:
    _patients(seeded, platform)
    priya = as_user(seeded, platform, "priya")
    day = SEED_DAY

    def run() -> object:
        return patients.find_patients(
            seeded, priya, "", 1, visited_from=day - timedelta(days=7), visited_to=day
        )

    plan = _plan(seeded, run, "patient")
    assert not _scans(plan, "visit"), plan
    assert "ix_visit_branch_visited" in plan, plan


@pytest.mark.item("EC-F02")
def test_the_bill_list_by_date_reads_the_bill_date_index(lab: Session, platform: Platform) -> None:
    priya = as_user(lab, platform, "priya")

    def run() -> object:
        return billing.bill_page(lab, priya, 1, SEED_DAY - timedelta(days=7), SEED_DAY)

    plan = _plan(lab, run, "bill")
    assert not _scans(plan, "bill"), plan
    assert "ix_bill_branch_date" in plan, plan


@pytest.mark.item("EC-F02")
def test_the_worklist_reads_the_order_status_index(lab: Session, platform: Platform) -> None:
    suresh = as_user(lab, platform, "suresh")
    plan = _plan(lab, lambda: worklist.work_page(lab, suresh), "order_test")
    assert not _scans(plan, "order_test"), plan
    assert "ix_order_test_perform_branch" in plan, plan
