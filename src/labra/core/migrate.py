"""Alembic, driven from code. Migrations ship inside the package, so an installed Labra
(the Docker image) can upgrade its own database with `labra migrate`."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection

from labra.core.config import get_settings

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["database_url"] = get_settings().database_url.get_secret_value()
    return cfg


def upgrade(revision: str = "head") -> None:
    command.upgrade(alembic_config(), revision)


def head_revisions() -> set[str]:
    return set(ScriptDirectory.from_config(alembic_config()).get_heads())


def current_revisions(conn: Connection) -> set[str]:
    return set(MigrationContext.configure(conn).get_current_heads())
