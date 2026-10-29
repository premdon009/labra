"""The database logins `labra migrate` hands out: what the web app's and the backup job's users
may and may not do, and how Compose gives each container its own."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from labra.core.config import Settings
from labra.core.dbroles import Login, ensure_roles, ensure_roles_from_settings, login_from_url
from labra.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]
RUN = (
    "insert into ops_run (kind, started_at, finished_at, ok) values ('backup', now(), now(), true)"
)


@pytest.fixture
def conn(db: Session) -> Iterator[Connection]:
    """The test database's connection, as a superuser that can make roles; all rolled back."""
    c = db.connection()
    if not c.scalar(text("select rolsuper from pg_roles where rolname = current_user")):
        pytest.skip("the test login can't create roles")
    yield c


def _login(prefix: str) -> Login:
    return Login(f"{prefix}_{uuid.uuid4().hex[:8]}", "pw-" + uuid.uuid4().hex)


def _denied(conn: Connection, statement: str) -> None:
    with pytest.raises(DBAPIError, match=r"permission denied|must be"), conn.begin_nested():
        conn.execute(text(statement))


def _allowed(conn: Connection, statement: str) -> None:
    with conn.begin_nested():
        conn.execute(text(statement))


def _as(conn: Connection, login: Login) -> None:
    conn.execute(text(f'SET ROLE "{login.name}"'))


@pytest.mark.item("W41")
def test_the_app_reads_and_writes_rows_but_cannot_change_the_schema(conn: Connection) -> None:
    app = _login("app")
    ensure_roles(conn, app)
    assert conn.execute(
        text("select rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = :n"),
        {"n": app.name},
    ).one() == (False, False, False)
    _as(conn, app)
    _allowed(conn, "select count(*) from audit_log")
    _allowed(conn, RUN)
    _allowed(conn, "update user_session set ip = ip")
    _allowed(conn, "delete from login_attempt where false")
    _allowed(conn, "select version_num from alembic_version")
    _denied(conn, "update alembic_version set version_num = version_num")
    _denied(conn, "create table planted (id int)")
    _denied(conn, "alter table audit_log disable trigger all")
    _denied(conn, "drop table ops_run")
    _denied(conn, "truncate ops_run")
    _denied(conn, "copy (select 1) to program 'true'")


@pytest.mark.item("W41")
def test_the_backup_job_reads_everything_and_writes_only_the_run_log(conn: Connection) -> None:
    app, backup = _login("app"), _login("backup")
    ensure_roles(conn, app, backup)
    _as(conn, backup)
    _allowed(conn, "select count(*) from audit_log")
    _allowed(conn, "select count(*) from alembic_version")
    _allowed(conn, RUN)
    _denied(conn, "update user_session set ip = ip")
    _denied(conn, "delete from login_attempt")
    _denied(conn, "create table planted (id int)")
    _denied(conn, "copy (select 1) to program 'true'")


@pytest.mark.item("W41")
def test_every_run_puts_a_widened_login_back(conn: Connection) -> None:
    app = _login("app")
    owner = conn.scalar(text("select current_user"))
    conn.execute(text(f'CREATE ROLE "{app.name}" SUPERUSER CREATEDB'))
    conn.execute(text(f'GRANT "{owner}" TO "{app.name}"'))
    ensure_roles(conn, app)
    ensure_roles(conn, app)  # and again: nothing to create the second time
    assert conn.execute(
        text("select rolsuper, rolcreatedb, rolcanlogin from pg_roles where rolname = :n"),
        {"n": app.name},
    ).one() == (False, False, True)
    members = conn.scalar(
        text(
            "select count(*) from pg_auth_members m join pg_roles r on r.oid = m.member "
            "where r.rolname = :n"
        ),
        {"n": app.name},
    )
    assert members == 0


@pytest.mark.item("W41")
def test_the_owner_is_never_handed_out(conn: Connection) -> None:
    owner = conn.scalar(text("select current_user"))
    with pytest.raises(ConfigError, match="must not be the owner"):
        ensure_roles(conn, Login(owner, "x"))
    with pytest.raises(ConfigError, match="must not be the owner"):
        ensure_roles(conn, _login("app"), Login(owner, "x"))
    same = _login("app")
    with pytest.raises(ConfigError, match="different logins"):
        ensure_roles(conn, same, same)
    with pytest.raises(ConfigError, match="reserved"):
        ensure_roles(conn, Login("pg_monitor", "x"))


@pytest.mark.item("W41")
def test_migrate_reads_the_logins_from_their_urls(conn: Connection) -> None:
    app, backup = _login("app"), _login("backup")
    settings = Settings(
        app_database_url=f"postgresql+psycopg://{app.name}:{app.password}@db/labra",  # type: ignore[arg-type]
        backup_database_url=f"postgresql://{backup.name}:{backup.password}@db/labra",  # type: ignore[arg-type]
    )
    assert ensure_roles_from_settings(conn, settings) == [app.name, backup.name]
    assert ensure_roles_from_settings(conn, Settings()) == []


@pytest.mark.item("W41")
def test_a_login_url_needs_a_user_and_a_password() -> None:
    assert login_from_url("postgresql://u:p%40ss@db/labra", "X") == Login("u", "p@ss")
    with pytest.raises(ConfigError, match="X must name a user and a password"):
        login_from_url("postgresql://u@db/labra", "X")


@pytest.mark.item("W41")
def test_a_login_url_must_be_postgresql() -> None:
    with pytest.raises(ConfigError, match="LABRA_APP_DATABASE_URL must start with postgresql"):
        Settings(app_database_url="sqlite:///labra.db")  # type: ignore[arg-type]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))["services"]


def _url_file(service: dict) -> str:
    return service["environment"]["LABRA_DATABASE_URL_FILE"].removeprefix("/run/secrets/")


@pytest.mark.item("W41")
def test_only_migrate_and_restore_get_the_owners_login() -> None:
    services = _compose()
    holders = {n for n, s in services.items() if "owner_database_url" in s.get("secrets", [])}
    assert holders == {"migrate", "restore"}
    assert {n: _url_file(services[n]) for n in ("web", "migrate", "backup", "restore")} == {
        "web": "database_url",
        "migrate": "owner_database_url",
        "backup": "backup_database_url",
        "restore": "owner_database_url",
    }
    env = services["migrate"]["environment"]
    assert env["LABRA_APP_DATABASE_URL_FILE"] == "/run/secrets/database_url"
    assert env["LABRA_BACKUP_DATABASE_URL_FILE"] == "/run/secrets/backup_database_url"
    for name in ("web", "migrate", "backup", "restore"):
        assert _url_file(services[name]) in services[name]["secrets"], name
