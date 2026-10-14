"""A visit and what was ordered on it: order lines, the tests they expand to, and the
samples collected for them."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, TrackedMixin
from labra.core.dialect import EMPTY_JSON, Json
from labra.core.ids import utcnow

COLLECTION_MODES = ("walk_in", "home")
ORDER_ITEM_TYPES = ("test", "package", "extra_charge")
ORDER_TEST_STATUSES = (
    "ordered",
    "collected",
    "in_lab",
    "sent_out",
    "resulted",
    "verified",
    "released",
    "cancelled",
)
ROUTES = ("in_house", "external")
SAMPLE_STATUSES = ("pending", "collected", "received", "rejected", "redraw", "cancelled")
REPORT_MODES = ("combined", "separate")


class Visit(TrackedMixin, Base):
    """One trip to the lab: the tests ordered, the referrer and when results are promised.
    `client_ref` comes from the form, so a double-clicked Save makes one visit."""

    __tablename__ = "visit"
    __table_args__ = (
        CheckConstraint("collection_mode in ('walk_in', 'home')", name="collection_mode"),
        CheckConstraint("status in ('open', 'completed', 'cancelled')", name="status"),
        CheckConstraint(
            "report_mode is null or report_mode in ('combined', 'separate')", name="report_mode"
        ),
        Index("ix_visit_branch_visited", "branch_id", text("visited_at DESC")),
    )

    visit_no: Mapped[str] = mapped_column(String(30), unique=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient.id"), index=True)
    referrer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("referrer.id"))
    visited_at: Mapped[datetime] = mapped_column(default=utcnow)
    collection_mode: Mapped[str] = mapped_column(String(10), default="walk_in")
    status: Mapped[str] = mapped_column(String(10), default="open")
    promised_at: Mapped[datetime]
    footer_note: Mapped[str] = mapped_column(String(200), default="")
    internal_note: Mapped[str] = mapped_column(Text, default="")
    manual_receipt_ref: Mapped[str] = mapped_column(String(30), default="")
    extra: Mapped[dict[str, Any]] = mapped_column(Json, default=dict, server_default=EMPTY_JSON)
    origin_device_id: Mapped[str | None] = mapped_column(String(40))
    client_ref: Mapped[uuid.UUID] = mapped_column(unique=True)
    # How outside results are reported; null follows the report.default_mode setting.
    report_mode: Mapped[str | None] = mapped_column(String(10))


class OrderItem(TrackedMixin, Base):
    """A line the patient pays for: a test, a package or an extra charge. `price_id` is the
    price row the rate came from."""

    __tablename__ = "order_item"
    __table_args__ = (
        CheckConstraint("item_type in ('test', 'package', 'extra_charge')", name="item_type"),
        CheckConstraint(
            "(item_type = 'test' and test_id is not null and package_id is null)"
            " or (item_type = 'package' and package_id is not null and test_id is null)"
            " or (item_type = 'extra_charge' and test_id is null and package_id is null)",
            name="item_ref",
        ),
        CheckConstraint(
            "item_type <> 'extra_charge' or length(reason) > 0", name="extra_charge_reason"
        ),
        CheckConstraint("list_price >= 0", name="list_price"),
        CheckConstraint("discount_amt >= 0 and discount_amt <= list_price", name="discount_amt"),
        CheckConstraint("net_price = list_price - discount_amt", name="net_price"),
        CheckConstraint("status in ('active', 'cancelled')", name="status"),
    )

    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visit.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(12))
    test_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("test.id"))
    package_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("package.id"))
    description: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(String(120), default="")
    price_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("price.id"))
    list_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_amt: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))
    net_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(10), default="active")
    cancel_reason: Mapped[str] = mapped_column(String(200), default="")


class OrderTest(TrackedMixin, Base):
    """One test to run, from a test line or one of a package's tests. `perform_branch_id`
    is the branch whose lab does it, the main lab unless a collection centre keeps it; a
    test routed `external` goes to `external_lab_id` and keeps the cost agreed that day."""

    __tablename__ = "order_test"
    __table_args__ = (
        CheckConstraint(
            "status in ('ordered', 'collected', 'in_lab', 'sent_out', 'resulted', 'verified',"
            " 'released', 'cancelled')",
            name="status",
        ),
        CheckConstraint("route in ('in_house', 'external')", name="route"),
        CheckConstraint(
            "(route = 'external') = (external_lab_id is not null)", name="route_external"
        ),
        Index("ix_order_test_perform_branch", "perform_branch_id", "status", "due_at"),
        Index(
            "uq_order_test_visit_test",
            "visit_id",
            "test_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
    )

    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visit.id"))
    order_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_item.id"), index=True)
    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test.id"))
    sample_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sample.id"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="ordered")
    due_at: Mapped[datetime]
    route: Mapped[str] = mapped_column(String(10), default="in_house", server_default="in_house")
    perform_branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id"))
    external_lab_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("external_lab.id"))
    external_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    external_accession_no: Mapped[str] = mapped_column(String(40), default="", server_default="")
    route_reason: Mapped[str] = mapped_column(String(200), default="", server_default="")
    routed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    routed_at: Mapped[datetime | None]
    # The method printed on the report; null means the test's default method.
    method_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("test_method.id"))


class Sample(TrackedMixin, Base):
    """A tube or container, numbered for its barcode label. `container` is copied from the
    specimen type when the label is made."""

    __tablename__ = "sample"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'collected', 'received', 'rejected', 'redraw', 'cancelled')",
            name="status",
        ),
        CheckConstraint(
            "status in ('pending', 'cancelled') or collected_at is not null", name="collected"
        ),
    )

    sample_no: Mapped[str] = mapped_column(String(20), unique=True)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visit.id"), index=True)
    specimen_type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("specimen_type.id"))
    container: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(10), default="pending")
    collected_at: Mapped[datetime | None]
    collected_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    # Scanned in at the lab that performs the tests, when that is a different branch.
    received_at: Mapped[datetime | None]
    received_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    # Printed above the panels this sample's tests appear in, e.g. "Mildly haemolysed".
    remarks: Mapped[str] = mapped_column(String(300), default="", server_default="")
