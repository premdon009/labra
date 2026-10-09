"""Tables every feature module relies on: settings, numbering, files, outbox, audit, consent.

Foreign keys to `branch` and `app_user` are written as strings, so the core never imports
a feature module.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, IdMixin, TrackedMixin
from labra.core.ids import utcnow


class Setting(TrackedMixin, Base):
    """A lab-level setting. A row with a branch overrides the instance row (branch_id null)."""

    __tablename__ = "setting"
    __table_args__ = (UniqueConstraint("key", "branch_id", postgresql_nulls_not_distinct=True),)

    key: Mapped[str] = mapped_column(String(100))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branch.id"))
    value: Mapped[Any] = mapped_column(JSONB)


class NumberSeries(TrackedMixin, Base):
    """Next number for one document type, per branch, restarting each financial year."""

    __tablename__ = "number_series"
    __table_args__ = (
        UniqueConstraint("doc_type", "branch_id", postgresql_nulls_not_distinct=True),
    )

    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branch.id"))
    doc_type: Mapped[str] = mapped_column(String(20))
    format: Mapped[str] = mapped_column(String(60))
    fin_year: Mapped[int]
    next_value: Mapped[int] = mapped_column(default=1)


class StoredFile(IdMixin, Base):
    """A file's metadata. The bytes live in the FileStore under `storage_key`."""

    __tablename__ = "stored_file"

    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(200))
    size: Mapped[int] = mapped_column(BigInteger)
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_by: Mapped[uuid.UUID | None]


class EventOutbox(IdMixin, Base):
    """Events written in the same transaction as the change they describe, sent later."""

    __tablename__ = "event_outbox"
    __table_args__ = (
        Index(
            "ix_event_outbox_pending",
            "available_at",
            postgresql_where="processed_at IS NULL",
        ),
    )

    topic: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    available_at: Mapped[datetime] = mapped_column(default=utcnow)
    processed_at: Mapped[datetime | None]
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    """Append-only: a database trigger refuses UPDATE, DELETE and TRUNCATE, and each row
    carries the hash of the one before it, so a removed or edited row is detectable."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    user_id: Mapped[uuid.UUID | None]
    branch_id: Mapped[uuid.UUID | None]
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Consent(IdMixin, Base):
    """A person's consent for one purpose (DPDP Act). Withdrawal is a new timestamp, never
    a deleted row."""

    __tablename__ = "consent"

    subject_type: Mapped[str] = mapped_column(String(30))
    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    purpose: Mapped[str] = mapped_column(String(60))
    method: Mapped[str] = mapped_column(String(20))
    given_at: Mapped[datetime] = mapped_column(default=utcnow)
    withdrawn_at: Mapped[datetime | None]
    recorded_by: Mapped[uuid.UUID | None]
