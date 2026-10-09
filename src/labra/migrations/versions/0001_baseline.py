"""Baseline: settings, numbering, files, outbox, audit log, consent, branches, staff,
roles, sessions.

Revision ID: 0001
Revises:
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The audit log is append-only, enforced by the database itself (design §5).
AUDIT_GUARD = """
CREATE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;
CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only();
"""


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("username", sa.String(length=40), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=15), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("can_login", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("username", name=op.f("uq_app_user_username")),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("entity", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_table(
        "branch",
        sa.Column("code", sa.String(length=4), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("phone", sa.String(length=15), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_branch")),
        sa.UniqueConstraint("code", name=op.f("uq_branch_code")),
    )
    op.create_table(
        "consent",
        sa.Column("subject_type", sa.String(length=30), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=60), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consent")),
    )
    op.create_index(op.f("ix_consent_subject_id"), "consent", ["subject_id"], unique=False)
    op.create_table(
        "event_outbox",
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_outbox")),
    )
    op.create_index(
        "ix_event_outbox_pending",
        "event_outbox",
        ["available_at"],
        unique=False,
        postgresql_where="processed_at IS NULL",
    )
    op.create_table(
        "login_attempt",
        sa.Column("username", sa.String(length=40), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempt")),
    )
    op.create_index(
        "ix_login_attempt_lookup", "login_attempt", ["username", "ip", "at"], unique=False
    )
    op.create_table(
        "role",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role")),
        sa.UniqueConstraint("code", name=op.f("uq_role_code")),
    )
    op.create_table(
        "stored_file",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_file")),
    )
    op.create_index(op.f("ix_stored_file_sha256"), "stored_file", ["sha256"], unique=False)
    op.create_table(
        "local_credential",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_local_credential_user_id_app_user")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_local_credential")),
    )
    op.create_table(
        "number_series",
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("doc_type", sa.String(length=20), nullable=False),
        sa.Column("format", sa.String(length=60), nullable=False),
        sa.Column("fin_year", sa.Integer(), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_number_series_branch_id_branch")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_number_series")),
        sa.UniqueConstraint(
            "doc_type",
            "branch_id",
            name=op.f("uq_number_series_doc_type_branch_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "role_permission",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission", sa.String(length=60), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
            name=op.f("fk_role_permission_role_id_role"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission", name=op.f("pk_role_permission")),
    )
    op.create_table(
        "setting",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_setting_branch_id_branch")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_setting")),
        sa.UniqueConstraint(
            "key",
            "branch_id",
            name=op.f("uq_setting_key_branch_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "user_branch_role",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_user_branch_role_branch_id_branch")
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["role.id"], name=op.f("fk_user_branch_role_role_id_role")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_branch_role_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "branch_id", "role_id", name=op.f("pk_user_branch_role")
        ),
    )
    op.create_table(
        "user_session",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_user_session_branch_id_branch")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_session_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_session_token_hash")),
    )
    op.create_index(op.f("ix_user_session_user_id"), "user_session", ["user_id"], unique=False)
    op.execute(AUDIT_GUARD)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only() CASCADE")
    op.drop_table("user_session")
    op.drop_table("user_branch_role")
    op.drop_table("setting")
    op.drop_table("role_permission")
    op.drop_table("number_series")
    op.drop_table("local_credential")
    op.drop_table("stored_file")
    op.drop_table("role")
    op.drop_table("login_attempt")
    op.drop_table("event_outbox")
    op.drop_table("consent")
    op.drop_table("branch")
    op.drop_table("audit_log")
    op.drop_table("app_user")
