"""Departments, specimen types, tests, parameters, ranges, methods, presets, packages and
prices. Every function takes the acting Principal and checks it, so a route can't forget to.
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, literal, or_, select, union_all, update
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.catalog import formula
from labra.catalog.models import (
    BAND_SEVERITIES,
    ITEM_TYPES,
    RANGE_CONDITIONS,
    RESULT_TYPES,
    SEXES,
    CommentPreset,
    Department,
    Package,
    PackageItem,
    Price,
    ReferenceBand,
    ReferenceRange,
    SpecimenType,
    Test,
    TestMethod,
    TestParameter,
)
from labra.catalog.units import UNITS
from labra.core import audit
from labra.core.dialect import list_as_text, list_contains, similar, similarity
from labra.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from labra.core.ids import utcnow
from labra.core.paging import Page, page_of
from labra.org.models import Branch
from labra.org.service import stale

_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_.+-]{0,19}$")
_PARAM_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,19}$")
_SPECIMEN_RE = re.compile(r"^[A-Z0-9_]{1,20}$")
MAX_AGE_DAYS = 54750


def _check(principal: Principal, permission: str) -> None:
    if not principal.can(permission):
        raise PermissionDeniedError()


def _get[T](db: Session, model: type[T], record_id: uuid.UUID) -> T:
    record = db.get(model, record_id)
    if record is None:
        raise NotFoundError()
    return record


def _apply(
    db: Session,
    principal: Principal,
    record: Any,
    values: dict[str, Any],
    row_version: int,
    action: str,
) -> list[str]:
    """Copy `values` onto `record` after the stale-edit check; audit before and after."""
    if record.row_version != row_version:
        raise stale(db, record)
    changes = {k: (getattr(record, k), v) for k, v in values.items() if getattr(record, k) != v}
    for k, (_, new) in changes.items():
        setattr(record, k, new)
    if changes:
        record.updated_by = principal.user_id
        db.flush()
        audit.record(
            db,
            action,
            record.__tablename__,
            record.id,
            {
                "before": {k: old for k, (old, _) in changes.items()},
                "after": {k: new for k, (_, new) in changes.items()},
            },
            user_id=principal.user_id,
        )
    return list(changes)


def _create(db: Session, principal: Principal, record: Any, action: str, detail: dict) -> Any:
    record.created_by = principal.user_id
    db.add(record)
    db.flush()
    audit.record(db, action, record.__tablename__, record.id, detail, user_id=principal.user_id)
    return record


def _decimal(raw: str | Decimal | None, problems: dict[str, str], key: str) -> Decimal | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        problems[key] = "Enter a number, for example 4.5."
        return None
    if not value.is_finite():
        problems[key] = "Enter a number, for example 4.5."
        return None
    return value


# Departments and specimen types


def department_page(db: Session, principal: Principal, page: int) -> Page[Department]:
    _check(principal, "catalog.view")
    stmt = select(Department).order_by(Department.report_order, Department.name, Department.id)
    return page_of(db, stmt, page)


def next_report_order(db: Session) -> int:
    """Where a new department goes by default: after the last one."""
    return (db.scalar(select(func.max(Department.report_order))) or 0) + 10


def list_departments(db: Session, principal: Principal) -> list[Department]:
    _check(principal, "catalog.view")
    return list(db.scalars(select(Department).order_by(Department.report_order, Department.name)))


def save_department(
    db: Session,
    principal: Principal,
    name: str,
    report_order: int,
    is_active: bool = True,
    department_id: uuid.UUID | None = None,
    row_version: int = 0,
) -> Department:
    _check(principal, "catalog.edit")
    name = name.strip()
    if not name:
        raise ValidationFailedError({"name": "Enter the department name."})
    clash = db.scalar(select(Department.id).where(func.lower(Department.name) == name.lower()))
    if clash is not None and clash != department_id:
        raise ValidationFailedError({"name": f"There is already a department called {name}."})
    values = {"name": name, "report_order": report_order, "is_active": is_active}
    if department_id is None:
        return _create(db, principal, Department(**values), "department.create", {"name": name})
    dept = _get(db, Department, department_id)
    _apply(db, principal, dept, values, row_version, "department.update")
    return dept


def specimen_type_page(db: Session, principal: Principal, page: int) -> Page[SpecimenType]:
    _check(principal, "catalog.view")
    return page_of(db, select(SpecimenType).order_by(SpecimenType.name, SpecimenType.id), page)


def list_specimen_types(db: Session, principal: Principal) -> list[SpecimenType]:
    _check(principal, "catalog.view")
    return list(db.scalars(select(SpecimenType).order_by(SpecimenType.name)))


def save_specimen_type(
    db: Session,
    principal: Principal,
    code: str,
    name: str,
    container: str = "",
    is_active: bool = True,
    specimen_type_id: uuid.UUID | None = None,
    row_version: int = 0,
) -> SpecimenType:
    _check(principal, "catalog.edit")
    code = code.strip().upper()
    problems: dict[str, str] = {}
    if not _SPECIMEN_RE.match(code):
        problems["code"] = "Use capital letters, digits and _, for example EDTA."
    if not name.strip():
        problems["name"] = "Enter the specimen name."
    clash = db.scalar(select(SpecimenType.id).where(SpecimenType.code == code))
    if clash is not None and clash != specimen_type_id:
        problems["code"] = f"Specimen code {code} is already used."
    if problems:
        raise ValidationFailedError(problems)
    values = {
        "code": code,
        "name": name.strip(),
        "container": container.strip(),
        "is_active": is_active,
    }
    if specimen_type_id is None:
        return _create(
            db, principal, SpecimenType(**values), "specimen_type.create", {"code": code}
        )
    st = _get(db, SpecimenType, specimen_type_id)
    _apply(db, principal, st, values, row_version, "specimen_type.update")
    return st


# Tests


@dataclass
class TestInput:
    __test__ = False  # not a pytest test class

    code: str
    name: str
    department_id: uuid.UUID
    aliases: list[str] = field(default_factory=list)
    short_name: str = ""
    specimen_type_id: uuid.UUID | None = None
    default_tat_hours: int = 24
    in_house_available: bool = True
    interpretation_text: str = ""
    is_active: bool = True


def _code_taken(
    db: Session, code: str, *, test_id: uuid.UUID | None = None, package_id: uuid.UUID | None = None
) -> bool:
    """Codes and aliases are one namespace across tests and packages, so a typed code finds
    exactly one thing."""
    t = db.scalar(
        select(Test.id).where(or_(Test.code == code, list_contains(Test.aliases, code))).limit(1)
    )
    if t is not None and t != test_id:
        return True
    p = db.scalar(select(Package.id).where(Package.code == code))
    return p is not None and p != package_id


def _validate_test(db: Session, data: TestInput, test_id: uuid.UUID | None) -> None:
    data.code = data.code.strip().lower()
    data.aliases = sorted({a.strip().lower() for a in data.aliases if a.strip()} - {data.code})
    data.name = data.name.strip()
    data.short_name = data.short_name.strip()
    problems: dict[str, str] = {}
    if not _CODE_RE.match(data.code):
        problems["code"] = "Use up to 20 small letters, digits or . _ + -, for example hb."
    elif _code_taken(db, data.code, test_id=test_id):
        problems["code"] = f"The code {data.code} is already used."
    bad = [a for a in data.aliases if not _CODE_RE.match(a)]
    taken = [a for a in data.aliases if a not in bad and _code_taken(db, a, test_id=test_id)]
    if bad:
        problems["aliases"] = f"Not a valid code: {', '.join(bad)}."
    elif taken:
        problems["aliases"] = f"Already used: {', '.join(taken)}."
    if not data.name:
        problems["name"] = "Enter the test name."
    if db.get(Department, data.department_id) is None:
        problems["department_id"] = "Choose a department."
    if data.specimen_type_id and db.get(SpecimenType, data.specimen_type_id) is None:
        problems["specimen_type_id"] = "Choose a specimen type."
    if not 0 < data.default_tat_hours <= 24 * 60:
        problems["default_tat_hours"] = "Between 1 and 1440 hours."
    if problems:
        raise ValidationFailedError(problems)


def test_page(
    db: Session,
    principal: Principal,
    page: int,
    department_id: uuid.UUID | None = None,
    text: str = "",
) -> Page[Test]:
    """Tests whose code or name contains `text`, or with an alias starting with it."""
    _check(principal, "catalog.view")
    q = select(Test).order_by(Test.code)
    if department_id:
        q = q.where(Test.department_id == department_id)
    text = text.strip().lower()
    if text:
        aliases = literal(" ") + list_as_text(Test.aliases)
        q = q.where(
            or_(
                func.lower(Test.code).contains(text, autoescape=True),
                func.lower(Test.name).contains(text, autoescape=True),
                aliases.contains(" " + text, autoescape=True),
            )
        )
    return page_of(db, q, page)


def list_tests(
    db: Session, principal: Principal, department_id: uuid.UUID | None = None
) -> list[Test]:
    _check(principal, "catalog.view")
    q = select(Test).order_by(Test.code)
    if department_id:
        q = q.where(Test.department_id == department_id)
    return list(db.scalars(q))


def tests_by_id(
    db: Session, principal: Principal, ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, Test]:
    _check(principal, "catalog.view")
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {t.id: t for t in db.scalars(select(Test).where(Test.id.in_(wanted)))}


def tests_by_code(db: Session, principal: Principal, typed: str) -> tuple[list[Test], list[str]]:
    """The tests in use that a line of codes or aliases names, split at spaces and commas,
    and the codes that name none."""
    _check(principal, "catalog.view")
    codes = list(dict.fromkeys(c for c in re.split(r"[\s,;]+", typed.lower()) if c))[:50]
    found: list[Test] = []
    unknown: list[str] = []
    for code in codes:
        test = db.scalar(
            select(Test)
            .where(Test.is_active, or_(Test.code == code, list_contains(Test.aliases, code)))
            .limit(1)
        )
        if test is None:
            unknown.append(code)
        else:
            found.append(test)
    return found, unknown


def get_test(db: Session, principal: Principal, test_id: uuid.UUID) -> Test:
    _check(principal, "catalog.view")
    return _get(db, Test, test_id)


def save_test(
    db: Session,
    principal: Principal,
    data: TestInput,
    test_id: uuid.UUID | None = None,
    row_version: int = 0,
) -> Test:
    _check(principal, "catalog.edit")
    _validate_test(db, data, test_id)
    if test_id is None:
        return _create(db, principal, Test(**vars(data)), "test.create", {"code": data.code})
    test = _get(db, Test, test_id)
    _apply(db, principal, test, vars(data), row_version, "test.update")
    return test


# Parameters


@dataclass
class ParameterInput:
    code: str
    name: str
    result_type: str
    unit_ucum: str = ""
    decimals: int = 0
    formula: str = ""
    formula_valid_if: str = ""
    options: list[dict[str, Any]] = field(default_factory=list)
    text_pattern: str = ""
    display_order: int = 0
    is_reportable: bool = True
    is_active: bool = True


def list_parameters(db: Session, principal: Principal, test_id: uuid.UUID) -> list[TestParameter]:
    _check(principal, "catalog.view")
    return list(
        db.scalars(
            select(TestParameter)
            .where(TestParameter.test_id == test_id)
            .order_by(TestParameter.display_order, TestParameter.name)
        )
    )


def get_parameter(db: Session, principal: Principal, parameter_id: uuid.UUID) -> TestParameter:
    _check(principal, "catalog.view")
    return _get(db, TestParameter, parameter_id)


def _formula_inputs(db: Session, test_id: uuid.UUID, skip: uuid.UUID | None) -> dict[str, str]:
    """code → formula of the test's other active parameters."""
    rows = db.execute(
        select(TestParameter.id, TestParameter.code, TestParameter.formula).where(
            TestParameter.test_id == test_id, TestParameter.is_active
        )
    )
    return {code: f for pid, code, f in rows if pid != skip}


