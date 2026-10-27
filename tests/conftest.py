"""Shared fixtures.

Tests that need Postgres use the `db`, `pg_engine` or `db_client` fixtures and are marked
`db` automatically. They run on a throwaway Postgres container (any runtime with a Docker-API
socket: Docker, or Podman via DOCKER_HOST), or on an existing database named in
LABRA_TEST_DATABASE_URL. With neither they are skipped with the reason "no Postgres for tests",
and `scripts/ci_local.sh` reports the test stage as WARN (unchecked), never PASS.

Under pytest-xdist each worker has its own: its own container, or its own database on the
server named in LABRA_TEST_DATABASE_URL (`labra_test` becomes `labra_gw0_test`, and so on).
"""

import gc
import os
import uuid
import warnings
from collections.abc import Iterator
from datetime import date
from functools import cache

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from labra.core.config import get_settings
from labra.core.db import get_session
from labra.core.registry import Platform, use_platform
from tests.fakes import fake_platform

DB_FIXTURES = {"pg_engine", "db", "db_client", "seeded", "committed_engine"}
SKIP_REASON = "no Postgres for tests"
POSTGRES_IMAGE = os.environ.get("LABRA_TEST_POSTGRES_IMAGE", "docker.io/library/postgres:18")
TEST_DATABASE_URL = os.environ.get("LABRA_TEST_DATABASE_URL", "")


def checked_test_url(url: str) -> str:
    """The tests create tables in this database and write to it, so only a database named for
    tests is accepted; a slip can never point them at a lab's data."""
    parsed = make_url(url)
    if not (parsed.database or "").endswith("_test"):
        raise pytest.UsageError(
            f"LABRA_TEST_DATABASE_URL must name a database ending in _test, "
            f"not {parsed.database!r}."
        )
    return parsed.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def worker_database_url(url: str, worker: str) -> str:
    """The database a pytest-xdist worker uses: `<name>_<worker>_test`, so workers never share
    tables or advisory locks. Without a worker (a serial run) it's the database named."""
    checked = checked_test_url(url)
    if not worker:
        return checked
    parsed = make_url(checked)
    name = (parsed.database or "").removesuffix("_test")
    return checked_test_url(
        parsed.set(database=f"{name}_{worker}_test").render_as_string(hide_password=False)
    )


def create_database_if_missing(url: str, server_url: str) -> None:
    """Create the database in `url` through `server_url` (another database on the same server)."""
    name = make_url(url).database
    admin = create_engine(server_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(text("select 1 from pg_database where datname = :n"), {"n": name})
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()


@cache
def postgres_available() -> bool:
    if TEST_DATABASE_URL:
        checked_test_url(TEST_DATABASE_URL)
        return True
    # docker-py leaves its socket open when the connection fails. Collect it here, with the
    # warning off, rather than in whichever test the garbage collector next runs in.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        try:
            import docker

            docker.from_env(timeout=5).ping()
            ok = True
        except Exception:  # noqa: BLE001  any failure means "can't run db tests here"
            ok = False
        gc.collect()
    return ok


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if DB_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.db)
        if item.get_closest_marker("db") and not postgres_available():
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


def migrated(url: str) -> Engine:
    from alembic import command

    from labra.core.migrate import alembic_config

    engine = create_engine(url)
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    return engine


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    from testcontainers.community.postgres import PostgresContainer

    if TEST_DATABASE_URL:
        server = checked_test_url(TEST_DATABASE_URL)
        url = worker_database_url(server, os.environ.get("PYTEST_XDIST_WORKER", ""))
        if url != server:
            create_database_if_missing(url, server)
        engine = migrated(url)
        yield engine
        engine.dispose()
        return
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as pg:
        engine = migrated(pg.get_connection_url())
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


NO_CREATEDB = "no CREATEDB for concurrency test"


@pytest.fixture
def committed_engine(pg_engine: Engine) -> Iterator[Engine]:
    """A database of its own for tests where several connections must see each other's
    committed work. Issued bills and audit rows can't be deleted, so the whole database is
    dropped afterwards. Skipped when the test role may not create databases."""
    name = f"labra_conc_{uuid.uuid4().hex[:8]}_test"
    url = checked_test_url(pg_engine.url.set(database=name).render_as_string(hide_password=False))
    admin = pg_engine.execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        allowed = conn.scalar(
            text("select rolcreatedb or rolsuper from pg_roles where rolname = current_user")
        )
        if not allowed:
            pytest.skip(NO_CREATEDB)
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = None
    try:
        engine = migrated(url)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


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
