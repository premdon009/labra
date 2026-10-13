"""External labs that tests are sent out to, and what each charges per test (design §5.4)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, false
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, TrackedMixin


class ExternalLab(TrackedMixin, Base):
    """A referral lab. `share_phone` and `share_address` say whether this lab needs the
    patient's phone or address on the sheet that goes with a sample; both start off."""

    __tablename__ = "external_lab"

    name: Mapped[str] = mapped_column(String(120), unique=True)
    nabl_cert_no: Mapped[str] = mapped_column(String(40), default="")
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(15), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    results_email: Mapped[str] = mapped_column(String(120), default="")
    portal_url: Mapped[str] = mapped_column(String(200), default="")
    dpa_signed_on: Mapped[date | None]
    share_phone: Mapped[bool] = mapped_column(default=False, server_default=false())
    share_address: Mapped[bool] = mapped_column(default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(default=True)


class ExternalLabRate(TrackedMixin, Base):
    """What a lab charges for one test from `valid_from` until `valid_to` (open while null),
    and how long it takes. A change closes the old row and adds a new one, as prices do."""

    __tablename__ = "external_lab_rate"
    __table_args__ = (
        CheckConstraint("cost >= 0", name="cost"),
        CheckConstraint("tat_hours > 0", name="tat_hours"),
        CheckConstraint("valid_to is null or valid_from < valid_to", name="validity"),
        Index(
            "uq_external_lab_rate_open",
            "external_lab_id",
            "test_id",
            unique=True,
            postgresql_where="valid_to is null",
        ),
        Index("ix_external_lab_rate_test", "test_id"),
    )

    external_lab_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("external_lab.id"))
    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test.id"))
    their_test_code: Mapped[str] = mapped_column(String(40), default="")
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tat_hours: Mapped[int]
    valid_from: Mapped[datetime]
    valid_to: Mapped[datetime | None]
