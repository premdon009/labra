"""Released reports and what happened to them afterwards (design §5.6, §7).

A `report` row exists only once a signatory has released it. Its PDF, its content snapshot
and its numbers never change; the database allows one change only, `released` to
`superseded`, when a later version replaces it. The other tables are append-only.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, IdMixin
from labra.core.dialect import EMPTY_JSON, Json
from labra.core.ids import utcnow

REPORT_KINDS = ("combined", "in_house", "external_forward")
REPORT_STATUSES = ("released", "superseded")
DELIVERY_MODES = ("counter", "home", "email", "whatsapp")
PRINT_OUTPUTS = ("digital", "print")


class Report(IdMixin, Base):
    """One released version of a report. Version n+1 of the same number supersedes version
    n; `amendment_reason` is set when a released result was changed, not when more tests
    were added."""

    __tablename__ = "report"
    __table_args__ = (
        CheckConstraint("kind in ('combined', 'in_house', 'external_forward')", name="kind"),
        CheckConstraint("status in ('released', 'superseded')", name="status"),
        CheckConstraint(
            "(kind = 'external_forward') = (external_document_id is not null)",
            name="external_document",
        ),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("(version = 1) = (supersedes_report_id is null)", name="supersedes"),
        CheckConstraint("length(sha256) = 64", name="sha256"),
        Index("uq_report_no_version", "report_no", "version", unique=True),
        Index(
            "uq_report_current",
            "report_no",
            unique=True,
            postgresql_where=text("status = 'released'"),
        ),
    )

    report_no: Mapped[str] = mapped_column(String(30))
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visit.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="combined")
    external_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("external_document.id")
    )
    status: Mapped[str] = mapped_column(String(10), default="released")
    is_partial: Mapped[bool] = mapped_column(default=False)
    amendment_reason: Mapped[str] = mapped_column(String(300), default="")
    supersedes_report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report.id"))
    released_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    released_at: Mapped[datetime] = mapped_column(default=utcnow)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stored_file.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    # Everything the PDF shows, so a print or a selected-tests copy matches the stored one.
    content: Mapped[dict[str, Any]] = mapped_column(Json, default=dict, server_default=EMPTY_JSON)
    # Null: the built-in header from the branch details.
    letterhead_layout_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("letterhead_layout.id")
    )
    # For the public check page; 128 random bits, never written to the audit log.
    verify_token: Mapped[str] = mapped_column(String(32), unique=True)


class ReportTest(Base):
    """Which ordered tests a report version carries."""

    __tablename__ = "report_test"

    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report.id"), primary_key=True)
    order_test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("order_test.id"), primary_key=True, index=True
    )


class ReportDelivery(IdMixin, Base):
    """A report handed over or sent: to whom, how, by which member of staff, and what was
    still due on the bill at the time."""

    __tablename__ = "report_delivery"
    __table_args__ = (
        CheckConstraint("mode in ('counter', 'home', 'email', 'whatsapp')", name="mode"),
        CheckConstraint("length(btrim(delivered_to)) > 0", name="delivered_to"),
        CheckConstraint("dues_at_delivery >= 0", name="dues_at_delivery"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report.id"), index=True)
    delivered_to: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(10))
    # Who handed it over; may be staff without a login, such as a home-collection runner.
    staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    delivered_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    delivered_at: Mapped[datetime] = mapped_column(default=utcnow)
    note: Mapped[str] = mapped_column(String(300), default="")
    dues_at_delivery: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))


class ReportPrint(IdMixin, Base):
    """A copy downloaded or printed. `order_test_ids` lists the tests chosen when only some
    were printed; empty means all of them."""

    __tablename__ = "report_print"
    __table_args__ = (
        CheckConstraint("output in ('digital', 'print')", name="output"),
        CheckConstraint("dues_at_print >= 0", name="dues_at_print"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report.id"), index=True)
    output: Mapped[str] = mapped_column(String(8))
    order_test_ids: Mapped[list[str]] = mapped_column(Json, default=list)
    # Paper size, reference column and the other output choices.
    options: Mapped[dict[str, Any]] = mapped_column(Json, default=dict, server_default=EMPTY_JSON)
    dues_at_print: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))
    printed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    printed_at: Mapped[datetime] = mapped_column(default=utcnow)
