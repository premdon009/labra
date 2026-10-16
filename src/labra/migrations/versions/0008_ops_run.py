"""The run log of the scheduled jobs: backups, restore drills, audit and disk checks, upgrades.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ops_run",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("snapshot", sa.String(length=200), nullable=True),
        sa.Column("bytes_added", sa.BigInteger(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind in ('backup', 'drill', 'verify', 'disk', 'upgrade')", name=op.f("ck_ops_run_kind")
        ),
        sa.CheckConstraint("finished_at >= started_at", name=op.f("ck_ops_run_finished_at")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ops_run")),
    )
    op.create_index("ix_ops_run_kind_started_at", "ops_run", ["kind", "started_at"])
    # Written once and never changed (refuse_change() comes from 0003).
    op.execute(
        "CREATE TRIGGER ops_run_no_change BEFORE UPDATE OR DELETE ON ops_run"
        " FOR EACH ROW EXECUTE FUNCTION refuse_change()"
    )
    op.execute(
        "CREATE TRIGGER ops_run_no_truncate BEFORE TRUNCATE ON ops_run"
        " FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()"
    )


def downgrade() -> None:
    op.drop_index("ix_ops_run_kind_started_at", table_name="ops_run")
    op.drop_table("ops_run")
