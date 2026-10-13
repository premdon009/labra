"""Entering results: one value at a time, each read against its range as it is saved.

The range's numbers and text are copied into the result, so a later change to the range
never alters a value already entered. Calculated rows are worked out here, on the server,
after every save. A save writes no audit row: the audit chain takes one lock for the whole
lab, and a technician saves hundreds of cells a day. The confirm of an absurd value is the
exception.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.catalog import formula
from labra.catalog.models import ReferenceRange, TestParameter
from labra.core import audit
from labra.core.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from labra.core.ids import utcnow
from labra.org.service import stale
from labra.results.flags import compute_flag, is_absurd
from labra.results.models import OrderTestEvent, Result, ResultRevision
from labra.results.worklist import (
    EDITABLE,
    ROUTABLE,
    Sheet,
    bands_of,
    has_document,
    load_sheet,
    plain,
    range_text,
)

NOT_YET = {
    "ordered": "The sample for this test hasn't been collected yet.",
    "collected": "The sample for this test hasn't been received in the lab yet.",
    "sent_out": "This test is with an outside lab.",
    "verified": "This test is verified. A signatory must reopen it before a value changes.",
    "released": "This test's report is released. A signatory must reopen it first.",
    "cancelled": "This test was cancelled with its bill.",
}
MAX_TEXT = 200
# What fits the column: ten digits before the point.
_TOO_BIG = Decimal(10) ** 10
_PLAIN_NUMBER = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)")


class AbsurdValueError(ValidationFailedError):
    """The value is one no patient has, most likely a slip of the finger. Nothing was saved;
    the same value sent again with the confirm is."""

    def __init__(self, value: Decimal) -> None:
        self.value = value
        super().__init__(
            {"value": f"Check value: {plain(value)} is outside what a patient can have."}
        )


@dataclass(frozen=True)
class Saved:
    result: Result
    # Every calculated row of the test that has a result row, worked out afresh.
    calculated: list[Result]


def _number(parameter: TestParameter, raw: str) -> Decimal:
    digits = raw.replace(",", "")
    # Plain digits only: Decimal would also take 1e3, NaN and Infinity.
    if not _PLAIN_NUMBER.fullmatch(digits):
        raise ValidationFailedError({"value": "Enter a number."})
    value = Decimal(digits)
    if abs(value) >= _TOO_BIG:
        raise ValidationFailedError({"value": "Enter a number."})
    places = parameter.decimals
    # 45.0 is a whole number; 45.5 isn't.
    if value != value.quantize(Decimal(1).scaleb(-places)):
        raise ValidationFailedError(
            {
                "value": "Enter a whole number."
                if places == 0
                else f"Use at most {places} decimal place{'s' if places > 1 else ''}."
            }
        )
    return value


def _option(parameter: TestParameter, raw: str) -> str:
    choices = [str(o.get("value", "")) for o in parameter.options]
    for choice in choices:
        if choice == raw:
            return choice
    folded = [c for c in choices if c.casefold() == raw.casefold()]
    if len(folded) == 1:
        return folded[0]
    raise ValidationFailedError({"value": "Choose one of the listed values."})


def _text(parameter: TestParameter, raw: str) -> str:
    if len(raw) > MAX_TEXT:
        raise ValidationFailedError({"value": f"Use at most {MAX_TEXT} characters."})
    if parameter.text_pattern and not re.fullmatch(parameter.text_pattern, raw):
        raise ValidationFailedError({"value": "This doesn't have the form the test expects."})
    return raw


def _write(
    db: Session,
    sheet: Sheet,
    parameter: TestParameter,
    principal: Principal,
    at: datetime,
    *,
    number: Decimal | None = None,
    text: str = "",
    source: str = "manual",
    not_calculable: bool = False,
    absurd_confirmed: bool = False,
) -> Result:
    """Create or change the parameter's result, copying in the range it is read against."""
    rng: ReferenceRange | None = None
    if number is not None:
        rng = sheet.range_for(parameter.id)
    read = compute_flag(
        number if number is not None else (text or None),
        rng,
        bands_of(db, rng),
        parameter.options if parameter.result_type == "option" else (),
    )
    result = sheet.results.get(parameter.id)
    before = (result.value_num, result.value_text, result.flag) if result is not None else None
    if result is None:
        result = Result(
            order_test_id=sheet.ordered.id,
            parameter_id=parameter.id,
            created_by=principal.user_id,
        )
        db.add(result)
        sheet.results[parameter.id] = result
    result.value_num = number
    result.value_text = text
    result.unit = parameter.unit_ucum
    result.flag = read.flag
    result.band_label = read.band_label
    result.band_severity = read.band_severity
    result.ref_range_text = range_text(rng.low, rng.high, rng.display_text) if rng else ""
    result.ref_low = rng.low if rng else None
    result.ref_high = rng.high if rng else None
    result.crit_low = rng.critical_low if rng else None
    result.crit_high = rng.critical_high if rng else None
    result.source = source
    result.not_calculable = not_calculable
    result.absurd_confirmed = absurd_confirmed
    if db.is_modified(result):
        result.entered_by = principal.user_id
        result.entered_at = at
        result.updated_by = principal.user_id
        sheet.changed = True
        if before is not None and sheet.reopen_reason and before[:2] != (number, text):
            db.add(
                ResultRevision(
                    result_id=result.id,
                    old_value_num=before[0],
                    old_value_text=before[1],
                    old_flag=before[2],
                    reason=sheet.reopen_reason,
                    changed_by=principal.user_id,
                    changed_at=at,
                )
            )
    return result