def _creates_cycle(code: str, uses: set[str], others: dict[str, str]) -> bool:
    seen: set[str] = set()
    todo = list(uses)
    while todo:
        name = todo.pop()
        if name == code:
            return True
        if name in seen or not others.get(name):
            continue
        seen.add(name)
        todo.extend(formula.parse(others[name])[1])
    return False


def _formula_problems(data: ParameterInput, others: dict[str, str]) -> dict[str, str]:
    problems: dict[str, str] = {}
    if not data.formula.strip():
        return {"formula": "A calculated parameter needs a formula."}
    try:
        uses = formula.parse(data.formula)[1]
        unknown = sorted(uses - others.keys())
        if unknown:
            problems["formula"] = f"Not a parameter of this test: {', '.join(unknown)}."
        elif _creates_cycle(data.code, uses, others):
            problems["formula"] = "The formula depends on itself."
    except formula.FormulaError as exc:
        problems["formula"] = str(exc)
    if data.formula_valid_if.strip():
        try:
            rule_uses = formula.parse(data.formula_valid_if, condition=True)[1]
            unknown = sorted(rule_uses - others.keys())
            if unknown:
                problems["formula_valid_if"] = (
                    f"Not a parameter of this test: {', '.join(unknown)}."
                )
        except formula.FormulaError as exc:
            problems["formula_valid_if"] = str(exc)
    return problems


