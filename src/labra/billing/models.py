"""Bills, their lines, payments and refunds. Issued amounts never change: the database
refuses edits to an issued bill's figures and to any line, payment or refund."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, TrackedMixin
from labra.core.ids import utcnow

DOC_TYPES = ("bill_of_supply", "tax_invoice")
PAYMENT_MODES = ("cash", "upi", "card")
BILL_STATUSES = ("open", "paid", "cancelled")
MONEY = Numeric(12, 2)


class Bill(TrackedMixin, Base):
    """What the patient owes for a visit. `print_snapshot` holds everything printed on it,
    as it was when the bill was issued."""

    __tablename__ = "bill"
    __table_args__ = (
        CheckConstraint("length(bill_no) <= 16 and bill_no ~ '^[A-Za-z0-9/-]+$'", name="bill_no"),
        CheckConstraint("doc_type in ('bill_of_supply', 'tax_invoice')", name="doc_type"),
        CheckConstraint("status in ('open', 'paid', 'cancelled')", name="status"),
        CheckConstraint("gross >= 0", name="gross"),
        CheckConstraint("discount >= 0 and discount <= gross", name="discount"),
        CheckConstraint("discount = 0 or length(discount_reason) > 0", name="discount_reason"),
        CheckConstraint("net = gross - discount + round_off", name="net"),
        CheckConstraint("net >= 0", name="net_not_negative"),
        CheckConstraint("paid >= 0 and paid <= net", name="paid"),
        CheckConstraint("abs(round_off) <= coalesce(round_off_unit, 0) / 2", name="round_off"),
        CheckConstraint("status <> 'paid' or paid = net", name="paid_status"),
        CheckConstraint("status <> 'open' or paid < net", name="open_status"),
        CheckConstraint(
            "status <> 'cancelled' or (length(cancel_reason) > 0 and cancelled_at is not null)",
            name="cancelled",
        ),
        UniqueConstraint("fin_year", "bill_no"),
        Index(
            "uq_bill_visit_doc_type",
            "visit_id",
            "doc_type",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
        Index("ix_bill_branch_date", "branch_id", "bill_date"),
        Index(
            "ix_bill_branch_date_open",
            "branch_id",
            "bill_date",
            postgresql_where=text("status = 'open'"),
        ),
    )

    bill_no: Mapped[str] = mapped_column(String(16))
    fin_year: Mapped[int] = mapped_column(SmallInteger)
    doc_type: Mapped[str] = mapped_column(String(16), default="bill_of_supply")
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id"))
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visit.id"))
    recipient_name: Mapped[str] = mapped_column(String(120))
    bill_date: Mapped[date]
    issued_at: Mapped[datetime] = mapped_column(default=utcnow)
    place_of_supply_state: Mapped[str] = mapped_column(String(2))
    gross: Mapped[Decimal] = mapped_column(MONEY)
    discount: Mapped[Decimal] = mapped_column(MONEY)
    discount_reason: Mapped[str] = mapped_column(String(120), default="")
    round_off: Mapped[Decimal] = mapped_column(MONEY)
    round_off_unit: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    net: Mapped[Decimal] = mapped_column(MONEY)
    paid: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    due: Mapped[Decimal] = mapped_column(MONEY, Computed("net - paid", persisted=True))
    status: Mapped[str] = mapped_column(String(10))
    cancel_reason: Mapped[str] = mapped_column(String(200), default="")
    cancelled_at: Mapped[datetime | None]
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    print_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    origin_device_id: Mapped[str | None] = mapped_column(String(40))
    client_ref: Mapped[uuid.UUID] = mapped_column(unique=True)


class BillLine(TrackedMixin, Base):
    __tablename__ = "bill_line"
    __table_args__ = (
        CheckConstraint("rate >= 0", name="rate"),
        CheckConstraint("discount >= 0 and discount <= rate", name="discount"),
        CheckConstraint("amount = rate - discount", name="amount"),
        UniqueConstraint("bill_id", "line_no"),
    )

    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bill.id"))
    order_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_item.id"))
    line_no: Mapped[int] = mapped_column(SmallInteger)
    description: Mapped[str] = mapped_column(String(120))
    sac_code: Mapped[str] = mapped_column(String(8), default="")
    rate: Mapped[Decimal] = mapped_column(MONEY)
    discount: Mapped[Decimal] = mapped_column(MONEY)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    price_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("price.id"))


class Payment(TrackedMixin, Base):
    """Money received against a bill, with its receipt number."""

    __tablename__ = "payment"
    __table_args__ = (
        CheckConstraint("mode in ('cash', 'upi', 'card')", name="mode"),
        CheckConstraint("amount > 0", name="amount"),
    )

    receipt_no: Mapped[str] = mapped_column(String(30), unique=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id"))
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bill.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient.id"))
    mode: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    reference: Mapped[str] = mapped_column(String(40), default="")
    received_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    received_at: Mapped[datetime] = mapped_column(default=utcnow)
    origin_device_id: Mapped[str | None] = mapped_column(String(40))
    client_ref: Mapped[uuid.UUID] = mapped_column(unique=True)


class Refund(TrackedMixin, Base):
    """Money paid back when a bill is cancelled. Only a full refund is recorded here."""

    __tablename__ = "refund"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("mode in ('cash', 'upi', 'card')", name="mode"),
        CheckConstraint("length(reason) > 0", name="reason"),
    )

    refund_no: Mapped[str] = mapped_column(String(30), unique=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id"))
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bill.id"), unique=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    mode: Mapped[str] = mapped_column(String(10))
    reference: Mapped[str] = mapped_column(String(40), default="")
    reason: Mapped[str] = mapped_column(String(200))
    refunded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    refunded_at: Mapped[datetime] = mapped_column(default=utcnow)
    client_ref: Mapped[uuid.UUID] = mapped_column(unique=True)
