"""The run log. Every scheduled job adds one row when it ends, and rows never change."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Identity, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base

KINDS = ("backup", "drill", "verify", "disk", "upgrade")


class OpsRun(Base):
    """One run of a backup, restore drill, audit check, disk check or upgrade. The backup
    container writes its rows with psql, so the columns stay plain."""

    __tablename__ = "ops_run"
    __table_args__ = (
        CheckConstraint(f"kind in {KINDS}", name="kind"),
        CheckConstraint("finished_at >= started_at", name="finished_at"),
        Index("ix_ops_run_kind_started_at", "kind", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime]
    ok: Mapped[bool]
    # restic snapshot IDs, one per repository: "drive:1a2b3c4d usb:5e6f7a8b".
    snapshot: Mapped[str | None] = mapped_column(String(200))
    bytes_added: Mapped[int | None] = mapped_column(BigInteger)
    detail: Mapped[str | None] = mapped_column(Text)