def _option_problems(data: ParameterInput) -> dict[str, str]:
    values = [str(o.get("value", "")).strip() for o in data.options]
    if not data.options or not all(values) or len(set(values)) != len(values):
        return {"options": "Give each option once, for example Nil, Trace, +."}
    if sum(bool(o.get("default")) for o in data.options) > 1:
        return {"options": "Mark at most one option as the default."}
    data.options = [
        {"value": v, "abnormal": bool(o.get("abnormal")), "default": bool(o.get("default"))}
        for v, o in zip(values, data.options, strict=True)
    ]
    return {}


def _validate_parameter(
    db: Session, test_id: uuid.UUID, data: ParameterInput, parameter_id: uuid.UUID | None
) -> None:
    data.code = data.code.strip()
    data.name = data.name.strip()
    problems: dict[str, str] = {}
    if not _PARAM_CODE_RE.match(data.code):
        problems["code"] = "Start with a letter; letters, digits and _ only, for example HDL."
    if not data.name:
        problems["name"] = "Enter the parameter name."
    if data.result_type not in RESULT_TYPES:
        problems["result_type"] = "Choose numeric, text, option or calculated."
    if data.unit_ucum and data.unit_ucum not in UNITS:
        problems["unit_ucum"] = "Choose a unit from the list."
    if not 0 <= data.decimals <= 4:
        problems["decimals"] = "Between 0 and 4."
    others = _formula_inputs(db, test_id, parameter_id)
    if data.code in others:
        problems["code"] = f"This test already has a parameter {data.code}."
    if data.result_type == "calculated":
        problems |= _formula_problems(data, others)
    else:
        data.formula = data.formula_valid_if = ""
    if data.result_type == "option":
        problems |= _option_problems(data)
    else:
        data.options = []
    if data.result_type != "text":
        data.text_pattern = ""
    elif data.text_pattern:
        try:
            re.compile(data.text_pattern)
        except re.error:
            problems["text_pattern"] = "That pattern can't be read."
    if problems:
        raise ValidationFailedError(problems)


