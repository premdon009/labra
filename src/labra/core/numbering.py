"""Document numbers: `{BR}/BS/{FY2}/{SEQ:5}` → `B2/BS/2627/00123` (design §5.1).

Numbers restart each Indian financial year (1 April). Issuing one locks the series row, so
two counters never get the same number and none is skipped.
"""

import re
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core.errors import ConfigError, NotFoundError
from labra.core.models import NumberSeries

# GST Rules 46 and 49: invoice-type numbers are at most 16 characters of letters, digits,
# hyphen and slash.
GST_DOC_TYPES = frozenset({"bos", "tax_inv", "credit_note"})
GST_MAX_LENGTH = 16
_GST_CHARS = re.compile(r"^[A-Za-z0-9/-]+$")

_TOKEN = re.compile(r"\{([A-Z0-9]+)(?::(\d))?\}")
MAX_BRANCH_CODE = 4


def financial_year(day: date) -> int:
    """The calendar year the financial year started in: 2026-04-01 to 2027-03-31 is 2026."""
    return day.year if day.month >= 4 else day.year - 1


def render(fmt: str, branch_code: str, fin_year: int, seq: int) -> str:
    def token(m: re.Match[str]) -> str:
        name, width = m.group(1), m.group(2)
        if name == "BR":
            return branch_code
        if name == "FY2":
            return f"{fin_year % 100:02d}{(fin_year + 1) % 100:02d}"
        if name == "FY":
            return f"{fin_year}-{(fin_year + 1) % 100:02d}"
        if name == "SEQ":
            return f"{seq:0{int(width or 1)}d}"
        raise ConfigError(f"Unknown token {{{name}}} in number format '{fmt}'.")

    return _TOKEN.sub(token, fmt)


def format_problems(doc_type: str, fmt: str, branch_code: str | None = None) -> list[str]:
    """Why a format can't be used; empty when it's fine. Checks the longest number the
    format can produce, with the series' branch code or else the longest allowed one."""
    m = re.search(r"\{SEQ:(\d)\}", fmt)
    if m is None:
        return ["The format needs a {SEQ:n} part, for example {SEQ:5}."]
    code = branch_code if branch_code is not None else "X" * MAX_BRANCH_CODE
    try:
        longest = render(fmt, code, 2099, 10 ** int(m.group(1)) - 1)
    except ConfigError as exc:
        return [exc.public_message]
    problems = []
    if doc_type in GST_DOC_TYPES:
        if len(longest) > GST_MAX_LENGTH:
            problems.append(
                f"Bill and invoice numbers can be at most {GST_MAX_LENGTH} characters; "
                f"this format reaches {len(longest)} ({longest})."
            )
        if not _GST_CHARS.match(longest):
            problems.append("Bill and invoice numbers may use only letters, digits, - and /.")
    return problems


def next_number(
    db: Session, doc_type: str, branch_id: uuid.UUID | None, branch_code: str, today: date
) -> str:
    """Issue the next number in the caller's transaction. The row lock is held until commit."""
    series = db.scalar(
        select(NumberSeries)
        .where(NumberSeries.doc_type == doc_type, NumberSeries.branch_id == branch_id)
        .with_for_update()
    )
    if series is None:
        raise NotFoundError(f"No number series for {doc_type}.")
    fy = financial_year(today)
    if series.fin_year != fy:
        series.fin_year = fy
        series.next_value = 1
    number = render(series.format, branch_code, fy, series.next_value)
    if doc_type in GST_DOC_TYPES and len(number) > GST_MAX_LENGTH:
        # The format check should have caught this; refuse rather than print a bad invoice.
        raise ConfigError(f"Number {number} is longer than {GST_MAX_LENGTH} characters.")
    series.next_value += 1
    db.flush()
    return number
