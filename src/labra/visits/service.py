"""Visits: price what was ordered, then save patient, visit, samples and bill together.

One save is one transaction. Locks are always taken in the same order: the form's client
reference, then the number series (patient, visit, sample, bill, receipt), and last the
audit chain.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.billing import service as billing
from labra.billing.models import Bill, BillLine, Payment, Refund
from labra.catalog import service as catalog
from labra.catalog.models import Package, SpecimenType, Test
from labra.core import audit, lab_settings
from labra.core.consent import current_notice
from labra.core.currency import load_format
from labra.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from labra.core.ids import lab_today, utcnow
from labra.core.models import Consent, ConsentNotice
from labra.core.money import ZERO, BillTotals, Discount, Line, bill_totals
from labra.core.numbering import next_number
from labra.org.models import Branch
from labra.patients import service as patients
from labra.patients.models import Patient, Referrer
from labra.visits.labels import group_by_specimen
from labra.visits.models import COLLECTION_MODES, OrderItem, OrderTest, Sample, Visit

CONSENT_PURPOSES = ("testing", "referral_lab_sharing")
DISCOUNT_KINDS = ("amount", "pct")
MAX_LINES = 60


def _check(principal: Principal, permission: str, branch_id: uuid.UUID | None = None) -> None:
    if not principal.can(permission, branch_id):
        raise PermissionDeniedError()


def _branch_of(principal: Principal) -> uuid.UUID:
    if principal.branch_id is None:
        raise PermissionDeniedError()
    _check(principal, "visit.create", principal.branch_id)
    return principal.branch_id


# The order


@dataclass(frozen=True)
class ChargeInput:
    """An extra charge as typed: home collection, a courier fee."""

    description: str
    amount: str
    reason: str


@dataclass
class VisitInput:
    """The one-screen visit form. Either `patient_id` (someone already registered) or
    `patient` (a new registration)."""

    client_ref: uuid.UUID
    patient_id: uuid.UUID | None = None
    patient: patients.PatientInput | None = None
    confirm_new: bool = False
    consent: bool = False
    items: Sequence[tuple[str, uuid.UUID]] = ()
    charges: Sequence[ChargeInput] = ()
    discount_kind: str = "amount"
    discount_value: str = ""
    discount_reason: str = ""
    referrer_id: uuid.UUID | None = None
    collection_mode: str = "walk_in"
    promised_at: datetime | None = None
    footer_note: str = ""
    internal_note: str = ""
    payment: billing.PaymentInput | None = None


@dataclass(frozen=True)
class DraftLine:
    """One line of an order being built. `in_house` is None where it doesn't apply: a
    package or an extra charge."""

    item_type: str
    item_id: uuid.UUID | None
    code: str
    description: str
    reason: str
    price_id: uuid.UUID | None
    rate: Decimal
    tests: tuple[Test, ...] = ()
    in_house: bool | None = None


@dataclass
class Draft:
    """An order priced but not saved: what the screen shows before Save."""

    lines: list[DraftLine]
    totals: BillTotals
    visited_at: datetime
    promised_default: datetime
    problems: dict[str, str] = field(default_factory=dict)


def _catalog_line(
    db: Session, kind: str, item_id: uuid.UUID, branch_id: uuid.UUID, at: datetime
) -> DraftLine | str:
    """The line for a test or package, or the reason it can't be ordered."""
    gone = "A test or package you chose is no longer in use."
    if kind not in ("test", "package"):
        return gone
    record = db.get(Test if kind == "test" else Package, item_id)
    if record is None or not record.is_active:
        return gone
    price = catalog.price_row_at(db, kind, item_id, branch_id, at)
    if price is None:
        return f"{record.name} has no price at this branch. Ask an administrator to set one."
    if isinstance(record, Test):
        tests: tuple[Test, ...] = (record,)
        in_house = record.in_house_available
    else:
        tests = tuple(catalog.package_tests(db, item_id))
        in_house = None
        if not tests:
            return f"{record.name} has no tests in it."
    return DraftLine(
        kind, item_id, record.code, record.name, "", price.id, price.amount, tests, in_house
    )