def save_parameter(
    db: Session,
    principal: Principal,
    test_id: uuid.UUID,
    data: ParameterInput,
    parameter_id: uuid.UUID | None = None,
    row_version: int = 0,
) -> TestParameter:
    _check(principal, "catalog.edit")
    _get(db, Test, test_id)
    _validate_parameter(db, test_id, data, parameter_id)
    if parameter_id is None:
        return _create(
            db,
            principal,
            TestParameter(test_id=test_id, **vars(data)),
            "parameter.create",
            {"test_id": str(test_id), "code": data.code},
        )
    param = _get(db, TestParameter, parameter_id)
    if param.test_id != test_id:
        raise NotFoundError()
    _apply(db, principal, param, vars(data), row_version, "parameter.update")
    return param


# Reference ranges


@dataclass
class RangeInput:
    sex: str | None = None
    age_min_days: int = 0
    age_max_days: int = MAX_AGE_DAYS
    condition: str | None = None
    low: Decimal | str | None = None
    high: Decimal | str | None = None
    critical_low: Decimal | str | None = None
    critical_high: Decimal | str | None = None
    absurd_low: Decimal | str | None = None
    absurd_high: Decimal | str | None = None
    display_text: str = ""
    source_citation: str = ""
    is_active: bool = True


@dataclass
class BandInput:
    label: str
    severity: str
    low: Decimal | str | None = None
    high: Decimal | str | None = None


_LIMITS = ("low", "high", "critical_low", "critical_high", "absurd_low", "absurd_high")


def _first(*values: Decimal | None) -> Decimal | None:
    return next((v for v in values if v is not None), None)


def _validate_range(data: RangeInput) -> None:
    problems: dict[str, str] = {}
    data.sex = data.sex or None
    data.condition = data.condition or None
    if data.sex is not None and data.sex not in SEXES:
        problems["sex"] = "Choose male, female, other or any."
    if data.condition is not None and data.condition not in RANGE_CONDITIONS:
        problems["condition"] = "Choose a condition from the list."
    if not 0 <= data.age_min_days < data.age_max_days <= MAX_AGE_DAYS:
        problems["age_max_days"] = "The age band must end after it starts."
    v = {k: _decimal(getattr(data, k), problems, k) for k in _LIMITS}
    for k, value in v.items():
        setattr(data, k, value)
    lo, hi = v["low"], v["high"]
    if lo is not None and hi is not None and lo > hi:
        problems["high"] = "The upper limit must not be below the lower one."
    # Critical limits sit outside the normal range, absurd limits outside the critical ones.
    for inner, outer, key in (
        (lo, v["critical_low"], "critical_low"),
        (_first(v["critical_low"], lo), v["absurd_low"], "absurd_low"),
    ):
        if inner is not None and outer is not None and outer > inner:
            problems[key] = "Must be at or below the limit inside it."
    for inner, outer, key in (
        (hi, v["critical_high"], "critical_high"),
        (_first(v["critical_high"], hi), v["absurd_high"], "absurd_high"),
    ):
        if inner is not None and outer is not None and outer < inner:
            problems[key] = "Must be at or above the limit inside it."
    data.display_text = data.display_text.strip()
    data.source_citation = data.source_citation.strip()
    if problems:
        raise ValidationFailedError(problems)


def list_ranges(db: Session, principal: Principal, parameter_id: uuid.UUID) -> list[ReferenceRange]:
    _check(principal, "catalog.view")
    return list(
        db.scalars(
            select(ReferenceRange)
            .where(ReferenceRange.parameter_id == parameter_id)
            .order_by(ReferenceRange.sex.nulls_first(), ReferenceRange.age_min_days)
        )
    )


def get_range(db: Session, principal: Principal, range_id: uuid.UUID) -> ReferenceRange:
    _check(principal, "catalog.view")
    return _get(db, ReferenceRange, range_id)


def list_bands(db: Session, principal: Principal, range_id: uuid.UUID) -> list[ReferenceBand]:
    _check(principal, "catalog.view")
    return list(
        db.scalars(
            select(ReferenceBand)
            .where(ReferenceBand.range_id == range_id)
            .order_by(ReferenceBand.display_order)
        )
    )


