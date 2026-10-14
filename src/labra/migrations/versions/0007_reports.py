"""Reports: released versions, their tests, deliveries and prints; letterhead layouts; report
fields on tests, staff, branches, visits, samples and ordered tests; the report number series.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written once and never changed (refuse_change() comes from 0003).
APPEND_ONLY = ("report_test", "report_delivery", "report_print")

# A released report can only be superseded: every other column stays as released, and the
# row is never deleted. A published letterhead layout never changes; a draft is edited freely.
GUARDS = """
CREATE FUNCTION report_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'report % v% is released and is kept', OLD.report_no, OLD.version
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status')
       OR NOT (OLD.status = 'released' AND NEW.status = 'superseded') THEN
        RAISE EXCEPTION 'report % v% is released: it can only be superseded',
            OLD.report_no, OLD.version
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER report_released_guard BEFORE UPDATE OR DELETE ON report
    FOR EACH ROW EXECUTE FUNCTION report_guard();
CREATE TRIGGER report_no_truncate BEFORE TRUNCATE ON report
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_change();

CREATE FUNCTION letterhead_layout_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'published' THEN
        RAISE EXCEPTION 'letterhead layout v% is published and is final', OLD.version
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER letterhead_layout_published_guard BEFORE UPDATE OR DELETE ON letterhead_layout
    FOR EACH ROW EXECUTE FUNCTION letterhead_layout_guard();
CREATE TRIGGER letterhead_layout_no_truncate BEFORE TRUNCATE ON letterhead_layout
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_change();
"""

# Every existing branch gets a report series in the format new branches start with. A
# colon inside a format is escaped so it isn't read as a query parameter.
ADD_REPORT_SERIES = r"""
INSERT INTO number_series
    (id, branch_id, doc_type, format, fin_year, next_value, created_at, updated_at, row_version)
SELECT gen_random_uuid(), b.id, 'report', '{BR}/R/{FY2}/{SEQ\:6}',
       CASE WHEN extract(month FROM today.day) >= 4
            THEN extract(year FROM today.day)::int
            ELSE extract(year FROM today.day)::int - 1 END,
       1, now(), now(), 1
