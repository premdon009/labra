"""Typed lab settings that admins change at runtime. A branch value beats the instance value,
which beats the default in code."""

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from labra.core import audit
from labra.core.errors import NotFoundError, ValidationFailedError
from labra.core.models import Setting


@dataclass(frozen=True)
class SettingDef:
    key: str
    type: type
    default: Any
    label: str
    per_branch: bool = False
    min_value: int | None = None
    max_value: int | None = None
    # (value, label) pairs; the first is the default.
    choices: tuple[tuple[str, str], ...] = ()
    max_length: int = 500
    pattern: str | None = None
    pattern_hint: str = ""
    # Settings with a group are edited on their own screen, not the main settings page.
    group: str = ""


DEFINITIONS: dict[str, SettingDef] = {}


def define(d: SettingDef) -> SettingDef:
    if d.key in DEFINITIONS:
        raise ValueError(f"Setting {d.key} defined twice.")
    DEFINITIONS[d.key] = d
    return d


define(SettingDef("lab.display_name", str, "Labra Diagnostics", "Lab name on screens"))
define(
    SettingDef(
        "lab.state_code",
        str,
        "",
        "GST state code of the main lab",
        pattern=r"(\d{2})?",
        pattern_hint="Enter two digits, for example 29, or leave it empty.",
    )
)
define(
    SettingDef(
        "visit.default_tat_hours",
        int,
        24,
        "Default turnaround time (hours)",
        per_branch=True,
        min_value=1,
        max_value=720,
    )
)
define(SettingDef("branch.receipt_footer", str, "", "Footer printed on receipts", per_branch=True))
define(
    SettingDef(
        "lab.legal_name",
        str,
        "",
        "Legal name printed on bills (empty: the lab name)",
        max_length=120,
    )
)
define(
    SettingDef(
        "billing.sac_code",
        str,
        "999316",
        "SAC code printed on bill lines",
        pattern=r"^\d{4,8}$",
        pattern_hint="Enter 4 to 8 digits.",
    )
)
define(
    SettingDef(
        "billing.exemption_note",
        str,
        "Health care services by a clinical establishment are exempt from GST.",
        "Exemption note printed on bills",
        max_length=200,
    )
)
define(
    SettingDef(
        "lab.receive_step",
        str,
        "other_branches",
        "Scan samples in when they reach the lab",
        choices=(
            ("other_branches", "Only samples that come from another branch"),
            ("always", "Every sample"),
            ("never", "Never: a collected sample is in the lab at once"),
        ),
    )
)
define(
    SettingDef(
        "report.default_mode",
        str,
        "combined",
        "Reports for a visit with outsourced tests",
        choices=(
            ("combined", "One report with every test"),
            ("separate", "The lab's own report, plus one per outside lab document"),
        ),
    )
)
define(
    SettingDef(
        "report.reference_column",
        str,
        "show",
        "Reference interval column on reports",
        choices=(("show", "Show it"), ("hide", "Hide it")),
    )
)
define(
    SettingDef(
        "report.verify_base_url",
        str,
        "",
        "Web address the report QR code points to (empty: the QR code carries the report "
        "number and a check code)",
        max_length=120,
        pattern=r"(https://[A-Za-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~-]+)*)?",
        pattern_hint="Enter an https:// address without a trailing slash, or leave it empty.",
    )
)
define(SettingDef("report.footer_text", str, "", "Footer printed on reports", max_length=200))
define(
    SettingDef(
        "letterhead.raster_dpi",
        int,
        150,
        "Resolution for picture letterheads (dots per inch)",
        min_value=150,
        max_value=200,
    )
)
define(
    SettingDef(
        "print.default_mode",
        str,
        "print",
        "What the Print button makes",
        per_branch=True,
        choices=(
            ("print", "A PDF for pre-printed letterhead paper (no letterhead)"),
            ("digital", "A PDF with the letterhead on it"),
        ),
    )
)
for _axis, _way in (("x", "right"), ("y", "down")):
    define(
        SettingDef(
            f"print.offset_{_axis}_mm",
            int,
            0,
            f"Printer offset {_way} (mm, negative for the other way)",
            per_branch=True,
            min_value=-10,
            max_value=10,
        )
    )


def _currency(key: str, default: str, label: str, **kw: Any) -> None:
    define(
        SettingDef(f"currency.{key}", str, default, label, per_branch=True, group="currency", **kw)
    )


