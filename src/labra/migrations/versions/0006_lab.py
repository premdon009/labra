"""Lab: performing branch and routing on ordered tests, external labs and their rates,
results, verification, critical-value notifications, external documents, test timeline.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written once and never changed (refuse_change() comes from 0003).
APPEND_ONLY = (
    "verification",
    "result_revision",
    "critical_notification",
    "external_document",
    "external_document_test",
    "order_test_event",
)

# Tests ordered before this revision are done at the main lab; a lab that has none yet
# keeps them at the branch that took the order.
BACKFILL_PERFORM_BRANCH = """
UPDATE order_test AS ot
SET perform_branch_id = coalesce(
    (SELECT id FROM branch WHERE kind = 'main_lab' ORDER BY created_at, id LIMIT 1),
    v.branch_id
)
FROM visit AS v
WHERE v.id = ot.visit_id
"""


def upgrade() -> None:
    op.create_table(
        "external_lab",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("nabl_cert_no", sa.String(length=40), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=15), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("results_email", sa.String(length=120), nullable=False),
        sa.Column("portal_url", sa.String(length=200), nullable=False),
        sa.Column("dpa_signed_on", sa.Date(), nullable=True),
        sa.Column("share_phone", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("share_address", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_lab")),
        sa.UniqueConstraint("name", name=op.f("uq_external_lab_name")),
    )
    op.create_table(
        "external_lab_rate",
        sa.Column("external_lab_id", sa.Uuid(), nullable=False),
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.Column("their_test_code", sa.String(length=40), nullable=False),
        sa.Column("cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tat_hours", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("cost >= 0", name=op.f("ck_external_lab_rate_cost")),
        sa.CheckConstraint("tat_hours > 0", name=op.f("ck_external_lab_rate_tat_hours")),
        sa.CheckConstraint(
            "valid_to is null or valid_from < valid_to", name=op.f("ck_external_lab_rate_validity")
        ),
        sa.ForeignKeyConstraint(
            ["external_lab_id"],
            ["external_lab.id"],
            name=op.f("fk_external_lab_rate_external_lab_id_external_lab"),
        ),
        sa.ForeignKeyConstraint(
            ["test_id"], ["test.id"], name=op.f("fk_external_lab_rate_test_id_test")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_lab_rate")),
    )
    op.create_index("ix_external_lab_rate_test", "external_lab_rate", ["test_id"], unique=False)
    op.create_index(
        "uq_external_lab_rate_open",
        "external_lab_rate",
        ["external_lab_id", "test_id"],
        unique=True,
        postgresql_where="valid_to is null",
    )
    op.create_table(
        "external_document",
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("external_lab_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("received_via", sa.String(length=10), nullable=False),
        sa.Column("email_message_id", sa.String(length=200), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_by", sa.Uuid(), nullable=False),
        sa.Column("match_status", sa.String(length=10), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "match_status in ('matched', 'unmatched')",
            name=op.f("ck_external_document_match_status"),
        ),
        sa.CheckConstraint(
            "received_via in ('upload')", name=op.f("ck_external_document_received_via")
        ),
        sa.ForeignKeyConstraint(
            ["external_lab_id"],
            ["external_lab.id"],
            name=op.f("fk_external_document_external_lab_id_external_lab"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["stored_file.id"], name=op.f("fk_external_document_file_id_stored_file")
        ),
        sa.ForeignKeyConstraint(
            ["received_by"], ["app_user.id"], name=op.f("fk_external_document_received_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["visit_id"], ["visit.id"], name=op.f("fk_external_document_visit_id_visit")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_document")),
    )
    op.create_index(
        op.f("ix_external_document_visit_id"), "external_document", ["visit_id"], unique=False
    )
    op.create_table(
        "external_document_test",
        sa.Column("external_document_id", sa.Uuid(), nullable=False),
        sa.Column("order_test_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["external_document_id"],
            ["external_document.id"],
            name=op.f("fk_external_document_test_external_document_id_external_document"),
        ),
        sa.ForeignKeyConstraint(
            ["order_test_id"],
            ["order_test.id"],
            name=op.f("fk_external_document_test_order_test_id_order_test"),
        ),
        sa.PrimaryKeyConstraint(
            "external_document_id", "order_test_id", name=op.f("pk_external_document_test")
        ),
    )
    op.create_index(
        op.f("ix_external_document_test_order_test_id"),
        "external_document_test",
        ["order_test_id"],
        unique=False,
    )
    op.create_table(
        "order_test_event",
        sa.Column("order_test_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(length=14), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("by", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "event in ('routed', 'received', 'sent', 'received_back', 'resulted', 'verified',"
            " 'reopened')",
            name=op.f("ck_order_test_event_event"),
        ),
        sa.ForeignKeyConstraint(
            ["by"], ["app_user.id"], name=op.f("fk_order_test_event_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["order_test_id"],
            ["order_test.id"],
            name=op.f("fk_order_test_event_order_test_id_order_test"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_test_event")),
    )
    op.create_index(
        op.f("ix_order_test_event_order_test_id"),
        "order_test_event",
        ["order_test_id"],
        unique=False,
    )
    op.create_table(
        "result",
        sa.Column("order_test_id", sa.Uuid(), nullable=False),
        sa.Column("parameter_id", sa.Uuid(), nullable=False),
        sa.Column("value_num", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("value_text", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("flag", sa.String(length=2), nullable=True),
        sa.Column("band_label", sa.String(length=40), nullable=False),
        sa.Column("band_severity", sa.String(length=12), nullable=True),
        sa.Column("ref_range_text", sa.String(length=200), nullable=False),
        sa.Column("ref_low", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("ref_high", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("crit_low", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("crit_high", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("source", sa.String(length=12), nullable=False),
        sa.Column("not_calculable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "absurd_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("comment", sa.String(length=300), nullable=False),
        sa.Column("entered_by", sa.Uuid(), nullable=True),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "band_severity is null or band_severity in ('normal', 'borderline', 'abnormal')",
            name=op.f("ck_result_band_severity"),
        ),
        sa.CheckConstraint(
            "flag is null or flag in ('N', 'L', 'H', 'LL', 'HH', 'A')", name=op.f("ck_result_flag")
        ),
        sa.CheckConstraint(
            "source in ('manual', 'calculated', 'external_pdf')", name=op.f("ck_result_source")
        ),
        sa.CheckConstraint(
            "not (not_calculable and value_num is not null)", name=op.f("ck_result_not_calculable")
        ),
        sa.ForeignKeyConstraint(
            ["entered_by"], ["app_user.id"], name=op.f("fk_result_entered_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["order_test_id"], ["order_test.id"], name=op.f("fk_result_order_test_id_order_test")
        ),
        sa.ForeignKeyConstraint(
            ["parameter_id"],
            ["test_parameter.id"],
            name=op.f("fk_result_parameter_id_test_parameter"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_result")),
        sa.UniqueConstraint(
            "order_test_id", "parameter_id", name=op.f("uq_result_order_test_id_parameter_id")
        ),
    )
    op.create_index(op.f("ix_result_order_test_id"), "result", ["order_test_id"], unique=False)
    op.create_index(op.f("ix_result_parameter_id"), "result", ["parameter_id"], unique=False)
    op.create_table(
        "verification",
        sa.Column("order_test_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("verified_by", sa.Uuid(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("level in (1, 2)", name=op.f("ck_verification_level")),
        sa.ForeignKeyConstraint(
            ["order_test_id"],
            ["order_test.id"],
            name=op.f("fk_verification_order_test_id_order_test"),
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"], ["app_user.id"], name=op.f("fk_verification_verified_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification")),
    )
    op.create_index(
        op.f("ix_verification_order_test_id"), "verification", ["order_test_id"], unique=False
    )
    op.create_table(
        "critical_notification",
        sa.Column("result_id", sa.Uuid(), nullable=False),
        sa.Column("reported_value", sa.String(length=40), nullable=False),
        sa.Column("reported_flag", sa.String(length=2), nullable=False),
        sa.Column("informed_to", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=15), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("informed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "mode in ('phone', 'in_person', 'message', 'email')",
            name=op.f("ck_critical_notification_mode"),
        ),
        sa.CheckConstraint(
            "length(btrim(informed_to)) > 0", name=op.f("ck_critical_notification_informed_to")
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["app_user.id"],
            name=op.f("fk_critical_notification_recorded_by_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["result_id"], ["result.id"], name=op.f("fk_critical_notification_result_id_result")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_critical_notification")),
    )
    op.create_index(
        op.f("ix_critical_notification_result_id"),
        "critical_notification",
        ["result_id"],
        unique=False,
    )
    op.create_table(
        "result_revision",
        sa.Column("result_id", sa.Uuid(), nullable=False),
        sa.Column("old_value_num", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("old_value_text", sa.String(length=200), nullable=False),
        sa.Column("old_flag", sa.String(length=2), nullable=True),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("length(btrim(reason)) > 0", name=op.f("ck_result_revision_reason")),
        sa.ForeignKeyConstraint(
            ["changed_by"], ["app_user.id"], name=op.f("fk_result_revision_changed_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["result_id"], ["result.id"], name=op.f("fk_result_revision_result_id_result")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_result_revision")),
    )
    op.create_index(
        op.f("ix_result_revision_result_id"), "result_revision", ["result_id"], unique=False
    )
    op.add_column(
        "order_test",
        sa.Column("route", sa.String(length=10), server_default="in_house", nullable=False),
    )
    op.add_column("order_test", sa.Column("perform_branch_id", sa.Uuid(), nullable=True))
    op.add_column("order_test", sa.Column("external_lab_id", sa.Uuid(), nullable=True))
    op.add_column(
        "order_test", sa.Column("external_cost", sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column(
        "order_test",
        sa.Column("external_accession_no", sa.String(length=40), server_default="", nullable=False),
    )
    op.add_column(
        "order_test",
        sa.Column("route_reason", sa.String(length=200), server_default="", nullable=False),
    )
    op.add_column("order_test", sa.Column("routed_by", sa.Uuid(), nullable=True))
    op.add_column("order_test", sa.Column("routed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(BACKFILL_PERFORM_BRANCH)
    op.alter_column("order_test", "perform_branch_id", nullable=False)
    op.create_check_constraint(
        op.f("ck_order_test_route"), "order_test", "route in ('in_house', 'external')"
    )
    op.create_check_constraint(
        op.f("ck_order_test_route_external"),
        "order_test",
        "(route = 'external') = (external_lab_id is not null)",
    )
    op.create_index(
        "ix_order_test_perform_branch",
        "order_test",
        ["perform_branch_id", "status", "due_at"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_order_test_routed_by_app_user"), "order_test", "app_user", ["routed_by"], ["id"]
    )
    op.create_foreign_key(
        op.f("fk_order_test_external_lab_id_external_lab"),
        "order_test",
        "external_lab",
        ["external_lab_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_order_test_perform_branch_id_branch"),
        "order_test",
        "branch",
        ["perform_branch_id"],
        ["id"],
    )
    op.add_column("sample", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sample", sa.Column("received_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_sample_received_by_app_user"), "sample", "app_user", ["received_by"], ["id"]
    )
    for table in APPEND_ONLY:
        op.execute(
            f"CREATE TRIGGER {table}_no_change BEFORE UPDATE OR DELETE ON {table}"
            " FOR EACH ROW EXECUTE FUNCTION refuse_change()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}"
            " FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()"
        )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_sample_received_by_app_user"), "sample", type_="foreignkey")
    op.drop_column("sample", "received_by")
    op.drop_column("sample", "received_at")
    op.drop_constraint(
        op.f("fk_order_test_perform_branch_id_branch"), "order_test", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_order_test_external_lab_id_external_lab"), "order_test", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_order_test_routed_by_app_user"), "order_test", type_="foreignkey")
    op.drop_index("ix_order_test_perform_branch", table_name="order_test")
    op.drop_constraint(op.f("ck_order_test_route_external"), "order_test", type_="check")
    op.drop_constraint(op.f("ck_order_test_route"), "order_test", type_="check")
    op.drop_column("order_test", "routed_at")
    op.drop_column("order_test", "routed_by")
    op.drop_column("order_test", "route_reason")
    op.drop_column("order_test", "external_accession_no")
    op.drop_column("order_test", "external_cost")
    op.drop_column("order_test", "external_lab_id")
    op.drop_column("order_test", "perform_branch_id")
    op.drop_column("order_test", "route")
    op.drop_index(op.f("ix_result_revision_result_id"), table_name="result_revision")
    op.drop_table("result_revision")
    op.drop_index(op.f("ix_critical_notification_result_id"), table_name="critical_notification")
    op.drop_table("critical_notification")
    op.drop_index(op.f("ix_verification_order_test_id"), table_name="verification")
    op.drop_table("verification")
    op.drop_index(op.f("ix_result_parameter_id"), table_name="result")
    op.drop_index(op.f("ix_result_order_test_id"), table_name="result")
    op.drop_table("result")
    op.drop_index(op.f("ix_order_test_event_order_test_id"), table_name="order_test_event")
    op.drop_table("order_test_event")
    op.drop_index(
        op.f("ix_external_document_test_order_test_id"), table_name="external_document_test"
    )
    op.drop_table("external_document_test")
    op.drop_index(op.f("ix_external_document_visit_id"), table_name="external_document")
    op.drop_table("external_document")
    op.drop_index(
        "uq_external_lab_rate_open",
        table_name="external_lab_rate",
        postgresql_where="valid_to is null",
    )
    op.drop_index("ix_external_lab_rate_test", table_name="external_lab_rate")
    op.drop_table("external_lab_rate")
    op.drop_table("external_lab")
