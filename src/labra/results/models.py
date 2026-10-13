"""Results and what happens to a test in the lab: values, verification, changes after
verification, critical-value notifications, external lab documents and the test's timeline
(design §5.6, §1a).

`result` is the only table here that is edited in place, while a test is being worked on.
The others are append-only, refused by the database itself.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, IdMixin, TrackedMixin
from labra.core.ids import utcnow

FLAGS = ("N", "L", "H", "LL", "HH", "A")
RESULT_SOURCES = ("manual", "calculated", "external_pdf")
NOTIFY_MODES = ("phone", "in_person", "message", "email")
TEST_EVENTS = ("routed", "received", "sent", "received_back", "resulted", "verified", "reopened")


class Result(TrackedMixin, Base):
    """One parameter's value for one ordered test. The range it was read against is copied
    in when the value is entered, so a later change to the range never alters this row."""

    __tablename__ = "result"
    __table_args__ = (
        UniqueConstraint("order_test_id", "parameter_id"),
        CheckConstraint("flag is null or flag in ('N', 'L', 'H', 'LL', 'HH', 'A')", name="flag"),
        CheckConstraint("source in ('manual', 'calculated', 'external_pdf')", name="source"),
        CheckConstraint(
            "band_severity is null or band_severity in ('normal', 'borderline', 'abnormal')",
            name="band_severity",
        ),
        CheckConstraint("not (not_calculable and value_num is not null)", name="not_calculable"),
    )

    order_test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_test.id"), index=True)
    parameter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_parameter.id"), index=True)
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    value_text: Mapped[str] = mapped_column(String(200), default="")
    unit: Mapped[str] = mapped_column(String(30), default="")
    flag: Mapped[str | None] = mapped_column(String(2))
    band_label: Mapped[str] = mapped_column(String(40), default="")
    band_severity: Mapped[str | None] = mapped_column(String(12))
    ref_range_text: Mapped[str] = mapped_column(String(200), default="")
    ref_low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    ref_high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    crit_low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    crit_high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    source: Mapped[str] = mapped_column(String(12), default="manual")
    # A calculated row whose formula may not be used for these inputs.
    not_calculable: Mapped[bool] = mapped_column(default=False, server_default=false())
    # The value is outside the typo guard and was saved on an explicit second confirm.
    absurd_confirmed: Mapped[bool] = mapped_column(default=False, server_default=false())
    comment: Mapped[str] = mapped_column(String(300), default="")
    entered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    entered_at: Mapped[datetime] = mapped_column(default=utcnow)


class Verification(IdMixin, Base):
    """A signatory's sign-off of one test's results. A test verified again after being
    reopened gets a new row; the old one stays."""

    __tablename__ = "verification"
    __table_args__ = (CheckConstraint("level in (1, 2)", name="level"),)

    order_test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_test.id"), index=True)
    level: Mapped[int] = mapped_column(SmallInteger, default=1)
    verified_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    verified_at: Mapped[datetime] = mapped_column(default=utcnow)
    note: Mapped[str] = mapped_column(String(300), default="")


class ResultRevision(IdMixin, Base):
    """What a result was before it was changed after verification, and why."""

    __tablename__ = "result_revision"
    __table_args__ = (CheckConstraint("length(btrim(reason)) > 0", name="reason"),)

    result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("result.id"), index=True)
    old_value_num: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    old_value_text: Mapped[str] = mapped_column(String(200), default="")
    old_flag: Mapped[str | None] = mapped_column(String(2))
    reason: Mapped[str] = mapped_column(String(300))
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    changed_at: Mapped[datetime] = mapped_column(default=utcnow)


class CriticalNotification(IdMixin, Base):
    """Who was told about a critical value, when and how (NABL). `reported_value` is the
    value they were told, in case the result is corrected afterwards."""

    __tablename__ = "critical_notification"
    __table_args__ = (
        CheckConstraint("mode in ('phone', 'in_person', 'message', 'email')", name="mode"),
        CheckConstraint("length(btrim(informed_to)) > 0", name="informed_to"),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("result.id"), index=True)
    reported_value: Mapped[str] = mapped_column(String(40))
    reported_flag: Mapped[str] = mapped_column(String(2))
    informed_to: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(15), default="")
    mode: Mapped[str] = mapped_column(String(12))
    informed_at: Mapped[datetime]
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    recorded_at: Mapped[datetime] = mapped_column(default=utcnow)


class ExternalDocument(IdMixin, Base):
    """A result PDF an external lab sent back, as uploaded."""

    __tablename__ = "external_document"
    __table_args__ = (
        CheckConstraint("received_via in ('upload')", name="received_via"),
        CheckConstraint("match_status in ('matched', 'unmatched')", name="match_status"),
    )

    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visit.id"), index=True)
    external_lab_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("external_lab.id"))
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stored_file.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    received_via: Mapped[str] = mapped_column(String(10), default="upload")
    email_message_id: Mapped[str | None] = mapped_column(String(200))
    received_at: Mapped[datetime] = mapped_column(default=utcnow)
    received_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    match_status: Mapped[str] = mapped_column(String(10), default="matched")


class ExternalDocumentTest(Base):
    """Which ordered tests a document reports."""

    __tablename__ = "external_document_test"

    external_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_document.id"), primary_key=True
    )
    order_test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("order_test.id"), primary_key=True, index=True
    )


class OrderTestEvent(IdMixin, Base):
    """One step in a test's life in the lab, with its time and the person: the timeline."""

    __tablename__ = "order_test_event"
    __table_args__ = (
        CheckConstraint(
            "event in ('routed', 'received', 'sent', 'received_back', 'resulted', 'verified',"
            " 'reopened')",
            name="event",
        ),
    )

    order_test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_test.id"), index=True)
    event: Mapped[str] = mapped_column(String(14))
    at: Mapped[datetime] = mapped_column(default=utcnow)
    by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    note: Mapped[str] = mapped_column(String(300), default="")
