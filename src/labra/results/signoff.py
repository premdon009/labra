"""Standing behind results: sending a test for verification, the critical-value log, the
signatory's sign-off, and reopening a verified test.

A critical value is saved like any other, but the test can go no further until someone has
been told and that is on record: who, when and how (NABL).
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.core import audit, outbox
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.ids import utcnow
from labra.org.service import stale
from labra.results.models import CriticalNotification, OrderTestEvent, Result, Verification
from labra.results.worklist import (
    CRITICAL,
    EDITABLE,
    SIGNED_OFF,
    Sheet,
    has_document,
    load_sheet,
    reported,
    told_about,
)

MODES = ("phone", "in_person", "message", "email")
MAX_NAME = 120
MAX_REASON = 300
# A call can be logged a little before the server's clock agrees it has happened.
CLOCK_SLACK = timedelta(minutes=5)
NOT_INFORMED = (
    "A critical value has nobody on record as informed. Record who was told before going on."
)


def _locked(db: Session, order_test_id: uuid.UUID, row_version: int) -> Sheet:
    sheet = load_sheet(db, order_test_id, lock=True)
    if sheet.ordered.row_version != row_version:
        raise stale(db, sheet.ordered)
    return sheet


def _event(db: Session, sheet: Sheet, event: str, by: uuid.UUID, at: datetime, note: str = ""):
    db.add(OrderTestEvent(order_test_id=sheet.ordered.id, event=event, at=at, by=by, note=note))


def _audit(db: Session, sheet: Sheet, action: str, principal: Principal, **detail: object):
    audit.record(
        db,
        action,
        "order_test",
        sheet.ordered.id,
        {"visit_id": str(sheet.ordered.visit_id), "test": sheet.test.code, **detail},
        user_id=principal.user_id,
        branch_id=sheet.ordered.perform_branch_id,
    )


def not_informed(db: Session, sheet: Sheet) -> list[Result]:
    """The test's critical results that nobody is on record as having been told about."""
    told = told_about(db, sheet)
    active = {p.id for p in sheet.parameters}
    return [
        r
        for r in sheet.results.values()
        if r.flag in CRITICAL and r.parameter_id in active and r.id not in told
    ]


def _has_values(sheet: Sheet) -> bool:
    return any(
        r.value_num is not None or r.value_text or r.not_calculable for r in sheet.results.values()
    )


# The critical-value log


def log_critical(
    db: Session,
    principal: Principal,
    result_id: uuid.UUID,
    *,
    informed_to: str,
    mode: str,
    phone: str = "",
    informed_at: datetime | None = None,
    now: datetime | None = None,
) -> CriticalNotification:
    """Put on record who was told about a critical value, when and how."""
    result = db.get(Result, result_id)
    if result is None:
        raise NotFoundError()
    sheet = load_sheet(db, result.order_test_id, lock=True)
    result = sheet.results.get(result.parameter_id, result)
    if not principal.can("result.enter", sheet.ordered.perform_branch_id):
        raise PermissionDeniedError()
    if sheet.ordered.status not in EDITABLE:
        raise ConflictError("This test can't take a critical-value entry now.")
    parameter = next((p for p in sheet.parameters if p.id == result.parameter_id), None)
    if parameter is None or result.flag not in CRITICAL:
        raise ConflictError("This value isn't critical any more. Reload the page.")
    at = now or utcnow()
    informed_to, phone = informed_to.strip(), "".join(phone.split())
    problems: dict[str, str] = {}
    if not informed_to:
        problems["informed_to"] = "Enter who was informed, such as the doctor's name."
    elif len(informed_to) > MAX_NAME:
        problems["informed_to"] = f"Use at most {MAX_NAME} characters."
    if mode not in MODES:
        problems["mode"] = "Pick how they were informed."
    if phone and not (phone.lstrip("+").isdigit() and 7 <= len(phone.lstrip("+")) <= 14):
        problems["phone"] = "Enter the number in digits, or leave it empty."
    when = informed_at or at
    if when > at + CLOCK_SLACK:
        problems["informed_at"] = "The time can't be in the future."
    elif when < sheet.visit.visited_at:
        problems["informed_at"] = "The time can't be before the visit."
    if problems:
        raise ValidationFailedError(problems)
    note = CriticalNotification(
        result_id=result.id,
        reported_value=reported(result, parameter.decimals),
        reported_flag=result.flag or "",
        informed_to=informed_to,
        phone=phone,
        mode=mode,
        informed_at=when,
        recorded_by=principal.user_id,
        recorded_at=at,
    )
    db.add(note)
    db.flush()
    # The name and number stay in the log itself; the audit trail keeps what was done.
    audit.record(
        db,
        "result.critical_inform",
        "result",
        result.id,
        {
            "order_test_id": str(sheet.ordered.id),
            "visit_id": str(sheet.ordered.visit_id),
            "parameter": parameter.code,
            "value": note.reported_value,
            "flag": note.reported_flag,
            "mode": mode,
        },
        user_id=principal.user_id,
        branch_id=sheet.ordered.perform_branch_id,
    )
    return note