def _charge_line(charge: ChargeInput) -> DraftLine | str:
    description = " ".join(charge.description.split())
    reason = " ".join(charge.reason.split())
    amount = billing.parse_amount(charge.amount)
    if not description or len(description) > 120:
        return "Say what the extra charge is for, in at most 120 characters."
    if amount is None or amount <= 0:
        return "Enter the extra charge as an amount above zero, such as 100."
    if not reason or len(reason) > 120:
        return "Give the reason for the extra charge, in at most 120 characters."
    return DraftLine("extra_charge", None, "", description, reason, None, amount)


def _discount(data: VisitInput, lines: list[DraftLine]) -> tuple[Discount | None, str]:
    """The bill discount as typed, or why it can't be given. It is spread over tests and
    packages only; an extra charge is never discounted."""
    if not data.discount_value.strip():
        return None, ""
    value = billing.parse_amount(data.discount_value)
    if data.discount_kind not in DISCOUNT_KINDS or value is None or value < 0:
        return None, "Enter the discount as an amount or a percentage, such as 100 or 10."
    if value == 0:
        return None, ""
    if data.discount_kind == "pct":
        if value > 100:
            return None, "A percentage discount can be at most 100."
        return Discount("pct", value), ""
    if value > sum((ln.rate for ln in lines if ln.item_type != "extra_charge"), ZERO):
        return None, "The discount is more than the tests and packages cost."
    return Discount("amount", value), ""


def price_order(
    db: Session, principal: Principal, data: VisitInput, at: datetime | None = None
) -> Draft:
    """Price the order at the user's branch. Lines that can't be ordered are left out and
    named in `problems`; nothing is written."""
    branch_id = _branch_of(principal)
    at = at or utcnow()
    problems: dict[str, str] = {}
    lines: list[DraftLine] = []
    seen: set[uuid.UUID] = set()
    if len(data.items) + len(data.charges) > MAX_LINES:
        problems["items"] = f"A visit can have at most {MAX_LINES} lines."
    for kind, item_id in list(data.items)[:MAX_LINES]:
        line = _catalog_line(db, kind, item_id, branch_id, at)
        if isinstance(line, str):
            problems["items"] = line
            continue
        repeated = [t for t in line.tests if t.id in seen]
        if repeated:
            problems["items"] = f"{repeated[0].name} is already on this visit."
            continue
        seen.update(t.id for t in line.tests)
        lines.append(line)
    for charge in list(data.charges)[: MAX_LINES - len(lines)]:
        line = _charge_line(charge)
        if isinstance(line, str):
            problems["charge"] = line
        else:
            lines.append(line)

    discount, discount_problem = _discount(data, lines)
    if discount_problem:
        problems["discount"] = discount_problem
    totals = bill_totals(
        [Line(ln.rate, ln.item_type != "extra_charge") for ln in lines],
        discount,
        load_format(db, branch_id).round_off_to,
    )
    fallback = lab_settings.get_value(db, "visit.default_tat_hours", branch_id)
    hours = [t.default_tat_hours or fallback for ln in lines for t in ln.tests]
    return Draft(lines, totals, at, at + timedelta(hours=max(hours, default=fallback)), problems)


# Looking things up for the screen


@dataclass(frozen=True)
class ItemHit:
    item_type: str
    item_id: uuid.UUID
    code: str
    name: str
    price: Decimal | None
    in_house: bool | None


def find_items(db: Session, principal: Principal, text: str, limit: int = 8) -> list[ItemHit]:
    """Tests and packages matching what was typed, the one Enter would add first."""
    branch_id = _branch_of(principal)
    hits = catalog.search(db, principal, text, branch_id, limit)
    test_ids = [h.item_id for h in hits if h.item_type == "test"]
    in_house = dict(
        db.execute(select(Test.id, Test.in_house_available).where(Test.id.in_(test_ids))).all()
    )
    return [
        ItemHit(h.item_type, h.item_id, h.code, h.name, h.price, in_house.get(h.item_id))
        for h in hits
    ]


