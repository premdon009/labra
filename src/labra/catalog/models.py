"""The test catalog and prices (design §5.3, §1d).

Ranges and prices are never edited in place once results or bills could depend on them: a
price change closes the old row and adds a new one, and a changed range loses its approval.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, TrackedMixin

RESULT_TYPES = ("numeric", "text", "option", "calculated")
SEXES = ("M", "F", "O")
BAND_SEVERITIES = ("normal", "borderline", "abnormal")
ITEM_TYPES = ("test", "package")
# Physiological states a range can apply to, besides sex and age.
RANGE_CONDITIONS = (
    "pregnancy_t1",
    "pregnancy_t2",
    "pregnancy_t3",
    "follicular",
    "luteal",
    "postmenopausal",
)


class Department(TrackedMixin, Base):
    __tablename__ = "department"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    report_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class SpecimenType(TrackedMixin, Base):
    __tablename__ = "specimen_type"

    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    container: Mapped[str] = mapped_column(String(80), default="")
    is_active: Mapped[bool] = mapped_column(default=True)


class Test(TrackedMixin, Base):
    """Something the lab orders and reports. `code` is the short mnemonic staff type
    (`hb`, `lipid`); `aliases` are other codes that find it."""

    __test__ = False  # not a pytest test class
    __tablename__ = "test"
    __table_args__ = (
        Index(
            "ix_test_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index("ix_test_aliases", "aliases", postgresql_using="gin"),
    )

    code: Mapped[str] = mapped_column(String(20), unique=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    name: Mapped[str] = mapped_column(String(120))
    short_name: Mapped[str] = mapped_column(String(40), default="")
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("department.id"), index=True)
    specimen_type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("specimen_type.id"))
    default_tat_hours: Mapped[int] = mapped_column(default=24)
    in_house_available: Mapped[bool] = mapped_column(default=True)
    interpretation_text: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(default=True)


class TestParameter(TrackedMixin, Base):
    """One reported row of a test. A calculated row's `formula` names other parameters of the
    same test by code; `formula_valid_if` says when the formula may be used at all."""

    __test__ = False  # not a pytest test class
    __tablename__ = "test_parameter"
    __table_args__ = (
        CheckConstraint(
            "result_type in ('numeric', 'text', 'option', 'calculated')", name="result_type"
        ),
        UniqueConstraint("test_id", "code"),
    )

    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test.id"))
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    result_type: Mapped[str] = mapped_column(String(12))
    unit_ucum: Mapped[str] = mapped_column(String(30), default="")
    decimals: Mapped[int] = mapped_column(default=0)
    formula: Mapped[str] = mapped_column(String(200), default="")
    formula_valid_if: Mapped[str] = mapped_column(String(200), default="")
    # [{"value": "Nil", "abnormal": false, "default": true}, ...]
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # A regular expression a text result must match, for example "120/80" for blood pressure.
    text_pattern: Mapped[str] = mapped_column(String(100), default="")
    display_order: Mapped[int] = mapped_column(default=0)
    is_reportable: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class ReferenceRange(TrackedMixin, Base):
    """The normal range for one parameter, sex and age band (ages in days, so newborn ranges
    work). Either limit may be missing for a one-sided range such as HDL > 40."""

    __tablename__ = "reference_range"
    __table_args__ = (
        CheckConstraint("sex is null or sex in ('M', 'F', 'O')", name="sex"),
        CheckConstraint("age_min_days < age_max_days", name="age_order"),
        CheckConstraint("low is null or high is null or low <= high", name="low_high"),
    )

    parameter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_parameter.id"), index=True)
    sex: Mapped[str | None] = mapped_column(String(1))
    age_min_days: Mapped[int] = mapped_column(default=0)
    # Exclusive upper bound; 54750 days is 150 years.
    age_max_days: Mapped[int] = mapped_column(default=54750)
    condition: Mapped[str | None] = mapped_column(String(20))
    low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    critical_low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    critical_high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    absurd_low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    absurd_high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    display_text: Mapped[str] = mapped_column(String(200), default="")
    source_citation: Mapped[str] = mapped_column(String(300), default="")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    approved_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(default=True)


class ReferenceBand(TrackedMixin, Base):
    """An interpretation tier inside or around a range, such as the lipid categories."""

    __tablename__ = "reference_band"
    __table_args__ = (
        CheckConstraint("severity in ('normal', 'borderline', 'abnormal')", name="severity"),
    )

    range_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reference_range.id", ondelete="CASCADE"), index=True
    )
    low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    label: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(12))
    display_order: Mapped[int] = mapped_column(default=0)


class TestMethod(TrackedMixin, Base):
    """A method a test can be run by; the default one is printed unless the result says
    otherwise."""

    __test__ = False  # not a pytest test class
    __tablename__ = "test_method"
    __table_args__ = (
        Index(
            "uq_test_method_one_default",
            "test_id",
            unique=True,
            postgresql_where="is_default and is_active",
        ),
    )

    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_default: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)


class CommentPreset(TrackedMixin, Base):
    """A ready-made comment the technician can pick; `test_id` null means any test."""

    __tablename__ = "comment_preset"

    test_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("test.id"), index=True)
    label: Mapped[str] = mapped_column(String(60))
    text: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)


class Package(TrackedMixin, Base):
    __tablename__ = "package"
    __table_args__ = (
        Index(
            "ix_package_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(default=True)


class PackageItem(Base):
    __tablename__ = "package_item"

    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("package.id", ondelete="CASCADE"), primary_key=True
    )
    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test.id"), primary_key=True)


class Price(TrackedMixin, Base):
    """The price of a test or package from `valid_from` until `valid_to` (open while null).
    `branch_id` null is the lab-wide price; a branch row overrides it at that branch."""

    __tablename__ = "price"
    __table_args__ = (
        CheckConstraint("item_type in ('test', 'package')", name="item_type"),
        CheckConstraint("amount >= 0", name="amount"),
        CheckConstraint("valid_to is null or valid_from < valid_to", name="validity"),
        Index(
            "uq_price_open",
            "item_type",
            "item_id",
            "branch_id",
            unique=True,
            postgresql_where="valid_to is null",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_price_item", "item_type", "item_id"),
    )

    item_type: Mapped[str] = mapped_column(String(10))
    item_id: Mapped[uuid.UUID]
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branch.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    valid_from: Mapped[datetime]
    valid_to: Mapped[datetime | None]
    reason: Mapped[str] = mapped_column(String(200), default="")