FROM branch b
CROSS JOIN (SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date AS day) AS today
WHERE NOT EXISTS (
    SELECT 1 FROM number_series s WHERE s.branch_id = b.id AND s.doc_type = 'report'
)
"""

EVENTS_BEFORE = (
    "event in ('routed', 'received', 'sent', 'received_back', 'resulted', 'verified', 'reopened')"
)
EVENTS_NOW = (
    "event in ('routed', 'received', 'sent', 'received_back', 'resulted', 'verified',"
    " 'reopened', 'released', 'delivered')"
)


def upgrade() -> None:
    op.create_table(
        "letterhead_layout",
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("doc_kind", sa.String(length=10), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_file_id", sa.Uuid(), nullable=True),
        sa.Column("letterhead_file_id", sa.Uuid(), nullable=True),
        sa.Column("file_type", sa.String(length=6), nullable=True),
        sa.Column("raster_dpi", sa.SmallInteger(), nullable=True),
        sa.Column("original_bytes", sa.Integer(), nullable=False),
        sa.Column("optimised_bytes", sa.Integer(), nullable=False),
        sa.Column("converted_from", sa.String(length=14), nullable=False),
        sa.Column("apply_on", sa.String(length=5), nullable=False),
        sa.Column("margin_top_mm", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("margin_bottom_mm", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("margin_left_mm", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("margin_right_mm", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("signature_area_mm", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("font_size_pt", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(status = 'published') = (version is not null and published_at is not null"
            " and published_by is not null)",
            name=op.f("ck_letterhead_layout_published"),
        ),
        sa.CheckConstraint(
            "apply_on in ('all', 'first')", name=op.f("ck_letterhead_layout_apply_on")
        ),
        sa.CheckConstraint(
            "converted_from in ('none', 'pdf', 'raster_traced')",
            name=op.f("ck_letterhead_layout_converted_from"),
        ),
        sa.CheckConstraint(
            "doc_kind in ('report_a4', 'bill_a4')", name=op.f("ck_letterhead_layout_doc_kind")
        ),
        sa.CheckConstraint(
            "file_type is null or file_type in ('svg', 'pdf', 'raster')",
            name=op.f("ck_letterhead_layout_file_type"),
        ),
        sa.CheckConstraint(
            "status in ('draft', 'published')", name=op.f("ck_letterhead_layout_status")
        ),
        sa.CheckConstraint(
            "(file_type is null) = (letterhead_file_id is null)"
            " and (file_type is null) = (original_file_id is null)",
            name=op.f("ck_letterhead_layout_file"),
        ),
        sa.CheckConstraint(
            "font_size_pt between 7 and 14", name=op.f("ck_letterhead_layout_font_size")
        ),
        sa.CheckConstraint(
            "margin_top_mm between 0 and 120 and margin_bottom_mm between 0 and 120"
            " and margin_left_mm between 0 and 60 and margin_right_mm between 0 and 60",
            name=op.f("ck_letterhead_layout_margins"),
        ),
        sa.CheckConstraint(
            "signature_area_mm between 0 and 80", name=op.f("ck_letterhead_layout_signature_area")
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_letterhead_layout_branch_id_branch")
        ),
        sa.ForeignKeyConstraint(
            ["letterhead_file_id"],
            ["stored_file.id"],
            name=op.f("fk_letterhead_layout_letterhead_file_id_stored_file"),
        ),
        sa.ForeignKeyConstraint(
            ["original_file_id"],
            ["stored_file.id"],
            name=op.f("fk_letterhead_layout_original_file_id_stored_file"),
        ),
        sa.ForeignKeyConstraint(
            ["published_by"],
            ["app_user.id"],
            name=op.f("fk_letterhead_layout_published_by_app_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_letterhead_layout")),
    )
    op.create_index(
        "uq_letterhead_layout_draft",
        "letterhead_layout",
        ["branch_id", "doc_kind"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_index(
        "uq_letterhead_layout_version",
        "letterhead_layout",
        ["branch_id", "doc_kind", "version"],
        unique=True,
    )
    op.create_table(
        "report",
        sa.Column("report_no", sa.String(length=30), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("external_document_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("is_partial", sa.Boolean(), nullable=False),
        sa.Column("amendment_reason", sa.String(length=300), nullable=False),
        sa.Column("supersedes_report_id", sa.Uuid(), nullable=True),
        sa.Column("released_by", sa.Uuid(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("letterhead_layout_id", sa.Uuid(), nullable=True),
        sa.Column("verify_token", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(kind = 'external_forward') = (external_document_id is not null)",
            name=op.f("ck_report_external_document"),
        ),
        sa.CheckConstraint(
            "kind in ('combined', 'in_house', 'external_forward')", name=op.f("ck_report_kind")
        ),
        sa.CheckConstraint("status in ('released', 'superseded')", name=op.f("ck_report_status")),
        sa.CheckConstraint(
            "(version = 1) = (supersedes_report_id is null)", name=op.f("ck_report_supersedes")
        ),
        sa.CheckConstraint("length(sha256) = 64", name=op.f("ck_report_sha256")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_report_version")),
        sa.ForeignKeyConstraint(
            ["external_document_id"],
            ["external_document.id"],
            name=op.f("fk_report_external_document_id_external_document"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["stored_file.id"], name=op.f("fk_report_file_id_stored_file")
        ),
        sa.ForeignKeyConstraint(
            ["letterhead_layout_id"],
            ["letterhead_layout.id"],
            name=op.f("fk_report_letterhead_layout_id_letterhead_layout"),
        ),
        sa.ForeignKeyConstraint(
            ["released_by"], ["app_user.id"], name=op.f("fk_report_released_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_report_id"],
            ["report.id"],
            name=op.f("fk_report_supersedes_report_id_report"),
        ),
        sa.ForeignKeyConstraint(["visit_id"], ["visit.id"], name=op.f("fk_report_visit_id_visit")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report")),
        sa.UniqueConstraint("verify_token", name=op.f("uq_report_verify_token")),
    )
    op.create_index(op.f("ix_report_visit_id"), "report", ["visit_id"], unique=False)
    op.create_index(
        "uq_report_current",
        "report",
        ["report_no"],
        unique=True,
        postgresql_where=sa.text("status = 'released'"),
    )
    op.create_index("uq_report_no_version", "report", ["report_no", "version"], unique=True)
    op.create_table(
        "report_delivery",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("delivered_to", sa.String(length=120), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.Column("delivered_by", sa.Uuid(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column("dues_at_delivery", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "mode in ('counter', 'home', 'email', 'whatsapp')", name=op.f("ck_report_delivery_mode")
        ),
        sa.CheckConstraint(
            "dues_at_delivery >= 0", name=op.f("ck_report_delivery_dues_at_delivery")
        ),
        sa.CheckConstraint(
            "length(btrim(delivered_to)) > 0", name=op.f("ck_report_delivery_delivered_to")
        ),
        sa.ForeignKeyConstraint(
            ["delivered_by"], ["app_user.id"], name=op.f("fk_report_delivery_delivered_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["report.id"], name=op.f("fk_report_delivery_report_id_report")
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"], ["app_user.id"], name=op.f("fk_report_delivery_staff_id_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_delivery")),
    )
    op.create_index(
        op.f("ix_report_delivery_report_id"), "report_delivery", ["report_id"], unique=False
    )
    op.create_table(
        "report_print",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("output", sa.String(length=8), nullable=False),
        sa.Column("order_test_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("dues_at_print", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("printed_by", sa.Uuid(), nullable=False),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("output in ('digital', 'print')", name=op.f("ck_report_print_output")),
        sa.CheckConstraint("dues_at_print >= 0", name=op.f("ck_report_print_dues_at_print")),
        sa.ForeignKeyConstraint(
            ["printed_by"], ["app_user.id"], name=op.f("fk_report_print_printed_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["report.id"], name=op.f("fk_report_print_report_id_report")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_print")),
    )
    op.create_index(op.f("ix_report_print_report_id"), "report_print", ["report_id"], unique=False)
    op.create_table(
        "report_test",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("order_test_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_test_id"],
            ["order_test.id"],
            name=op.f("fk_report_test_order_test_id_order_test"),
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["report.id"], name=op.f("fk_report_test_report_id_report")
        ),
        sa.PrimaryKeyConstraint("report_id", "order_test_id", name=op.f("pk_report_test")),
    )
    op.create_index(
        op.f("ix_report_test_order_test_id"), "report_test", ["order_test_id"], unique=False
    )
    op.add_column(
        "app_user",
        sa.Column("qualification", sa.String(length=80), server_default="", nullable=False),
    )
    op.add_column(
        "app_user",
        sa.Column("council_reg_no", sa.String(length=40), server_default="", nullable=False),
    )
    op.add_column("app_user", sa.Column("signature_file_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_app_user_signature_file_id_stored_file"),
        "app_user",
        "stored_file",
        ["signature_file_id"],
        ["id"],
    )
    op.add_column(
        "branch", sa.Column("nabl_cert_no", sa.String(length=40), server_default="", nullable=False)
    )
    op.add_column("order_test", sa.Column("method_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_order_test_method_id_test_method"),
        "order_test",
        "test_method",
        ["method_id"],
        ["id"],
    )
    op.add_column(
        "sample", sa.Column("remarks", sa.String(length=300), server_default="", nullable=False)
    )
    op.add_column(
        "test", sa.Column("display_order", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "test",
        sa.Column("research_use", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "test",
        sa.Column("in_nabl_scope", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("visit", sa.Column("report_mode", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        op.f("ck_visit_report_mode"),
        "visit",
        "report_mode is null or report_mode in ('combined', 'separate')",
    )
    op.drop_constraint(op.f("ck_order_test_event_event"), "order_test_event", type_="check")
    op.create_check_constraint(op.f("ck_order_test_event_event"), "order_test_event", EVENTS_NOW)
    op.execute(GUARDS)
    for table in APPEND_ONLY:
        op.execute(
            f"CREATE TRIGGER {table}_no_change BEFORE UPDATE OR DELETE ON {table}"
            " FOR EACH ROW EXECUTE FUNCTION refuse_change()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}"
            " FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()"
        )
    op.execute(ADD_REPORT_SERIES)


def downgrade() -> None:
    # The report series may have issued numbers by now, so it stays.
    op.execute("DROP FUNCTION IF EXISTS report_guard() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS letterhead_layout_guard() CASCADE")
    op.execute("DROP TRIGGER IF EXISTS report_no_truncate ON report")
    op.execute("DROP TRIGGER IF EXISTS letterhead_layout_no_truncate ON letterhead_layout")
    for table in APPEND_ONLY:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_change ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
    op.drop_constraint(op.f("ck_order_test_event_event"), "order_test_event", type_="check")
    op.create_check_constraint(op.f("ck_order_test_event_event"), "order_test_event", EVENTS_BEFORE)
    op.drop_constraint(op.f("ck_visit_report_mode"), "visit", type_="check")
    op.drop_column("visit", "report_mode")
    op.drop_column("test", "in_nabl_scope")
    op.drop_column("test", "research_use")
    op.drop_column("test", "display_order")
    op.drop_column("sample", "remarks")
    op.drop_constraint(
        op.f("fk_order_test_method_id_test_method"), "order_test", type_="foreignkey"
    )
    op.drop_column("order_test", "method_id")
    op.drop_column("branch", "nabl_cert_no")
    op.drop_constraint(
        op.f("fk_app_user_signature_file_id_stored_file"), "app_user", type_="foreignkey"
    )
    op.drop_column("app_user", "signature_file_id")
    op.drop_column("app_user", "council_reg_no")
    op.drop_column("app_user", "qualification")
    op.drop_index(op.f("ix_report_test_order_test_id"), table_name="report_test")
    op.drop_table("report_test")
    op.drop_index(op.f("ix_report_print_report_id"), table_name="report_print")
    op.drop_table("report_print")
    op.drop_index(op.f("ix_report_delivery_report_id"), table_name="report_delivery")
    op.drop_table("report_delivery")
    op.drop_index("uq_report_no_version", table_name="report")
    op.drop_index(
        "uq_report_current", table_name="report", postgresql_where=sa.text("status = 'released'")
    )
    op.drop_index(op.f("ix_report_visit_id"), table_name="report")
    op.drop_table("report")
    op.drop_index("uq_letterhead_layout_version", table_name="letterhead_layout")
    op.drop_index(
        "uq_letterhead_layout_draft",
        table_name="letterhead_layout",
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.drop_table("letterhead_layout")
