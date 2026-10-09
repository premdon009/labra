"""Shared fixtures.

Tests that need Postgres use the `db`, `pg_engine` or `db_client` fixtures and are marked
`db` automatically. Without Docker they are skipped with the reason "Docker not reachable",
and `scripts/ci_local.sh` reports the test stage as WARN (unchecked), never PASS.
"""

import os
from collections.abc import Iterator
from datetime import date
from functools import cache

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from labra.core.config import get_settings
from labra.core.db import get_session
from labra.core.registry import Platform, use_platform
from tests.fakes import fake_platform

DB_FIXTURES = {"pg_engine", "db", "db_client", "seeded"}
SKIP_REASON = "Docker not reachable"
POSTGRES_IMAGE = os.environ.get("LABRA_TEST_POSTGRES_IMAGE", "postgres:18")


@cache
def docker_reachable() -> bool:
    try:
        import docker

        docker.from_env(timeout=5).ping()
    except Exception:  # noqa: BLE001  any failure means "can't run db tests here"
        return False
    return True


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if DB_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.db)
        if item.get_closest_marker("db") and not docker_reachable():
            item.add_marker(pytest.mark.skip(reason=SKIP_REASON))


@pytest.fixture(autouse=True)
def _test_settings(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory):
    monkeypatch.setenv("LABRA_FILES_DIR", str(tmp_path_factory.getbasetemp()))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def platform() -> Iterator[Platform]:
    p = fake_platform()
    use_platform(p)
    yield p
    use_platform(None)


@pytest.fixture
def app(platform: Platform) -> FastAPI:
    from labra.app import create_app

    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """No database: for routes that never reach one."""
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    from testcontainers.postgres import PostgresContainer

    from labra.core.migrate import alembic_config

    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as pg:
        engine = create_engine(pg.get_connection_url())
        from alembic import command

        cfg = alembic_config()
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        yield engine
        engine.dispose()


@pytest.fixture
def db(pg_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after the test, even if the code commits."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            trans.rollback()


@pytest.fixture
def seeded(db: Session, platform: Platform) -> Session:
    """The demo cast (§1e): MAIN, B2 and B3, with anil, priya, suresh, meera and b3desk."""
    from labra.seed import seed

    seed(db, platform.identity, SEED_DAY)
    return db


SEED_DAY = date(2026, 10, 9)


@pytest.fixture
def db_client(app: FastAPI, db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app, base_url="https://testserver") as c:
        yield c
    app.dependency_overrides.clear()
