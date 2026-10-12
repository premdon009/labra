"""Consent notice: the versioned wording a patient agrees to, and each consent's link to it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Rows that must never change once written. Later tables reuse the same function.
REFUSE_CHANGE = """
CREATE FUNCTION refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;
CREATE TRIGGER consent_notice_no_change BEFORE UPDATE OR DELETE ON consent_notice
    FOR EACH ROW EXECUTE FUNCTION refuse_change();
CREATE TRIGGER consent_notice_no_truncate BEFORE TRUNCATE ON consent_notice
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_change();
"""

FIRST_NOTICE = (
    "I agree to the tests ordered today being done on my samples, and to my samples and "
    "details being shared with a referral lab when a test is sent out. "
    "(Replace this with your lab's wording.)"
)


def upgrade() -> None:
    op.create_table(
        "consent_notice",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=8), server_default="en", nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consent_notice")),
        sa.UniqueConstraint("version", "language", name=op.f("uq_consent_notice_version_language")),
    )
    op.execute(
        sa.text(
            "INSERT INTO consent_notice (id, version, language, body_text, effective_from) "
            "VALUES (gen_random_uuid(), 1, 'en', :body, now())"
        ).bindparams(body=FIRST_NOTICE)
    )
    op.execute(REFUSE_CHANGE)
    op.add_column("consent", sa.Column("notice_id", sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE consent SET notice_id = "
        "(SELECT id FROM consent_notice WHERE version = 1 AND language = 'en')"
    )
    op.alter_column("consent", "notice_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_consent_notice_id_consent_notice"),
        "consent",
        "consent_notice",
        ["notice_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_consent_notice_id_consent_notice"), "consent", type_="foreignkey")
    op.drop_column("consent", "notice_id")
    op.execute("DROP FUNCTION IF EXISTS refuse_change() CASCADE")
    op.drop_table("consent_notice")
