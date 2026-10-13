"""The lab bench: where each test is done, and samples arriving at the lab.

Lab screens get the patient's name, age and sex and nothing else about them; the phone and
address stay at the front desk.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.catalog.models import Test
from labra.core import audit, lab_settings
from labra.core.consent import current_notice
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.ids import lab_today, utcnow
from labra.core.models import Consent
from labra.extlabs import service as extlabs
from labra.org.models import Branch
from labra.org.service import stale
from labra.patients.age import age_text
from labra.patients.models import Patient
from labra.results.models import OrderTestEvent
from labra.results.worklist import ROUTABLE, can_route, has_sharing_consent
from labra.visits.models import OrderTest, Sample, Visit
from labra.visits.service import main_lab_id, status_once_collected

MAX_REASON = 200


def _check(principal: Principal, permission: str, branch_id: uuid.UUID | None = None) -> None:
    if not principal.can(permission, branch_id):
        raise PermissionDeniedError()


def _event(db: Session, ordered: OrderTest, event: str, by: uuid.UUID, at: datetime, note: str):
    db.add(OrderTestEvent(order_test_id=ordered.id, event=event, at=at, by=by, note=note))


# Routing


def route_test(
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    row_version: int,
    *,
    branch_id: uuid.UUID | None = None,
    external_lab_id: uuid.UUID | None = None,
    reason: str = "",
    now: datetime | None = None,
) -> OrderTest:
    """Say who does a test. With `external_lab_id` it goes to that lab at the lab's rate of
    the moment, and is due when the lab's turnaround says. Without, it is done in-house at
    `branch_id`: the main lab, or the branch that took the sample."""
    ordered = db.scalar(select(OrderTest).where(OrderTest.id == order_test_id).with_for_update())
    if ordered is None:
        raise NotFoundError()
    visit = db.get_one(Visit, ordered.visit_id)
    if not can_route(principal, ordered, visit):
        raise PermissionDeniedError()
    if ordered.row_version != row_version:
        raise stale(db, ordered)
    if ordered.status not in ROUTABLE:
        raise ConflictError(
            "This test can't be moved any more: it was sent out, has a result or was cancelled."
        )
    reason = reason.strip()
    if len(reason) > MAX_REASON:
        raise ValidationFailedError({"reason": f"Use at most {MAX_REASON} characters."})
    at = now or utcnow()
    test = db.get_one(Test, ordered.test_id)

    if external_lab_id is not None:
        quote = next(
            (
                q
                for q in extlabs.quotes_for(db, principal, ordered.test_id, at)
                if q.lab.id == external_lab_id
            ),
            None,
        )
        if quote is None:
            raise ValidationFailedError(
                {
                    "external_lab_id": "This lab has no rate for the test. Add one under"
                    " External labs first."
                }
            )
        ordered.route = "external"
        ordered.external_lab_id = quote.lab.id
        ordered.external_cost = quote.rate.cost
        ordered.due_at = at + timedelta(hours=quote.rate.tat_hours)
        note = f"To {quote.lab.name}"
    else:
        main = main_lab_id(db)
        target = branch_id or main or visit.branch_id
        if target not in {main, visit.branch_id}:
            raise ValidationFailedError(
                {
                    "branch_id": "A test is done at the main lab or at the branch that took"
                    " the sample."
                }
            )
        fallback = lab_settings.get_value(db, "visit.default_tat_hours", visit.branch_id)
        ordered.route = "in_house"
        ordered.external_lab_id = None
        ordered.external_cost = None
        ordered.external_accession_no = ""
        ordered.due_at = visit.visited_at + timedelta(hours=test.default_tat_hours or fallback)
        if target != ordered.perform_branch_id:
            ordered.perform_branch_id = target
            if ordered.status != "ordered":
                ordered.status = status_once_collected(db, visit.branch_id, target)
        note = f"In-house at {db.get_one(Branch, target).code}"
    ordered.route_reason = reason
    ordered.routed_by = principal.user_id
    ordered.routed_at = at
    ordered.updated_by = principal.user_id
    db.flush()
    _event(db, ordered, "routed", principal.user_id, at, f"{note}. {reason}" if reason else note)
    audit.record(
        db,
        "test.route",
        "order_test",
        ordered.id,
        {
            "visit_id": str(visit.id),
            "test": test.code,
            "route": ordered.route,
            "perform_branch_id": str(ordered.perform_branch_id),
            "external_lab_id": str(ordered.external_lab_id) if ordered.external_lab_id else None,
            "external_cost": str(ordered.external_cost) if ordered.external_cost else None,
            "sharing_consent": has_sharing_consent(db, visit.patient_id),
        },
        user_id=principal.user_id,
        branch_id=visit.branch_id,
    )
    return ordered


def record_sharing_consent(db: Session, principal: Principal, visit_id: uuid.UUID) -> bool:
    """Record that the visit's patient agreed to their details going to an outside lab.
    Returns False when that was already on file."""
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise NotFoundError()
    if not principal.can("test.route", visit.branch_id) and not principal.can(
        "test.route", principal.branch_id
    ):
        raise PermissionDeniedError()
    if has_sharing_consent(db, visit.patient_id):
        return False
    db.add(
        Consent(
            subject_type="patient",
            subject_id=visit.patient_id,
            purpose="referral_lab_sharing",
            method="counter",
            recorded_by=principal.user_id,
            notice_id=current_notice(db).id,
        )
    )
    db.flush()
    audit.record(
        db,
        "consent.record",
        "patient",
        visit.patient_id,
        {"purpose": "referral_lab_sharing", "visit_id": str(visit.id)},
        user_id=principal.user_id,
        branch_id=visit.branch_id,
    )
    return True


# Receiving samples


@dataclass(frozen=True)
class LabSample:
    """What the lab sees of a sample: no phone, no address."""

    sample_no: str
    container: str
    patient_name: str
    age: str
    sex: str
    from_branch: str
    tests: list[str]
    received_at: datetime | None


def _here(principal: Principal) -> uuid.UUID:
    if principal.branch_id is None:
        raise PermissionDeniedError()
    _check(principal, "sample.receive", principal.branch_id)
    return principal.branch_id


def _tests_here(db: Session, sample_id: uuid.UUID, here: uuid.UUID) -> list[OrderTest]:
    return list(
        db.scalars(
            select(OrderTest).where(
                OrderTest.sample_id == sample_id,
                OrderTest.perform_branch_id == here,
                OrderTest.status != "cancelled",
            )
        )
    )


def lab_sample(db: Session, principal: Principal, sample_no: str) -> LabSample | None:
    """A sample whose tests the user's branch does, by its number."""
    here = _here(principal)
    row = db.execute(
        select(Sample, Patient.full_name, Patient.dob, Patient.sex, Branch.code)
        .join(Visit, Visit.id == Sample.visit_id)
        .join(Patient, Patient.id == Visit.patient_id)
        .join(Branch, Branch.id == Visit.branch_id)
        .where(Sample.sample_no == sample_no.strip().upper())
    ).first()
    if row is None:
        return None
    sample, name, dob, sex, branch_code = row
    codes = list(
        db.scalars(
            select(Test.code)
            .join(OrderTest, OrderTest.test_id == Test.id)
            .where(
                OrderTest.sample_id == sample.id,
                OrderTest.perform_branch_id == here,
                OrderTest.status != "cancelled",
            )
            .order_by(Test.code)
        )
    )
    if not codes:
        return None
    return LabSample(
        sample_no=sample.sample_no,
        container=sample.container,
        patient_name=name,
        age=age_text(dob, lab_today()),
        sex=sex,
        from_branch=branch_code,
        tests=codes,
        received_at=sample.received_at,
    )