# Submit, verify, reopen


def submit(
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    row_version: int,
    now: datetime | None = None,
) -> None:
    """Send a test's results to the signatory. Rows may still be empty; a critical value
    with nobody informed holds the test back."""
    sheet = _locked(db, order_test_id, row_version)
    ordered = sheet.ordered
    if not principal.can("result.enter", ordered.perform_branch_id):
        raise PermissionDeniedError()
    if ordered.status != "in_lab":
        raise ConflictError("This test isn't waiting for results. Reload the page.")
    if ordered.route == "external":
        # An outside lab's PDF is the result; typing its values in is optional.
        if not has_document(db, ordered.id):
            raise ValidationFailedError({"test": "Attach the outside lab's PDF first."})
    elif not _has_values(sheet):
        raise ValidationFailedError({"test": "Enter at least one value first."})
    if not_informed(db, sheet):
        raise ValidationFailedError({"test": NOT_INFORMED})
    at = now or utcnow()
    ordered.status = "resulted"
    ordered.updated_by = principal.user_id
    db.flush()
    _event(db, sheet, "resulted", principal.user_id, at)


def verify(
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    row_version: int,
    note: str = "",
    now: datetime | None = None,
) -> Verification:
    """A signatory's sign-off. From here the values can't change unless the test is
    reopened."""
    sheet = _locked(db, order_test_id, row_version)
    ordered = sheet.ordered
    if not principal.can("result.verify", ordered.perform_branch_id):
        raise PermissionDeniedError()
    if ordered.status != "resulted":
        raise ConflictError("This test isn't waiting for verification. Reload the page.")
    note = note.strip()
    if len(note) > MAX_REASON:
        raise ValidationFailedError({"test": f"Use at most {MAX_REASON} characters."})
    if not_informed(db, sheet):
        raise ValidationFailedError({"test": NOT_INFORMED})
    at = now or utcnow()
    signed = Verification(
        order_test_id=ordered.id, verified_by=principal.user_id, verified_at=at, note=note
    )
    db.add(signed)
    ordered.status = "verified"
    ordered.updated_by = principal.user_id
    db.flush()
    _event(db, sheet, "verified", principal.user_id, at, note)
    _audit(db, sheet, "result.verify", principal, results=len(sheet.results))
    # IDs only: no name, no value. Verified again after a reopen, it is sent again.
    outbox.emit(
        db,
        "test.performed",
        {
            "schema_version": 1,
            "entity": "order_test",
            "entity_id": str(ordered.id),
            "visit_id": str(ordered.visit_id),
            "test_id": str(ordered.test_id),
            "branch_id": str(sheet.visit.branch_id),
            "perform_branch_id": str(ordered.perform_branch_id),
            "route": ordered.route,
            "external_lab_id": str(ordered.external_lab_id) if ordered.external_lab_id else None,
            "verification_id": str(signed.id),
        },
    )
    return signed


def reopen(
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    row_version: int,
    reason: str,
    now: datetime | None = None,
) -> None:
    """Take back a sign-off so a value can be corrected. The test waits for verification
    again, and every value changed from here on is kept with this reason. A released test
    can be reopened too; its next release is marked amended, with this reason."""
    sheet = _locked(db, order_test_id, row_version)
    ordered = sheet.ordered
    if not principal.can("result.verify", ordered.perform_branch_id):
        raise PermissionDeniedError()
    if ordered.status not in SIGNED_OFF:
        raise ConflictError("Only a verified or released test can be reopened. Reload the page.")
    reason = reason.strip()
    if not reason:
        raise ValidationFailedError({"test": "Say why the test is being reopened."})
    if len(reason) > MAX_REASON:
        raise ValidationFailedError({"test": f"Use at most {MAX_REASON} characters."})
    at = now or utcnow()
    ordered.status = "resulted"
    ordered.updated_by = principal.user_id
    db.flush()
    _event(db, sheet, "reopened", principal.user_id, at, reason)
    _audit(db, sheet, "result.reopen", principal, reason=reason)