def _overlapping_range(
    db: Session, parameter_id: uuid.UUID, data: RangeInput, range_id: uuid.UUID | None
) -> bool:
    """Two ranges in use for one sex and condition must not share an age, or a patient
    would match both."""
    query = select(ReferenceRange.id).where(
        ReferenceRange.parameter_id == parameter_id,
        ReferenceRange.is_active,
        ReferenceRange.sex.is_not_distinct_from(data.sex),
        ReferenceRange.condition.is_not_distinct_from(data.condition),
        ReferenceRange.age_min_days < data.age_max_days,
        ReferenceRange.age_max_days > data.age_min_days,
    )
    if range_id is not None:
        query = query.where(ReferenceRange.id != range_id)
    return db.scalar(query.limit(1)) is not None


def save_range(
    db: Session,
    principal: Principal,
    parameter_id: uuid.UUID,
    data: RangeInput,
    range_id: uuid.UUID | None = None,
    row_version: int = 0,
) -> ReferenceRange:
    """A new or changed range is unapproved until a signatory approves it (§1d)."""
    _check(principal, "catalog.edit")
    param = _get(db, TestParameter, parameter_id)
    if param.result_type not in ("numeric", "calculated"):
        raise ValidationFailedError({"low": "Only numeric and calculated parameters have ranges."})
    _validate_range(data)
    if data.is_active and _overlapping_range(db, parameter_id, data, range_id):
        message = "These ages overlap another range in use for the same sex and condition."
        raise ValidationFailedError({"age_min_days": message})
    if range_id is None:
        return _create(
            db,
            principal,
            ReferenceRange(parameter_id=parameter_id, **vars(data)),
            "range.create",
            {"parameter_id": str(parameter_id)},
        )
    rng = _get(db, ReferenceRange, range_id)
    if rng.parameter_id != parameter_id:
        raise NotFoundError()
    if _apply(db, principal, rng, vars(data), row_version, "range.update"):
        rng.approved_by = rng.approved_at = None
        db.flush()
    return rng


def set_bands(
    db: Session, principal: Principal, range_id: uuid.UUID, bands: list[BandInput]
) -> list[ReferenceBand]:
    """Replace a range's interpretation tiers. The range needs approval again."""
    _check(principal, "catalog.edit")
    rng = _get(db, ReferenceRange, range_id)
    problems: dict[str, str] = {}
    rows = []
    for i, b in enumerate(bands):
        low = _decimal(b.low, problems, f"band_{i}")
        high = _decimal(b.high, problems, f"band_{i}")
        if not b.label.strip() or b.severity not in BAND_SEVERITIES:
            problems[f"band_{i}"] = "Each tier needs a label and a severity."
        elif low is not None and high is not None and low > high:
            problems[f"band_{i}"] = "The upper limit must not be below the lower one."
        rows.append((low, high, b.label.strip(), b.severity))
    if problems:
        raise ValidationFailedError(problems)
    before = [
        {"label": b.label, "low": b.low, "high": b.high, "severity": b.severity}
        for b in list_bands(db, principal, range_id)
    ]
    for old in list_bands(db, principal, range_id):
        db.delete(old)
    db.flush()
    new = []
    for order, (low, high, label, severity) in enumerate(rows):
        band = ReferenceBand(
            range_id=range_id,
            low=low,
            high=high,
            label=label,
            severity=severity,
            display_order=order,
            created_by=principal.user_id,
        )
        db.add(band)
        new.append(band)
    rng.approved_by = rng.approved_at = None
    rng.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "range.bands",
        "reference_range",
        range_id,
        {
            "before": before,
            "after": [{"label": r[2], "low": r[0], "high": r[1], "severity": r[3]} for r in rows],
        },
        user_id=principal.user_id,
    )
    return new


def approve_range(
    db: Session, principal: Principal, range_id: uuid.UUID, row_version: int
) -> ReferenceRange:
    _check(principal, "range.approve")
    rng = _get(db, ReferenceRange, range_id)
    if rng.row_version != row_version:
        raise stale(db, rng)
    rng.approved_by = principal.user_id
    rng.approved_at = utcnow()
    rng.updated_by = principal.user_id
    db.flush()
    audit.record(db, "range.approve", "reference_range", rng.id, {}, user_id=principal.user_id)
    return rng


def unapproved_ranges(
    db: Session, principal: Principal, page: int = 1
) -> Page[tuple[Test, TestParameter, ReferenceRange]]:
    """Active ranges still waiting for a signatory, in catalog order."""
    _check(principal, "catalog.view")
    stmt = (
        select(Test, TestParameter, ReferenceRange)
        .join(TestParameter, TestParameter.test_id == Test.id)
        .join(ReferenceRange, ReferenceRange.parameter_id == TestParameter.id)
        .where(ReferenceRange.approved_at.is_(None), ReferenceRange.is_active)
        .order_by(
            Test.code, TestParameter.display_order, ReferenceRange.age_min_days, ReferenceRange.id
        )
    )
    return page_of(db, stmt, page)


def count_unapproved_ranges(db: Session, principal: Principal) -> int:
    _check(principal, "catalog.view")
    return (
        db.scalar(
            select(func.count())
            .select_from(ReferenceRange)
            .where(ReferenceRange.approved_at.is_(None), ReferenceRange.is_active)
        )
        or 0
    )


