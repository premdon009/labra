"""Catalog and prices: departments, specimen types, tests, parameters, reference ranges and
bands, methods, comment presets, packages, price history.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Trigram search on test and package names (code-first search). A trusted
    # extension: the database owner may create it.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "department",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("report_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_department")),
        sa.UniqueConstraint("name", name=op.f("uq_department_name")),
    )
    op.create_table(
        "package",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_package")),
        sa.UniqueConstraint("code", name=op.f("uq_package_code")),
    )
    op.create_index(
        "ix_package_name_trgm",
        "package",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_table(
        "specimen_type",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("container", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_specimen_type")),
        sa.UniqueConstraint("code", name=op.f("uq_specimen_type_code")),
    )
    op.create_table(
        "price",
        sa.Column("item_type", sa.String(length=10), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("item_type in ('test', 'package')", name=op.f("ck_price_item_type")),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_price_amount")),
        sa.CheckConstraint(
            "valid_to is null or valid_from < valid_to", name=op.f("ck_price_validity")
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_price_branch_id_branch")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price")),
    )
    op.create_index("ix_price_item", "price", ["item_type", "item_id"], unique=False)
    op.create_index(
        "uq_price_open",
        "price",
        ["item_type", "item_id", "branch_id"],
        unique=True,
        postgresql_where="valid_to is null",
        postgresql_nulls_not_distinct=True,
    )
    op.create_table(
        "test",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("short_name", sa.String(length=40), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("specimen_type_id", sa.Uuid(), nullable=True),
        sa.Column("default_tat_hours", sa.Integer(), nullable=False),
        sa.Column("in_house_available", sa.Boolean(), nullable=False),
        sa.Column("interpretation_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["department_id"], ["department.id"], name=op.f("fk_test_department_id_department")
        ),
        sa.ForeignKeyConstraint(
            ["specimen_type_id"],
            ["specimen_type.id"],
            name=op.f("fk_test_specimen_type_id_specimen_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test")),
        sa.UniqueConstraint("code", name=op.f("uq_test_code")),
    )
    op.create_index("ix_test_aliases", "test", ["aliases"], unique=False, postgresql_using="gin")
    op.create_index(op.f("ix_test_department_id"), "test", ["department_id"], unique=False)
    op.create_index(
        "ix_test_name_trgm",
        "test",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_table(
        "comment_preset",
        sa.Column("test_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["test_id"], ["test.id"], name=op.f("fk_comment_preset_test_id_test")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comment_preset")),
    )
    op.create_index(op.f("ix_comment_preset_test_id"), "comment_preset", ["test_id"], unique=False)
    op.create_table(
        "package_item",
        sa.Column("package_id", sa.Uuid(), nullable=False),
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["package.id"],
            name=op.f("fk_package_item_package_id_package"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_id"], ["test.id"], name=op.f("fk_package_item_test_id_test")
        ),
        sa.PrimaryKeyConstraint("package_id", "test_id", name=op.f("pk_package_item")),
    )
    op.create_table(
        "test_method",
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["test_id"], ["test.id"], name=op.f("fk_test_method_test_id_test")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_method")),
    )
    op.create_index(op.f("ix_test_method_test_id"), "test_method", ["test_id"], unique=False)
    op.create_index(
        "uq_test_method_one_default",
        "test_method",
        ["test_id"],
        unique=True,
        postgresql_where="is_default and is_active",
    )
    op.create_table(
        "test_parameter",
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("result_type", sa.String(length=12), nullable=False),
        sa.Column("unit_ucum", sa.String(length=30), nullable=False),
        sa.Column("decimals", sa.Integer(), nullable=False),
        sa.Column("formula", sa.String(length=200), nullable=False),
        sa.Column("formula_valid_if", sa.String(length=200), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("text_pattern", sa.String(length=100), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_reportable", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "result_type in ('numeric', 'text', 'option', 'calculated')",
            name=op.f("ck_test_parameter_result_type"),
        ),
        sa.ForeignKeyConstraint(
            ["test_id"], ["test.id"], name=op.f("fk_test_parameter_test_id_test")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_parameter")),
        sa.UniqueConstraint("test_id", "code", name=op.f("uq_test_parameter_test_id_code")),
    )
    op.create_table(
        "reference_range",
        sa.Column("parameter_id", sa.Uuid(), nullable=False),
        sa.Column("sex", sa.String(length=1), nullable=True),
        sa.Column("age_min_days", sa.Integer(), nullable=False),
        sa.Column("age_max_days", sa.Integer(), nullable=False),
        sa.Column("condition", sa.String(length=20), nullable=True),
        sa.Column("low", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("high", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("critical_low", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("critical_high", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("absurd_low", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("absurd_high", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("display_text", sa.String(length=200), nullable=False),
        sa.Column("source_citation", sa.String(length=300), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "sex is null or sex in ('M', 'F', 'O')", name=op.f("ck_reference_range_sex")
        ),
        sa.CheckConstraint(
            "age_min_days < age_max_days", name=op.f("ck_reference_range_age_order")
        ),
        sa.CheckConstraint(
            "low is null or high is null or low <= high", name=op.f("ck_reference_range_low_high")
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["app_user.id"], name=op.f("fk_reference_range_approved_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["parameter_id"],
            ["test_parameter.id"],
            name=op.f("fk_reference_range_parameter_id_test_parameter"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_range")),
    )
    op.create_index(
        op.f("ix_reference_range_parameter_id"), "reference_range", ["parameter_id"], unique=False
    )
    op.create_table(
        "reference_band",
        sa.Column("range_id", sa.Uuid(), nullable=False),
        sa.Column("low", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("high", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=12), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "severity in ('normal', 'borderline', 'abnormal')",
            name=op.f("ck_reference_band_severity"),
        ),
        sa.ForeignKeyConstraint(
            ["range_id"],
            ["reference_range.id"],
            name=op.f("fk_reference_band_range_id_reference_range"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_band")),
    )
    op.create_index(
        op.f("ix_reference_band_range_id"), "reference_band", ["range_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reference_band_range_id"), table_name="reference_band")
    op.drop_table("reference_band")
    op.drop_index(op.f("ix_reference_range_parameter_id"), table_name="reference_range")
    op.drop_table("reference_range")
    op.drop_table("test_parameter")
    op.drop_index(
        "uq_test_method_one_default",
        table_name="test_method",
        postgresql_where="is_default and is_active",
    )
    op.drop_index(op.f("ix_test_method_test_id"), table_name="test_method")
    op.drop_table("test_method")
    op.drop_table("package_item")
    op.drop_index(op.f("ix_comment_preset_test_id"), table_name="comment_preset")
    op.drop_table("comment_preset")
    op.drop_index(
        "ix_test_name_trgm",
        table_name="test",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_index(op.f("ix_test_department_id"), table_name="test")
    op.drop_index("ix_test_aliases", table_name="test", postgresql_using="gin")
    op.drop_table("test")
    op.drop_index(
        "uq_price_open",
        table_name="price",
        postgresql_where="valid_to is null",
        postgresql_nulls_not_distinct=True,
    )
    op.drop_index("ix_price_item", table_name="price")
    op.drop_table("price")
    op.drop_table("specimen_type")
    op.drop_index(
        "ix_package_name_trgm",
        table_name="package",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_table("package")
    op.drop_table("department")
