"""Phone searches by their first digits read an index: pattern-operator indexes on both
phone columns, in place of the plain one, which a prefix search can't use outside the C
collation.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_patient_phone", table_name="patient")
    op.create_index(
        "ix_patient_phone_prefix",
        "patient",
        ["phone"],
        postgresql_ops={"phone": "varchar_pattern_ops"},
    )
    op.create_index(
        "ix_patient_alt_phone_prefix",
        "patient",
        ["alt_phone"],
        postgresql_ops={"alt_phone": "varchar_pattern_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_patient_alt_phone_prefix", table_name="patient")
    op.drop_index("ix_patient_phone_prefix", table_name="patient")
    op.create_index("ix_patient_phone", "patient", ["phone"])