# Methods and comment presets


def list_methods(db: Session, principal: Principal, test_id: uuid.UUID) -> list[TestMethod]:
    _check(principal, "catalog.view")
    return list(
        db.scalars(
            select(TestMethod)
            .where(TestMethod.test_id == test_id)
            .order_by(TestMethod.is_default.desc(), TestMethod.name)
        )
    )


def save_method(
    db: Session,
    principal: Principal,
    test_id: uuid.UUID,
    name: str,
    is_default: bool = False,
    is_active: bool = True,
    method_id: uuid.UUID | None = None,
    row_version: int = 0,
) -> TestMethod:
    """Making a method the default takes the mark off the test's other methods."""
    _check(principal, "catalog.edit")
    _get(db, Test, test_id)
    name = name.strip()
    if not name:
        raise ValidationFailedError({"name": "Enter the method name."})
    clash = db.scalar(
        select(TestMethod.id).where(
            TestMethod.test_id == test_id, func.lower(TestMethod.name) == name.lower()
        )
    )
    if clash is not None and clash != method_id:
        raise ValidationFailedError({"name": f"This test already has the method {name}."})
    is_default = is_default and is_active
    if is_default:
        db.execute(
            update(TestMethod)
            .where(TestMethod.test_id == test_id, TestMethod.id != method_id)
            .values(is_default=False, row_version=TestMethod.row_version + 1)
            .execution_options(synchronize_session="fetch")
        )
    values = {"name": name, "is_default": is_default, "is_active": is_active}
    if method_id is None:
        return _create(
            db,
            principal,
            TestMethod(test_id=test_id, **values),
            "method.create",
            {"test_id": str(test_id), "name": name},
        )
    method = _get(db, TestMethod, method_id)
    if method.test_id != test_id:
        raise NotFoundError()
    _apply(db, principal, method, values, row_version, "method.update")
    return method


def preset_page(db: Session, principal: Principal, page: int) -> Page[CommentPreset]:
    _check(principal, "catalog.view")
    return page_of(db, select(CommentPreset).order_by(CommentPreset.label, CommentPreset.id), page)


def list_presets(
    db: Session, principal: Principal, test_id: uuid.UUID | None = None
) -> list[CommentPreset]:
    """All presets, or with `test_id` the ones for that test plus those for any test."""
    _check(principal, "catalog.view")
    q = select(CommentPreset).order_by(CommentPreset.label)
    if test_id is not None:
        q = q.where(or_(CommentPreset.test_id == test_id, CommentPreset.test_id.is_(None)))
    return list(db.scalars(q))


def save_preset(
    db: Session,
    principal: Principal,
    label: str,
    text: str,
    test_id: uuid.UUID | None = None,
    is_active: bool = True,
    preset_id: uuid.UUID | None = None,
    row_version: int = 0,
) -> CommentPreset:
    _check(principal, "catalog.edit")
    problems = {}
    if not label.strip():
        problems["label"] = "Enter a short label."
    if not text.strip():
        problems["text"] = "Enter the comment."
    if test_id is not None and db.get(Test, test_id) is None:
        problems["test_id"] = "Choose a test, or leave it for any test."
    if problems:
        raise ValidationFailedError(problems)
    values = {
        "label": label.strip(),
        "text": text.strip(),
        "test_id": test_id,
        "is_active": is_active,
    }
    if preset_id is None:
        return _create(db, principal, CommentPreset(**values), "preset.create", {"label": label})
    preset = _get(db, CommentPreset, preset_id)
    _apply(db, principal, preset, values, row_version, "preset.update")
    return preset


# Packages


def package_page(db: Session, principal: Principal, page: int) -> Page[Package]:
    _check(principal, "catalog.view")
    return page_of(db, select(Package).order_by(Package.code), page)


def get_package(db: Session, principal: Principal, package_id: uuid.UUID) -> Package:
    _check(principal, "catalog.view")
    return _get(db, Package, package_id)


def package_tests(db: Session, package_id: uuid.UUID) -> list[Test]:
    return list(
        db.scalars(
            select(Test)
            .join(PackageItem, PackageItem.test_id == Test.id)
            .where(PackageItem.package_id == package_id)
            .order_by(Test.code)
        )
    )