_currency(
    "code",
    "INR",
    "Currency code",
    max_length=3,
    pattern=r"[A-Z]{3}",
    pattern_hint="Use the three capital letters of the currency, such as INR.",
)
_currency("symbol", "₹", "Currency symbol (may be blank)", max_length=5)
_currency(
    "symbol_position",
    "before",
    "Where the symbol goes",
    choices=(
        ("before", "Before the amount: ₹1,737.00"),
        ("before_space", "Before, with a space: ₹ 1,737.00"),
        ("after", "After the amount: 1,737.00₹"),
        ("after_space", "After, with a space: 1,737.00 ₹"),
    ),
)
_currency(
    "grouping",
    "indian",
    "Digit grouping",
    choices=(
        ("indian", "Lakh and crore: 1,23,45,678"),
        ("international", "Thousands and millions: 12,345,678"),
    ),
)
_currency(
    "decimals",
    "2",
    "Decimals shown",
    choices=(("2", "Two: 1,737.50"), ("0", "None: 1,738")),
)
_currency(
    "show_in_columns",
    "header",
    "Symbol in bill columns",
    choices=(("header", "Once, in the column heading"), ("every", "On every amount")),
)
_currency(
    "words",
    "indian",
    "Amount in words",
    choices=(("indian", "Lakh and crore"), ("international", "Million and billion")),
)
_currency("word_major", "rupees", "Word for the main unit", max_length=20)
_currency("word_minor", "paise", "Word for the small unit", max_length=20)
_currency(
    "round_off_to",
    "1.00",
    "Round bill totals to",
    choices=(
        ("1.00", "The nearest rupee"),
        ("0.50", "The nearest 50 paise"),
        ("0.10", "The nearest 10 paise"),
        ("none", "No rounding"),
    ),
)


def coerce(d: SettingDef, raw: Any) -> Any:
    """Turn a form or JSON value into the setting's type, or raise ValidationFailedError."""
    try:
        if d.type is bool:
            if isinstance(raw, str):
                value: Any = raw.strip().lower() in {"1", "true", "yes", "on"}
            else:
                value = bool(raw)
        elif d.type is int:
            value = int(str(raw).strip())
        else:
            value = str(raw).strip()
    except ValueError:
        raise ValidationFailedError({d.key: "Enter a whole number."}) from None
    if d.type is int:
        if d.min_value is not None and value < d.min_value:
            raise ValidationFailedError({d.key: f"Must be at least {d.min_value}."})
        if d.max_value is not None and value > d.max_value:
            raise ValidationFailedError({d.key: f"Must be at most {d.max_value}."})
    if d.type is str and len(value) > d.max_length:
        raise ValidationFailedError({d.key: f"Use at most {d.max_length} characters."})
    if d.choices and value not in {c for c, _ in d.choices}:
        raise ValidationFailedError({d.key: "Choose one of the listed values."})
    if d.pattern is not None and not re.fullmatch(d.pattern, value):
        raise ValidationFailedError({d.key: d.pattern_hint or "That value isn't allowed."})
    return value


def _definition(key: str) -> SettingDef:
    d = DEFINITIONS.get(key)
    if d is None:
        raise NotFoundError(f"Unknown setting {key}.")
    return d


def get_value(db: Session, key: str, branch_id: uuid.UUID | None = None) -> Any:
    d = _definition(key)
    scope = Setting.branch_id.is_(None)
    if branch_id is not None:
        scope = or_(scope, Setting.branch_id == branch_id)
    rows = {
        s.branch_id: s.value for s in db.scalars(select(Setting).where(Setting.key == key, scope))
    }
    if branch_id is not None and branch_id in rows:
        return rows[branch_id]
    return rows.get(None, d.default)


def set_value(
    db: Session,
    key: str,
    raw: Any,
    user_id: uuid.UUID | None,
    branch_id: uuid.UUID | None = None,
) -> Any:
    d = _definition(key)
    if branch_id is not None and not d.per_branch:
        raise ValidationFailedError({key: "This setting applies to the whole lab."})
    value = coerce(d, raw)
    row = db.scalar(select(Setting).where(Setting.key == key, Setting.branch_id == branch_id))
    old = row.value if row else None
    if row is None:
        row = Setting(key=key, branch_id=branch_id, value=value, created_by=user_id)
        db.add(row)
    else:
        row.value = value
        row.updated_by = user_id
    db.flush()
    audit.record(
        db,
        "setting.change",
        "setting",
        row.id,
        {"key": key, "old": old, "new": value},
        user_id=user_id,
        branch_id=branch_id,
    )
    return value
