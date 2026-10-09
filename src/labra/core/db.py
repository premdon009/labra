import time
import uuid
from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, Engine, MetaData, create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    mapped_column,
    sessionmaker,
)

from labra.core.config import get_settings
from labra.core.errors import LabraError
from labra.core.ids import new_id, utcnow

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {datetime: DateTime(timezone=True)}  # noqa: RUF012


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)


class TrackedMixin(IdMixin):
    """The metadata columns every business table carries (design §5)."""

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_by: Mapped[uuid.UUID | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    updated_by: Mapped[uuid.UUID | None]
    row_version: Mapped[int] = mapped_column(default=1)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:  # noqa: N805
        return {"version_id_col": cls.row_version}


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url.get_secret_value(), pool_pre_ping=True)


def wait_for_database(engine: Engine, timeout: float, interval: float = 1.0) -> None:
    """Return once the database takes connections. Some Compose implementations start services
    in order without waiting for health checks, so `migrate` can start before Postgres does."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            with engine.connect():
                return
        except OperationalError:
            if time.monotonic() >= deadline:
                raise LabraError(f"Database not reachable after {timeout:g} s.") from None
            time.sleep(interval)


def get_session() -> Iterator[Session]:
    with sessionmaker(get_engine())() as session:
        yield session