def save_package(
    db: Session,
    principal: Principal,
    code: str,
    name: str,
    test_ids: list[uuid.UUID],
    description: str = "",
    is_active: bool = True,
    package_id: uuid.UUID | None = None,
    row_version: int = 0,
) -> Package:
    _check(principal, "catalog.edit")
    code = code.strip().lower()
    problems: dict[str, str] = {}
    if not _CODE_RE.match(code):
        problems["code"] = "Use up to 20 small letters, digits or . _ + -, for example lft."
    elif _code_taken(db, code, package_id=package_id):
        problems["code"] = f"The code {code} is already used."
    if not name.strip():
        problems["name"] = "Enter the package name."
    wanted = set(test_ids)
    found = set(db.scalars(select(Test.id).where(Test.id.in_(wanted))))
    if len(wanted) < 2 or found != wanted:
        problems["test_ids"] = "Choose at least two tests."
    if problems:
        raise ValidationFailedError(problems)
    values = {
        "code": code,
        "name": name.strip(),
        "description": description.strip(),
        "is_active": is_active,
    }
    if package_id is None:
        pkg = _create(db, principal, Package(**values), "package.create", {"code": code})
    else:
        pkg = _get(db, Package, package_id)
        _apply(db, principal, pkg, values, row_version, "package.update")
    have = set(db.scalars(select(PackageItem.test_id).where(PackageItem.package_id == pkg.id)))
    if have != wanted:
        for tid in have - wanted:
            db.delete(db.get(PackageItem, (pkg.id, tid)))
        for tid in wanted - have:
            db.add(PackageItem(package_id=pkg.id, test_id=tid))
        db.flush()
        if package_id is not None:
            audit.record(
                db,
                "package.tests",
                "package",
                pkg.id,
                {"before": sorted(map(str, have)), "after": sorted(map(str, wanted))},
                user_id=principal.user_id,
            )
    return pkg


# Prices


def _item_exists(db: Session, item_type: str, item_id: uuid.UUID) -> bool:
    model = Test if item_type == "test" else Package
    return item_type in ITEM_TYPES and db.get(model, item_id) is not None


def set_price(
    db: Session,
    principal: Principal,
    item_type: str,
    item_id: uuid.UUID,
    amount: Decimal | str,
    branch_id: uuid.UUID | None = None,
    reason: str = "",
) -> Price:
    """Close the open price and start a new one now; old rows are never changed otherwise,
    so any past bill's price can be traced (EC-K02)."""
    _check(principal, "price.edit")
    problems: dict[str, str] = {}
    value = _decimal(amount, problems, "amount")
    if value is None and not problems:
        problems["amount"] = "Enter the price."
    elif value is not None and (value < 0 or value != value.quantize(Decimal("0.01"))):
        problems["amount"] = "A price of zero or more, with at most two decimals."
    if not _item_exists(db, item_type, item_id):
        problems["item_id"] = "Choose a test or package."
    if branch_id is not None and db.get(Branch, branch_id) is None:
        problems["branch_id"] = "Choose a branch."
    if problems or value is None:
        raise ValidationFailedError(problems)
    value = value.quantize(Decimal("0.01"))
    now = utcnow()
    open_row = db.scalar(
        select(Price)
        .where(
            Price.item_type == item_type,
            Price.item_id == item_id,
            Price.branch_id.is_(None) if branch_id is None else Price.branch_id == branch_id,
            Price.valid_to.is_(None),
        )
        .with_for_update()
    )
    before = None
    if open_row is not None:
        before = open_row.amount
        open_row.valid_to = now
        open_row.updated_by = principal.user_id
        db.flush()
    row = Price(
        item_type=item_type,
        item_id=item_id,
        branch_id=branch_id,
        amount=value,
        valid_from=now,
        reason=reason.strip(),
        created_by=principal.user_id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        "price.set",
        "price",
        row.id,
        {
            "item_type": item_type,
            "item_id": str(item_id),
            "branch_id": str(branch_id) if branch_id else None,
            "before": before,
            "after": value,
            "reason": row.reason,
        },
        user_id=principal.user_id,
        branch_id=branch_id,
    )
    return row


def end_branch_price(
    db: Session, principal: Principal, item_type: str, item_id: uuid.UUID, branch_id: uuid.UUID
) -> None:
    """Stop a branch override, so the branch charges the lab-wide price again."""
    _check(principal, "price.edit")
    row = db.scalar(
        select(Price).where(
            Price.item_type == item_type,
            Price.item_id == item_id,
            Price.branch_id == branch_id,
            Price.valid_to.is_(None),
        )
    )
    if row is None:
        raise NotFoundError()
    row.valid_to = utcnow()
    row.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "price.end_override",
        "price",
        row.id,
        {"item_type": item_type, "item_id": str(item_id), "before": row.amount, "after": None},
        user_id=principal.user_id,
        branch_id=branch_id,
    )


def price_row_at(
    db: Session,
    item_type: str,
    item_id: uuid.UUID,
    branch_id: uuid.UUID | None,
    at: datetime | None = None,
) -> Price | None:
    """The price row a branch charged (or charges now): its own override if one was in
    force, else the lab-wide row. A bill line keeps this row's id as its proof of rate."""
    at = at or utcnow()
    rows = db.scalars(
        select(Price).where(
            Price.item_type == item_type,
            Price.item_id == item_id,
            or_(Price.branch_id.is_(None), Price.branch_id == branch_id),
            Price.valid_from <= at,
            or_(Price.valid_to.is_(None), Price.valid_to > at),
        )
    ).all()
    by_scope = {row.branch_id: row for row in rows}
    if branch_id is not None and branch_id in by_scope:
        return by_scope[branch_id]
    return by_scope.get(None)


