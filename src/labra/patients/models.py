"""Patients and the doctors, clinics and companies that refer them."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, TrackedMixin

SEXES = ("M", "F", "O")
REFERRER_KINDS = ("doctor", "clinic", "hospital", "corporate", "self")


class Patient(TrackedMixin, Base):
    """A person tested at the lab. `dob` is always set; when only an age was given it is
    worked back from the age and `dob_is_estimated` is true."""

    __tablename__ = "patient"
    __table_args__ = (
        CheckConstraint("length(btrim(full_name)) > 0", name="full_name"),
        CheckConstraint("sex in ('M', 'F', 'O')", name="sex"),
        CheckConstraint("phone ~ '^[0-9]{10}$' or phone = ''", name="phone"),
        CheckConstraint("alt_phone ~ '^[0-9]{10}$' or alt_phone = ''", name="alt_phone"),
        CheckConstraint("pincode ~ '^[0-9]{6}$' or pincode = ''", name="pincode"),
        Index(
            "ix_patient_full_name_trgm",
            "full_name",
            postgresql_using="gin",
            postgresql_ops={"full_name": "gin_trgm_ops"},
        ),
        Index("ix_patient_branch_created", "registered_branch_id", "created_at"),
    )

    patient_no: Mapped[str] = mapped_column(String(30), unique=True)
    registered_branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id"))
    title: Mapped[str] = mapped_column(String(10), default="")
    full_name: Mapped[str] = mapped_column(String(120))
    sex: Mapped[str] = mapped_column(String(1))
    dob: Mapped[date]
    dob_is_estimated: Mapped[bool] = mapped_column(default=False)
    phone: Mapped[str] = mapped_column(String(10), default="", index=True)
    alt_phone: Mapped[str] = mapped_column(String(10), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(60), default="")
    pincode: Mapped[str] = mapped_column(String(6), default="")
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


class Referrer(TrackedMixin, Base):
    """Who sent the patient. No commission is ever recorded here."""

    __tablename__ = "referrer"
    __table_args__ = (
        CheckConstraint(
            "kind in ('doctor', 'clinic', 'hospital', 'corporate', 'self')", name="kind"
        ),
        Index(
            "ix_referrer_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    kind: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(120))
    qualification: Mapped[str] = mapped_column(String(80), default="")
    council_reg_no: Mapped[str] = mapped_column(String(40), default="")
    phone: Mapped[str] = mapped_column(String(10), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