def consent_on_file(db: Session, patient_id: uuid.UUID, notice: ConsentNotice) -> Consent | None:
    """The patient's consent to testing under the notice now in force, if not withdrawn."""
    return db.scalar(
        select(Consent)
        .where(
            Consent.subject_type == "patient",
            Consent.subject_id == patient_id,
            Consent.purpose == "testing",
            Consent.notice_id == notice.id,
            Consent.withdrawn_at.is_(None),
        )
        .order_by(Consent.given_at.desc())
        .limit(1)
    )


# Saving


def _problems(
    db: Session,
    principal: Principal,
    data: VisitInput,
    draft: Draft,
    patient: Patient | None,
    notice: ConsentNotice,
    today: date,
) -> dict[str, str]:
    problems = dict(draft.problems)
    if patient is None:
        if data.patient is None:
            problems["patient"] = "Choose a patient or fill in a new one."
        else:
            problems |= data.patient.birth(today)[2] | data.patient.problems()
    if not data.consent and (patient is None or consent_on_file(db, patient.id, notice) is None):
        problems["consent"] = "Tick the consent box once the patient agrees to the notice."
    if not draft.lines:
        problems.setdefault("items", "Add at least one test, package or charge.")
    reason = data.discount_reason.strip()
    if draft.totals.discount > 0 and not reason:
        problems["discount_reason"] = "Give the reason for the discount."
    if len(reason) > 120:
        problems["discount_reason"] = "Use at most 120 characters."
    if data.referrer_id is not None:
        referrer = db.get(Referrer, data.referrer_id)
        if referrer is None or not referrer.is_active:
            problems["referrer"] = "Choose a referrer from the list."
    if data.collection_mode not in COLLECTION_MODES:
        problems["collection_mode"] = "Choose walk-in or home collection."
    if data.promised_at is not None and data.promised_at < draft.visited_at:
        problems["promised_at"] = "The promised time can't be in the past."
    if len(data.footer_note.strip()) > 200:
        problems["footer_note"] = "Use at most 200 characters."
    if data.payment is not None:
        _check(principal, "payment.take", principal.branch_id)
        problems |= data.payment.problems(draft.totals.net)
    return problems


def _order(
    db: Session, principal: Principal, visit: Visit, branch: Branch, draft: Draft, today: date
) -> tuple[list[OrderItem], list[Sample]]:
    """Write the order lines, one sample per specimen type, and the tests to run."""
    items = [
        OrderItem(
            visit_id=visit.id,
            item_type=line.item_type,
            test_id=line.item_id if line.item_type == "test" else None,
            package_id=line.item_id if line.item_type == "package" else None,
            description=line.description,
            reason=line.reason,
            price_id=line.price_id,
            list_price=share.rate,
            discount_amt=share.discount,
            net_price=share.amount,
            created_by=principal.user_id,
        )
        for line, share in zip(draft.lines, draft.totals.lines, strict=True)
    ]
    db.add_all(items)
    sample_of: dict[uuid.UUID, Sample] = {}
    samples: list[Sample] = []
    for specimen_type_id, tests in group_by_specimen(t for ln in draft.lines for t in ln.tests):
        specimen = db.get(SpecimenType, specimen_type_id) if specimen_type_id else None
        sample = Sample(
            sample_no=next_number(db, "sample", branch.id, branch.code, today),
            visit_id=visit.id,
            specimen_type_id=specimen_type_id,
            container=specimen.container if specimen else "",
            created_by=principal.user_id,
        )
        samples.append(sample)
        sample_of |= {t.id: sample for t in tests}
    db.add_all(samples)
    db.flush()
    fallback = lab_settings.get_value(db, "visit.default_tat_hours", branch.id)
    db.add_all(
        OrderTest(
            visit_id=visit.id,
            order_item_id=item.id,
            test_id=test.id,
            sample_id=sample_of[test.id].id,
            due_at=visit.visited_at + timedelta(hours=test.default_tat_hours or fallback),
            created_by=principal.user_id,
        )
        for line, item in zip(draft.lines, items, strict=True)
        for test in line.tests
    )
    db.flush()
    return items, samples