def price_at(
    db: Session,
    item_type: str,
    item_id: uuid.UUID,
    branch_id: uuid.UUID | None,
    at: datetime | None = None,
) -> Decimal | None:
    """The amount of `price_row_at`. None when the item had no price."""
    row = price_row_at(db, item_type, item_id, branch_id, at)
    return None if row is None else row.amount


def price_history(
    db: Session, principal: Principal, item_type: str, item_id: uuid.UUID
) -> list[Price]:
    _check(principal, "catalog.view")
    return list(
        db.scalars(
            select(Price)
            .where(Price.item_type == item_type, Price.item_id == item_id)
            .order_by(Price.branch_id.nulls_first(), Price.valid_from.desc())
        )
    )


def get_item(db: Session, principal: Principal, item_type: str, item_id: uuid.UUID) -> Any:
    """The test or package a price belongs to."""
    _check(principal, "catalog.view")
    if item_type not in ITEM_TYPES:
        raise NotFoundError()
    return _get(db, Test if item_type == "test" else Package, item_id)


@dataclass
class PriceRow:
    item_type: str
    item_id: uuid.UUID
    code: str
    name: str
    is_active: bool
    lab_price: Decimal | None
    branch_price: Decimal | None


def _open_prices(
    db: Session, item_ids: list[uuid.UUID], branch_id: uuid.UUID | None
) -> dict[tuple[uuid.UUID, uuid.UUID | None], Decimal]:
    rows = db.execute(
        select(Price.item_id, Price.branch_id, Price.amount).where(
            Price.valid_to.is_(None),
            Price.item_id.in_(item_ids),
            or_(Price.branch_id.is_(None), Price.branch_id == branch_id),
        )
    ).all()
    return {(item_id, branch): amount for item_id, branch, amount in rows}


def lab_prices(db: Session, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Today's lab-wide price of each item that has one."""
    return {item_id: amount for (item_id, _), amount in _open_prices(db, item_ids, None).items()}


def price_page(
    db: Session, principal: Principal, page: int, branch_id: uuid.UUID | None = None
) -> Page[PriceRow]:
    """Tests, then packages, each with its lab-wide price today and, given a branch, that
    branch's own price where it has one."""
    _check(principal, "catalog.view")
    items = union_all(
        select(literal("test").label("kind"), Test.id, Test.code, Test.name, Test.is_active),
        select(
            literal("package").label("kind"),
            Package.id,
            Package.code,
            Package.name,
            Package.is_active,
        ),
    ).subquery()
    found = page_of(db, select(items).order_by(items.c.kind.desc(), items.c.code), page)
    current = _open_prices(db, [row[1] for row in found.items], branch_id)
    rows = [
        PriceRow(
            kind,
            item_id,
            code,
            name,
            is_active,
            current.get((item_id, None)),
            current.get((item_id, branch_id)) if branch_id else None,
        )
        for kind, item_id, code, name, is_active in found.items
    ]
    return replace(found, items=rows)


# Search


@dataclass(frozen=True)
class SearchHit:
    item_type: str
    item_id: uuid.UUID
    code: str
    name: str
    price: Decimal | None


def search(
    db: Session,
    principal: Principal,
    text: str,
    branch_id: uuid.UUID | None = None,
    limit: int = 10,
) -> list[SearchHit]:
    """Code first: an exact code or alias, then codes starting with the text, then names
    that look like it (trigram), so `hb` + Enter always adds haemoglobin (§1d)."""
    _check(principal, "catalog.view")
    q = text.strip().lower()
    if not q:
        return []
    like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    ranked: dict[tuple[str, uuid.UUID], tuple[int, float, str, str]] = {}

    def add(kind: str, rows: Any, rank: int) -> None:
        for item_id, code, name, score in rows:
            key = (kind, item_id)
            if key not in ranked or ranked[key][:2] > (rank, -score):
                ranked[key] = (rank, -score, code, name)

    for kind, model in (("test", Test), ("package", Package)):
        exact = model.code == q
        prefix = model.code.like(like)
        if model is Test:
            exact = or_(exact, list_contains(Test.aliases, q))
            # Any alias starting with the text: " hgb haemo" matches "% hae%".
            aliases = func.concat(" ", list_as_text(Test.aliases))
            prefix = or_(prefix, aliases.like(f"% {like}"))
        # Trigram matching ignores case, and the trigram index serves it and ILIKE alike.
        sim = similarity(model.name, q)
        base = select(model.id, model.code, model.name, sim).where(model.is_active)
        add(kind, db.execute(base.where(exact)), 0)
        add(kind, db.execute(base.where(prefix).limit(limit)), 1)
        add(
            kind,
            db.execute(
                base.where(or_(similar(model.name, q), model.name.ilike(f"%{like[:-1]}%")))
                .order_by(sim.desc())
                .limit(limit)
            ),
            2,
        )
    best = sorted(ranked.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[1][2]))[:limit]
    return [
        SearchHit(kind, item_id, code, name, price_at(db, kind, item_id, branch_id))
        for (kind, item_id), (_, _, code, name) in best
    ]
