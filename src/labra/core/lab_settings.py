"""Typed lab settings that admins change at runtime. A branch value beats the instance value,
which beats the default in code."""

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


DEFINITIONS: dict[str, SettingDef] = {}


def define(d: SettingDef) -> SettingDef:
    if d.key in DEFINITIONS:
        raise ValueError(f"Setting {d.key} defined twice.")
    DEFINITIONS[d.key] = d
    return d


define(SettingDef("lab.display_name", str, "Labra Diagnostics", "Lab name on screens"))
define(SettingDef("lab.state_code", str, "", "GST state code of the main lab"))
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
    if d.type is str and len(value) > 500:
        raise ValidationFailedError({d.key: "Keep it under 500 characters."})
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