def save_visit(
    db: Session, principal: Principal, data: VisitInput, today: date | None = None
) -> Visit:
    """Register the patient if new, record consent, and save the visit with its order,
    samples, bill and counter payment. Saving the same form again (the same `client_ref`)
    returns the visit already made."""
    branch_id = _branch_of(principal)
    billing.lock_ref(db, data.client_ref)
    done = db.scalar(select(Visit).where(Visit.client_ref == data.client_ref))
    if done is not None:
        if not principal.can("visit.view", done.branch_id):
            raise NotFoundError()
        return done
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise NotFoundError()
    today = today or lab_today()
    patient = (
        patients.get_patient(db, principal, data.patient_id)
        if data.patient_id is not None
        else None
    )
    notice = current_notice(db)
    draft = price_order(db, principal, data)
    problems = _problems(db, principal, data, draft, patient, notice, today)
    if problems:
        raise ValidationFailedError(problems)

    new_patient = patient is None
    if patient is None:
        if data.patient is None:
            raise ValidationFailedError({"patient": "Choose a patient or fill in a new one."})
        patient = patients.insert_patient(db, principal, data.patient, today, data.confirm_new)
    visit = Visit(
        visit_no=next_number(db, "visit", branch.id, branch.code, today),
        branch_id=branch.id,
        patient_id=patient.id,
        referrer_id=data.referrer_id,
        visited_at=draft.visited_at,
        collection_mode=data.collection_mode,
        promised_at=data.promised_at or draft.promised_default,
        footer_note=data.footer_note.strip(),
        internal_note=data.internal_note.strip(),
        client_ref=data.client_ref,
        created_by=principal.user_id,
    )
    db.add(visit)
    if data.consent:
        db.add_all(
            Consent(
                subject_type="patient",
                subject_id=patient.id,
                purpose=purpose,
                method="counter",
                recorded_by=principal.user_id,
                notice_id=notice.id,
            )
            for purpose in CONSENT_PURPOSES
        )
    db.flush()
    items, samples = _order(db, principal, visit, branch, draft, today)
    billing.issue_bill(
        db,
        principal,
        visit,
        patient,
        items,
        data.discount_reason,
        [s.sample_no for s in samples],
        data.payment,
        today,
    )
    if new_patient:
        audit.record(
            db,
            "patient.create",
            "patient",
            patient.id,
            user_id=principal.user_id,
            branch_id=branch.id,
        )
    audit.record(
        db,
        "visit.create",
        "visit",
        visit.id,
        {"visit_no": visit.visit_no, "patient_id": str(patient.id)},
        user_id=principal.user_id,
        branch_id=branch.id,
    )
    return visit


# After saving


@dataclass
class VisitSummary:
    visit: Visit
    patient: Patient
    referrer: Referrer | None
    bill: Bill | None
    lines: list[BillLine]
    payments: list[Payment]
    refund: Refund | None
    samples: list[Sample]
    tests: list[tuple[OrderTest, Test]]


def get_visit(db: Session, principal: Principal, visit_id: uuid.UUID) -> Visit:
    """A visit at a branch the user may see visits at; elsewhere it is not found."""
    visit = db.get(Visit, visit_id)
    if visit is None or not principal.can("visit.view", visit.branch_id):
        raise NotFoundError()
    return visit


def visit_summary(db: Session, principal: Principal, visit_id: uuid.UUID) -> VisitSummary:
    visit = get_visit(db, principal, visit_id)
    bill = None
    if principal.can("bill.view", visit.branch_id):
        bill = db.scalar(
            select(Bill).where(Bill.visit_id == visit.id).order_by(Bill.issued_at.desc()).limit(1)
        )
    return VisitSummary(
        visit=visit,
        patient=db.get_one(Patient, visit.patient_id),
        referrer=db.get(Referrer, visit.referrer_id) if visit.referrer_id else None,
        bill=bill,
        lines=billing.bill_lines(db, bill.id) if bill else [],
        payments=billing.bill_payments(db, bill.id) if bill else [],
        refund=billing.bill_refund(db, bill.id) if bill else None,
        samples=list(
            db.scalars(select(Sample).where(Sample.visit_id == visit.id).order_by(Sample.sample_no))
        ),
        tests=[
            (row[0], row[1])
            for row in db.execute(
                select(OrderTest, Test)
                .join(Test, Test.id == OrderTest.test_id)
                .where(OrderTest.visit_id == visit.id)
                .order_by(Test.code)
            )
        ],
    )