def _calculate(parameter: TestParameter, values: dict[str, Decimal | None], broken: set[str]):
    """A calculated row's value and whether it is "not calculable". Both empty while an
    input is still missing. A row built on one in `broken`, the rows that can't be
    calculated, can't be calculated either."""
    try:
        _, needs = formula.parse(parameter.formula)
        _, rule_needs = (
            formula.parse(parameter.formula_valid_if, condition=True)
            if parameter.formula_valid_if.strip()
            else (None, set())
        )
    except formula.FormulaError:
        return None, True
    if broken & (needs | rule_needs):
        return None, True
    if any(values.get(code) is None for code in needs | rule_needs):
        return None, False
    try:
        if not formula.holds(parameter.formula_valid_if, values):
            return None, True
        value = formula.evaluate(parameter.formula, values)
    except formula.NotCalculable:
        return None, True
    if not value.is_finite() or abs(value) >= _TOO_BIG:
        return None, True
    return value.quantize(Decimal(1).scaleb(-parameter.decimals), ROUND_HALF_UP), False


def recalculate(db: Session, sheet: Sheet, principal: Principal, at: datetime) -> list[Result]:
    """Work out every calculated row of the test from the values it has now."""
    calculated = [p for p in sheet.parameters if p.result_type == "calculated"]
    if not calculated:
        return []
    values: dict[str, Decimal | None] = {}
    for p in sheet.parameters:
        if p.result_type == "numeric":
            result = sheet.results.get(p.id)
            values[p.code] = result.value_num if result is not None else None
    outcome: dict[uuid.UUID, tuple[Decimal | None, bool]] = {}
    # A formula may build on another calculated row, so go round until nothing new appears.
    broken: set[str] = set()
    for _ in calculated:
        before = (dict(values), set(broken))
        for p in calculated:
            outcome[p.id] = _calculate(p, values, broken)
            values[p.code] = outcome[p.id][0]
            if outcome[p.id][1]:
                broken.add(p.code)
        if (values, broken) == before:
            break
    written = []
    for p in calculated:
        number, not_calculable = outcome[p.id]
        if number is None and not not_calculable and p.id not in sheet.results:
            continue
        written.append(
            _write(
                db,
                sheet,
                p,
                principal,
                at,
                number=number,
                source="calculated",
                not_calculable=not_calculable,
            )
        )
    return written


def reopen_reason(db: Session, order_test_id: uuid.UUID) -> str:
    """Why the test was last reopened after verification; empty if it never was."""
    return (
        db.scalar(
            select(OrderTestEvent.note)
            .where(
                OrderTestEvent.order_test_id == order_test_id, OrderTestEvent.event == "reopened"
            )
            .order_by(OrderTestEvent.at.desc(), OrderTestEvent.id.desc())
            .limit(1)
        )
        or ""
    )


def save_value(
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    parameter_id: uuid.UUID,
    raw: str,
    row_version: int = 0,
    *,
    confirm_absurd: bool = False,
    now: datetime | None = None,
) -> Saved:
    """Save one typed value as a draft and work out the rows calculated from it. An empty
    value clears the result. `row_version` is the result's version the screen had, 0 for a
    cell that was empty."""
    sheet = load_sheet(db, order_test_id, lock=True)
    ordered = sheet.ordered
    if not principal.can("result.enter", ordered.perform_branch_id):
        raise PermissionDeniedError()
    outside = ordered.route == "external"
    waits_for_pdf = outside and ordered.status in (*ROUTABLE, *EDITABLE)
    if waits_for_pdf and not has_document(db, ordered.id):
        raise ConflictError(
            "This test goes to an outside lab. Attach the lab's PDF first, or move the test"
            " in-house."
        )
    if ordered.status not in EDITABLE:
        raise ConflictError(NOT_YET.get(ordered.status, "This test can't take results now."))
    parameter = next((p for p in sheet.parameters if p.id == parameter_id), None)
    if parameter is None:
        raise ValidationFailedError({"value": "This test doesn't have that row any more."})
    if parameter.result_type == "calculated":
        raise ValidationFailedError({"value": "This row is calculated; it can't be typed."})
    existing = sheet.results.get(parameter.id)
    if existing is not None and existing.row_version != row_version:
        raise stale(db, existing)
    if existing is None and row_version != 0:
        raise ConflictError()

    raw = raw.strip()
    number: Decimal | None = None
    text = ""
    confirmed = False
    if raw:
        if parameter.result_type == "numeric":
            number = _number(parameter, raw)
            if is_absurd(number, sheet.range_for(parameter.id, approved_only=False)):
                if not confirm_absurd:
                    raise AbsurdValueError(number)
                confirmed = True
        elif parameter.result_type == "option":
            text = _option(parameter, raw)
        else:
            text = _text(parameter, raw)
    at = now or utcnow()
    sheet.reopen_reason = reopen_reason(db, ordered.id)
    result = _write(
        db,
        sheet,
        parameter,
        principal,
        at,
        number=number,
        text=text,
        source="external_pdf" if outside else "manual",
        absurd_confirmed=confirmed,
    )
    calculated = recalculate(db, sheet, principal, at)
    if sheet.changed and ordered.status == "resulted":
        # The signatory verifies what was submitted; a later change is submitted again.
        ordered.status = "in_lab"
        ordered.updated_by = principal.user_id
    db.flush()
    if confirmed:
        audit.record(
            db,
            "result.absurd_confirm",
            "result",
            result.id,
            {
                "order_test_id": str(ordered.id),
                "visit_id": str(ordered.visit_id),
                "parameter": parameter.code,
                "value": plain(number) if number is not None else "",
            },
            user_id=principal.user_id,
            branch_id=ordered.perform_branch_id,
        )
    return Saved(result, calculated)
