"""Number series for branches that were set up before every branch was given its own.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The formats a new branch started with when this was written. A series a branch already
# has is left as it is, whatever its format. The financial year starts on 1 April in India.
# A colon inside a format is escaped so it isn't read as a query parameter.
ADD_MISSING_SERIES = r"""
INSERT INTO number_series
    (id, branch_id, doc_type, format, fin_year, next_value, created_at, updated_at, row_version)
SELECT gen_random_uuid(), b.id, d.doc_type, d.format,
       CASE WHEN extract(month FROM today.day) >= 4
            THEN extract(year FROM today.day)::int
            ELSE extract(year FROM today.day)::int - 1 END,
       1, now(), now(), 1
FROM branch b
CROSS JOIN (VALUES
    ('patient', '{BR}/P/{SEQ\:6}'),
    ('visit', '{BR}/V/{FY2}/{SEQ\:5}'),
    ('bos', '{BR}/{FY2}/{SEQ\:5}'),
    ('receipt', '{BR}/RC/{FY2}/{SEQ\:5}'),
    ('refund', '{BR}/RF/{FY2}/{SEQ\:5}'),
    ('sample', '{BR}{FY2}{SEQ\:6}')
) AS d (doc_type, format)
CROSS JOIN (SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date AS day) AS today
WHERE NOT EXISTS (
    SELECT 1 FROM number_series s WHERE s.branch_id = b.id AND s.doc_type = d.doc_type
)
"""


def upgrade() -> None:
    op.execute(ADD_MISSING_SERIES)


def downgrade() -> None:
    # The series may have issued numbers by now, so they stay.
    pass
