"""The database logins Labra runs as. `labra migrate` connects as the owner, which made the
tables, and on every run puts the web app's and the backup job's logins right: the app may read
and write rows but never change the schema, so a flaw in it can't alter tables, switch off the
audit log's triggers or run programs on the server; the backup job may read everything and add
rows to the run log, nothing else. A restore loads tables without their grants, and the
`migrate` that starts with the stack afterwards gives them back."""

from dataclasses import dataclass
from typing import Any

from psycopg import sql
from sqlalchemy import Connection, make_url, text

from labra.core.config import Settings
from labra.core.errors import ConfigError

ROLE_OPTIONS = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
# The schema version is the owner's to change.
READ_ONLY_FOR_APP = "alembic_version"
RUN_LOG = "ops_run"
READ_ALL = "pg_read_all_data"


@dataclass(frozen=True)
class Login:
    name: str
    password: str


def login_from_url(url: str, setting: str) -> Login:
    parsed = make_url(url)
    if not parsed.username or not parsed.password:
        raise ConfigError(f"{setting} must name a user and a password.")
    return Login(parsed.username, parsed.password)


def _run(conn: Connection, statement: sql.Composable) -> None:
    # Through the driver, so a password is quoted as a literal and never parsed for parameters.
    raw: Any = conn.connection.driver_connection
    with raw.cursor() as cur:
        cur.execute(statement)


def _ensure_login(conn: Connection, login: Login, keep: set[str]) -> None:
    role = sql.Identifier(login.name)
    if not conn.scalar(text("select 1 from pg_roles where rolname = :n"), {"n": login.name}):
        _run(conn, sql.SQL("CREATE ROLE {}").format(role))
    _run(
        conn,
        sql.SQL("ALTER ROLE {} WITH {} PASSWORD {}").format(
            role, sql.SQL(ROLE_OPTIONS), sql.Literal(login.password)
        ),
    )
    # Membership in any other role, the owner's above all, would hand its rights over.
    granted = conn.scalars(
        text(
            "select g.rolname from pg_auth_members m join pg_roles g on g.oid = m.roleid "
            "join pg_roles r on r.oid = m.member where r.rolname = :n"
        ),
        {"n": login.name},
    )
    for group in set(granted) - keep:
        _run(conn, sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(group), role))
    database = sql.Identifier(conn.scalar(text("select current_database()")))
    _run(conn, sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role))
    _run(conn, sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(role))
    _run(conn, sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}").format(role))


def ensure_roles(conn: Connection, app: Login, backup: Login | None = None) -> None:
    """Create or correct the app's login (and the backup job's), in the caller's transaction."""
    owner = conn.scalar(text("select current_user"))
    names = [app.name] + ([backup.name] if backup else [])
    if owner in names:
        raise ConfigError(
            f"The app and backup logins must not be the owner {owner!r}, which can change the "
            "schema; give them users of their own (docs/dev/running-the-stack.md)."
        )
    if len(set(names)) != len(names):
        raise ConfigError("The app and the backup job need different logins.")
    if any(name.startswith("pg_") for name in names):
        raise ConfigError("Role names starting with pg_ are reserved by PostgreSQL.")

    _ensure_login(conn, app, keep=set())
    role = sql.Identifier(app.name)
    _run(conn, sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
    _run(
        conn,
        sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(
            role
        ),
    )
    _run(
        conn,
        sql.SQL("REVOKE INSERT, UPDATE, DELETE ON {} FROM {}").format(
            sql.Identifier(READ_ONLY_FOR_APP), role
        ),
    )
    _run(
        conn,
        sql.SQL("GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {}").format(role),
    )

    if backup:
        _ensure_login(conn, backup, keep={READ_ALL})
        role = sql.Identifier(backup.name)
        _run(conn, sql.SQL("GRANT {} TO {}").format(sql.Identifier(READ_ALL), role))
        _run(conn, sql.SQL("GRANT INSERT ON {} TO {}").format(sql.Identifier(RUN_LOG), role))
        sequence = conn.scalar(text("select pg_get_serial_sequence(:t, 'id')"), {"t": RUN_LOG})
        _run(conn, sql.SQL("GRANT USAGE ON SEQUENCE {} TO {}").format(sql.SQL(sequence), role))


def ensure_roles_from_settings(conn: Connection, settings: Settings) -> list[str]:
    """The logins named in the settings, put right; none when the app has no login of its own."""
    if settings.app_database_url is None:
        return []
    app = login_from_url(settings.app_database_url.get_secret_value(), "LABRA_APP_DATABASE_URL")
    backup = None
    if settings.backup_database_url is not None:
        backup = login_from_url(
            settings.backup_database_url.get_secret_value(), "LABRA_BACKUP_DATABASE_URL"
        )
    ensure_roles(conn, app, backup)
    return [app.name] + ([backup.name] if backup else [])
