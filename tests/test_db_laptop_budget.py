"""The laptop budgets that can be checked in process: patient search over about two years of
registrations. The whole stack is measured by scripts/laptop_budget.py."""

import importlib.util
import statistics
import sys
import time
from pathlib import Path
from types import ModuleType

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.core.registry import Platform
from labra.patients.models import Patient
from tests.frontdesk import as_user, register, sign_in

ROOT = Path(__file__).resolve().parent.parent
PATIENTS = 50_000


def _script() -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))  # it imports runtime_bench beside it
    try:
        spec = importlib.util.spec_from_file_location(
            "laptop_budget", ROOT / "scripts" / "laptop_budget.py"
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    return module


budget = _script()


def _run_sql(db: Session, sql: str) -> None:
    """The script's SQL as psql sends it: several statements in one go, in the test's
    transaction so it is rolled back after."""
    driver = db.connection().connection.driver_connection
    assert isinstance(driver, psycopg.Connection)
    driver.execute(sql)  # pyright: ignore[reportArgumentType, reportCallIssue]


@pytest.mark.item("EC-F01")
def test_the_fill_adds_synthetic_patients_once(seeded: Session) -> None:
    _run_sql(seeded, budget.fill_sql(500))
    _run_sql(seeded, budget.fill_sql(500))
    numbers = seeded.scalars(select(Patient.patient_no).order_by(Patient.patient_no)).all()
    assert len(numbers) == 500
    assert numbers[0] == "PERF-000001"
    assert all(p.startswith("PERF-") for p in numbers)
    names = seeded.scalars(select(func.count(func.distinct(Patient.full_name)))).one()
    assert names > 400


@pytest.mark.item("EC-F01")
def test_the_fill_refuses_a_database_with_patients_of_its_own(
    seeded: Session, platform: Platform
) -> None:
    register(seeded, as_user(seeded, platform, "priya"))
    seeded.flush()
    with pytest.raises(psycopg.errors.RaiseException, match="patients of its own"):
        _run_sql(seeded, budget.fill_sql(10))


@pytest.mark.item("EC-F01")
@pytest.mark.serial
@pytest.mark.parametrize("username", ["anil", "priya"])
def test_patient_search_stays_within_300_ms_over_two_years_of_patients(
    seeded: Session, platform: Platform, db_client: TestClient, username: str
) -> None:
    _run_sql(seeded, budget.fill_sql(PATIENTS))
    sign_in(db_client, username)
    for q in budget.SEARCHES:
        took = []
        for _ in range(5):
            started = time.perf_counter()
            response = db_client.get("/frontdesk/patients", params={"q": q})
            took.append(time.perf_counter() - started)
            assert response.status_code == 200, q
        # The median, so one slow round on a busy CI runner doesn't fail it.
        assert statistics.median(took) < 0.3, f"{q!r}: {[round(t * 1000) for t in took]} ms"