def receive_sample(
    db: Session, principal: Principal, sample_no: str, now: datetime | None = None
) -> Sample:
    """Scan a sample in at the user's branch: its tests done here are now in the lab."""
    here = _here(principal)
    number = sample_no.strip().upper()
    if not number:
        raise ValidationFailedError({"sample_no": "Scan or type the sample number."})
    sample = db.scalar(select(Sample).where(Sample.sample_no == number).with_for_update())
    if sample is None:
        raise ValidationFailedError({"sample_no": f"No sample has the number {number}."})
    if sample.status == "cancelled":
        raise ValidationFailedError(
            {"sample_no": f"Sample {number} was cancelled with its bill. Don't test it."}
        )
    if sample.status == "pending":
        raise ValidationFailedError(
            {
                "sample_no": f"Sample {number} isn't marked as collected yet. Record the"
                " collection first."
            }
        )
    if sample.status not in ("collected", "received"):
        raise ValidationFailedError({"sample_no": f"Sample {number} can't be received."})
    tests = _tests_here(db, sample.id, here)
    if not tests:
        raise ValidationFailedError(
            {"sample_no": f"Sample {number} has no test that is done at this branch."}
        )
    waiting = [t for t in tests if t.status == "collected"]
    if not waiting:
        raise ValidationFailedError({"sample_no": f"Sample {number} is already in the lab."})
    at = now or utcnow()
    for ordered in waiting:
        ordered.status = "in_lab"
        ordered.updated_by = principal.user_id
        _event(db, ordered, "received", principal.user_id, at, "")
    sample.status = "received"
    sample.received_at = at
    sample.received_by = principal.user_id
    sample.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "sample.receive",
        "sample",
        sample.id,
        {
            "sample_no": sample.sample_no,
            "visit_id": str(sample.visit_id),
            "tests": len(waiting),
        },
        user_id=principal.user_id,
        branch_id=here,
    )
    return sample
