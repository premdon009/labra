"""Bills: issue one for a visit, take payments against it, cancel it.

A bill is issued complete and its figures never change afterwards. Everything printed on
it is frozen in `print_snapshot`, so a later change to the lab's name, note or currency
leaves issued bills as they were. Each change queues an event in the same transaction.

Locks are always taken in the same order: the client reference, the bill, a number
series, and last the audit chain.
"""

import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.billing.models import BILL_STATUSES, PAYMENT_MODES, Bill, BillLine, Payment, Refund
from labra.core import audit, lab_settings, outbox
from labra.core.currency import amount_in_words, load_format
from labra.core.dialect import advisory_lock_for
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.ids import lab_today, utcnow
from labra.core.money import ZERO, apply_payment, bill_status, money, round_to_unit
from labra.core.numbering import financial_year, next_number
from labra.core.paging import Page, page_of
from labra.org.models import Branch
from labra.org.service import stale
from labra.patients.models import Patient, Referrer
from labra.visits.models import OrderItem, OrderTest, Sample, Visit

# What staff copy from the payer's UPI app; banks differ in length and letters.
_UTR_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9]{8,35}$")
_CARD_RE = re.compile(r"^\d{4}$")
_NAMESPACE_PARTS = ("bill", "payment", "refund")
# The money columns hold ten digits before the point.
MAX_AMOUNT = Decimal(10**10)


def _check(principal: Principal, permission: str, branch_id: uuid.UUID | None = None) -> None:
    if not principal.can(permission, branch_id):
        raise PermissionDeniedError()


def derived_ref(client_ref: uuid.UUID, part: str) -> uuid.UUID:
    """The reference of a record made together with another: saving the same form twice
    gives the same bill, payment and refund references."""
    if part not in _NAMESPACE_PARTS:
        raise ValueError(f"Unknown reference part {part!r}.")
    return uuid.uuid5(client_ref, part)


def lock_ref(db: Session, client_ref: uuid.UUID) -> None:
    """Make a second save of the same form wait for the first, until commit."""
    advisory_lock_for(db, str(client_ref))


def parse_amount(value: str) -> Decimal | None:
    """An amount as typed at the counter, or None when it isn't one."""
    try:
        amount = Decimal(value.strip().replace(",", ""))
    except InvalidOperation:
        return None
    if not amount.is_finite() or abs(amount) >= MAX_AMOUNT or amount != money(amount):
        return None
    return money(amount)


@dataclass(frozen=True)
class PaymentInput:
    mode: str
    amount: Decimal | None
    reference: str = ""
    # The desk has said this UPI payment also paid another bill.
    same_payment: bool = False

    def problems(self, due: Decimal) -> dict[str, str]:
        p: dict[str, str] = {}
        reference = self.reference.strip()
        if self.mode not in PAYMENT_MODES:
            p["mode"] = "Choose cash, UPI or card."
        elif self.mode == "upi" and not _UTR_RE.match(reference):
            p["reference"] = (
                "Enter the UPI reference (UTR): 8 to 35 letters and digits, with a digit in it."
            )
        elif self.mode == "card" and not _CARD_RE.match(reference):
            p["reference"] = "Enter the last 4 digits of the card."
        elif len(reference) > 40:
            p["reference"] = "Use at most 40 characters."
        if self.amount is None:
            p["amount"] = "Enter the amount, such as 500 or 499.50."
        elif self.amount <= 0:
            p["amount"] = "A payment must be more than zero."
        elif due <= 0:
            p["amount"] = "Nothing is due on this bill."
        elif self.amount > due:
            p["amount"] = "The payment is more than the amount due."
        return p


def _event(db: Session, topic: str, bill: Bill, entity: str, entity_id: uuid.UUID, **more: str):
    """Queue an event about a bill. IDs, numbers and amounts only: never a name, phone
    number or anything typed as free text."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "entity": entity,
        "entity_id": str(entity_id),
        "bill_no": bill.bill_no,
        "branch_id": str(bill.branch_id),
        "visit_id": str(bill.visit_id),
        "net": str(bill.net),
        "paid": str(bill.paid),
        **more,
    }
    return outbox.emit(db, topic, payload)


def _snapshot(
    db: Session,
    principal: Principal,
    branch: Branch,
    visit: Visit,
    patient: Patient,
    recipient: str,
    sample_nos: Sequence[str],
    net: Decimal,
) -> dict[str, Any]:
    fmt = load_format(db, branch.id)
    legal_name = lab_settings.get_value(db, "lab.legal_name") or lab_settings.get_value(
        db, "lab.display_name"
    )
    referrer = db.get(Referrer, visit.referrer_id) if visit.referrer_id else None
    return {
        "supplier": {
            "legal_name": legal_name,
            "branch_code": branch.code,
            "branch_name": branch.name,
            "address": branch.address,
            "gstin": branch.gstin,
            "state_code": branch.state_code,
            "phone": branch.phone,
            "email": branch.email,
        },
        "recipient": {"name": recipient, "patient_no": patient.patient_no},
        "referrer": referrer.name if referrer else "",
        "visit_no": visit.visit_no,
        "sample_nos": list(sample_nos),
        "counter_user": principal.full_name,
        "exemption_note": lab_settings.get_value(db, "billing.exemption_note"),
        "footer_note": visit.footer_note,
        "receipt_footer": lab_settings.get_value(db, "branch.receipt_footer", branch.id),
        "currency": fmt.snapshot(),
        "amount_in_words": amount_in_words(net, fmt),
    }


def _check_reference_is_new(db: Session, payment: PaymentInput, client_ref: uuid.UUID) -> None:
    """A UPI reference names one transfer, so seeing it a second time is usually a mistyped
    or reused number. One transfer can pay two bills, though, so the desk may confirm it."""
    reference = payment.reference.strip()
    if payment.mode != "upi" or payment.same_payment or not reference:
        return
    earlier = db.scalar(
        select(Payment.receipt_no)
        .where(
            Payment.mode == "upi",
            func.lower(Payment.reference) == reference.lower(),
            Payment.client_ref != client_ref,
        )
        .order_by(Payment.created_at)
        .limit(1)
    )
    if earlier is not None:
        raise ValidationFailedError(
            {
                "reference": f"This UPI reference is already on receipt {earlier}. "
                "Check it against the patient's phone.",
                "same_payment": "If one UPI payment covers both bills, tick this and save again.",
            }
        )


def _receive(
    db: Session,
    principal: Principal,
    bill: Bill,
    branch: Branch,
    patient_id: uuid.UUID,
    payment: PaymentInput,
    client_ref: uuid.UUID,
    today: date,
) -> Payment:
    """Write a checked payment and move the bill's paid amount. No audit row: the caller
    writes it last."""
    if payment.amount is None:
        raise ValidationFailedError({"amount": "Enter the amount, such as 500 or 499.50."})
    _check_reference_is_new(db, payment, client_ref)
    paid, _, status = apply_payment(bill.net, bill.paid, payment.amount)
    row = Payment(
        receipt_no=next_number(db, "receipt", branch.id, branch.code, today),
        branch_id=branch.id,
        bill_id=bill.id,
        patient_id=patient_id,
        mode=payment.mode,
        amount=money(payment.amount),
        reference=payment.reference.strip(),
        received_by=principal.user_id,
        created_by=principal.user_id,
        client_ref=client_ref,
    )
    db.add(row)
    bill.paid = paid
    bill.status = status
    bill.updated_by = principal.user_id
    db.flush()
    _event(db, "payment.received", bill, "payment", row.id, amount=str(row.amount), mode=row.mode)
    return row


def _audit_payment(db: Session, principal: Principal, payment: Payment) -> None:
    audit.record(
        db,
        "payment.receive",
        "payment",
        payment.id,
        {
            "receipt_no": payment.receipt_no,
            "bill_id": str(payment.bill_id),
            "mode": payment.mode,
            "amount": str(payment.amount),
        },
        user_id=principal.user_id,
        branch_id=payment.branch_id,
    )


def issue_bill(
    db: Session,
    principal: Principal,
    visit: Visit,
    patient: Patient,
    items: Sequence[OrderItem],
    discount_reason: str = "",
    sample_nos: Sequence[str] = (),
    payment: PaymentInput | None = None,
    today: date | None = None,
    audit_first: Callable[[], None] | None = None,
) -> Bill:
    """Issue the bill of supply for a visit's order lines, with the payment taken at the
    counter if there is one. The lines already carry their rate and discount; the bill
    adds them up and rounds the total as the branch's currency settings say.

    Called while a visit is being saved, after its own number series: this takes the bill
    and receipt numbers and then writes the audit rows. `audit_first` writes the caller's
    own audit rows just ahead of them, so the log reads visit, bill, payment.
    """
    _check(principal, "visit.create", visit.branch_id)
    if payment is not None:
        _check(principal, "payment.take", visit.branch_id)
    branch = db.get(Branch, visit.branch_id)
    if branch is None:
        raise NotFoundError()
    today = today or lab_today()
    discount_reason = discount_reason.strip()
    gross = money(sum((i.list_price for i in items), ZERO))
    discount = money(sum((i.discount_amt for i in items), ZERO))
    unit = load_format(db, branch.id).round_off_to
    net = round_to_unit(gross - discount, unit)

    problems: dict[str, str] = {}
    if not items:
        problems["items"] = "Add at least one test, package or charge."
    if discount > 0 and not discount_reason:
        problems["discount_reason"] = "Give the reason for the discount."
    if len(discount_reason) > 120:
        problems["discount_reason"] = "Use at most 120 characters."
    if payment is not None:
        problems |= payment.problems(net)
    if problems:
        raise ValidationFailedError(problems)

    recipient = f"{patient.title} {patient.full_name}".strip()[:120]
    sac_code = lab_settings.get_value(db, "billing.sac_code")
    bill = Bill(
        bill_no=next_number(db, "bos", branch.id, branch.code, today),
        fin_year=financial_year(today),
        branch_id=branch.id,
        visit_id=visit.id,
        recipient_name=recipient,
        bill_date=today,
        place_of_supply_state=branch.state_code or lab_settings.get_value(db, "lab.state_code"),
        gross=gross,
        discount=discount,
        discount_reason=discount_reason if discount > 0 else "",
        round_off=net - (gross - discount),
        round_off_unit=unit,
        net=net,
        paid=ZERO,
        status=bill_status(net, ZERO),
        print_snapshot=_snapshot(db, principal, branch, visit, patient, recipient, sample_nos, net),
        client_ref=derived_ref(visit.client_ref, "bill"),
        created_by=principal.user_id,
    )
    db.add(bill)
    db.flush()
    db.add_all(
        BillLine(
            bill_id=bill.id,
            order_item_id=item.id,
            line_no=n,
            description=item.description,
            sac_code=sac_code,
            rate=item.list_price,
            discount=item.discount_amt,
            amount=item.net_price,
            price_id=item.price_id,
            created_by=principal.user_id,
        )
        for n, item in enumerate(items, start=1)
    )
    db.flush()
    _event(db, "bill.issued", bill, "bill", bill.id)
    received = None
    if payment is not None:
        ref = derived_ref(visit.client_ref, "payment")
        received = _receive(db, principal, bill, branch, patient.id, payment, ref, today)
    if audit_first is not None:
        audit_first()
    audit.record(
        db,
        "bill.issue",
        "bill",
        bill.id,
        {"bill_no": bill.bill_no, "visit_id": str(visit.id), "net": str(bill.net)},
        user_id=principal.user_id,
        branch_id=branch.id,
    )
    if received is not None:
        _audit_payment(db, principal, received)
    return bill


def get_bill(
    db: Session, principal: Principal, bill_id: uuid.UUID, for_update: bool = False
) -> Bill:
    """A bill at a branch the user may see bills at; elsewhere it is not found."""
    query = select(Bill).where(Bill.id == bill_id)
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    bill = db.scalar(query)
    if bill is None or not principal.can("bill.view", bill.branch_id):
        raise NotFoundError()
    return bill


def bill_lines(db: Session, bill_id: uuid.UUID) -> list[BillLine]:
    return list(
        db.scalars(select(BillLine).where(BillLine.bill_id == bill_id).order_by(BillLine.line_no))
    )


def bill_payments(db: Session, bill_id: uuid.UUID) -> list[Payment]:
    return list(
        db.scalars(
            select(Payment)
            .where(Payment.bill_id == bill_id)
            .order_by(Payment.received_at, Payment.receipt_no)
        )
    )


def bill_refund(db: Session, bill_id: uuid.UUID) -> Refund | None:
    return db.scalar(select(Refund).where(Refund.bill_id == bill_id))


def get_payment(db: Session, principal: Principal, payment_id: uuid.UUID) -> tuple[Payment, Bill]:
    """A payment and its bill, at a branch the user may see bills at."""
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError()
    return payment, get_bill(db, principal, payment.bill_id)


def bill_page(
    db: Session,
    principal: Principal,
    page: int,
    day_from: date | None = None,
    day_to: date | None = None,
    status: str = "",
) -> Page[Bill]:
    """Bills at the user's branches, newest first, optionally by date and status."""
    stmt = select(Bill).where(Bill.branch_id.in_(principal.branches_with("bill.view")))
    if day_from is not None:
        stmt = stmt.where(Bill.bill_date >= day_from)
    if day_to is not None:
        stmt = stmt.where(Bill.bill_date <= day_to)
    if status in BILL_STATUSES:
        stmt = stmt.where(Bill.status == status)
    return page_of(db, stmt.order_by(Bill.bill_date.desc(), Bill.issued_at.desc(), Bill.id), page)


def dues_page(db: Session, principal: Principal, page: int) -> Page[Bill]:
    """Bills with money still to collect, the oldest first."""
    stmt = select(Bill).where(
        Bill.branch_id.in_(principal.branches_with("bill.view")), Bill.status == "open"
    )
    return page_of(db, stmt.order_by(Bill.bill_date, Bill.issued_at, Bill.id), page)


def take_payment(
    db: Session,
    principal: Principal,
    bill_id: uuid.UUID,
    payment: PaymentInput,
    client_ref: uuid.UUID,
    today: date | None = None,
) -> Payment:
    """Take money against an open bill. Sending the same `client_ref` again returns the
    payment already taken, so a double-clicked button takes the money once."""
    lock_ref(db, client_ref)
    done = db.scalar(select(Payment).where(Payment.client_ref == client_ref))
    if done is not None:
        if done.bill_id != bill_id or not principal.can("bill.view", done.branch_id):
            raise NotFoundError()
        return done
    bill = get_bill(db, principal, bill_id, for_update=True)
    _check(principal, "payment.take", bill.branch_id)
    if bill.status == "cancelled":
        raise ConflictError("This bill is cancelled, so it can't take a payment.")
    problems = payment.problems(bill.net - bill.paid)
    if problems:
        raise ValidationFailedError(problems)
    branch = db.get(Branch, bill.branch_id)
    visit = db.get(Visit, bill.visit_id)
    if branch is None or visit is None:
        raise NotFoundError()
    row = _receive(
        db, principal, bill, branch, visit.patient_id, payment, client_ref, today or lab_today()
    )
    _audit_payment(db, principal, row)
    return row


# A test this far along has cost the lab money or produced a result someone may have seen.
PAST_CANCELLING = ("sent_out", "resulted", "verified", "released")
CANCEL_BLOCKED = (
    "This bill can't be cancelled: one of its tests was already sent to an outside lab or"
    " has a result."
)


def cancel_blocked(db: Session, visit_id: uuid.UUID) -> bool:
    """True once a test of the visit was sent out or has a result."""
    return (
        db.scalar(
            select(OrderTest.id)
            .where(OrderTest.visit_id == visit_id, OrderTest.status.in_(PAST_CANCELLING))
            .limit(1)
        )
        is not None
    )


def _cancel_order(db: Session, principal: Principal, visit: Visit, reason: str) -> None:
    """Cancel the visit, its order lines and tests, and the samples not yet in the lab.
    Refused once the lab's work on any test can't be taken back."""
    if cancel_blocked(db, visit.id):
        raise ConflictError(CANCEL_BLOCKED)
    for item in db.scalars(
        select(OrderItem).where(OrderItem.visit_id == visit.id, OrderItem.status == "active")
    ):
        item.status = "cancelled"
        item.cancel_reason = reason
        item.updated_by = principal.user_id
    for ordered in db.scalars(
        select(OrderTest).where(OrderTest.visit_id == visit.id, OrderTest.status != "cancelled")
    ):
        ordered.status = "cancelled"
        ordered.updated_by = principal.user_id
    for sample in db.scalars(
        select(Sample).where(
            Sample.visit_id == visit.id, Sample.status.in_(("pending", "collected"))
        )
    ):
        sample.status = "cancelled"
        sample.updated_by = principal.user_id
    visit.status = "cancelled"
    visit.updated_by = principal.user_id


def cancel_bill(
    db: Session,
    principal: Principal,
    bill_id: uuid.UUID,
    reason: str,
    confirm: bool,
    row_version: int,
    refund_mode: str = "cash",
    refund_reference: str = "",
    today: date | None = None,
) -> Bill:
    """Cancel a bill and its visit, for good. Money already taken is paid back in full and
    recorded as one refund. The tests and any samples not yet in the lab are cancelled."""
    bill = get_bill(db, principal, bill_id, for_update=True)
    _check(principal, "bill.cancel", bill.branch_id)
    if bill.status == "cancelled":
        raise ConflictError("This bill is already cancelled.")
    reason = reason.strip()
    refund_reference = refund_reference.strip()
    problems: dict[str, str] = {}
    if not reason:
        problems["reason"] = "Give the reason for cancelling."
    elif len(reason) > 200:
        problems["reason"] = "Use at most 200 characters."
    if not confirm:
        problems["confirm"] = "Tick the box to confirm. A cancelled bill can't be brought back."
    if bill.paid > 0:
        if refund_mode not in PAYMENT_MODES:
            problems["refund_mode"] = "Choose how the money was paid back."
        if len(refund_reference) > 40:
            problems["refund_reference"] = "Use at most 40 characters."
    if problems:
        raise ValidationFailedError(problems)
    if bill.row_version != row_version:
        raise stale(db, bill)
    branch = db.get(Branch, bill.branch_id)
    visit = db.get(Visit, bill.visit_id)
    if branch is None or visit is None:
        raise NotFoundError()
    _cancel_order(db, principal, visit, reason)

    refund = None
    if bill.paid > 0:
        refund = Refund(
            refund_no=next_number(db, "refund", branch.id, branch.code, today or lab_today()),
            branch_id=branch.id,
            bill_id=bill.id,
            amount=bill.paid,
            mode=refund_mode,
            reference=refund_reference,
            reason=reason,
            refunded_by=principal.user_id,
            created_by=principal.user_id,
            client_ref=derived_ref(bill.client_ref, "refund"),
        )
        db.add(refund)
    bill.status = "cancelled"
    bill.cancel_reason = reason
    bill.cancelled_at = utcnow()
    bill.cancelled_by = principal.user_id
    bill.updated_by = principal.user_id

    db.flush()

    refunded = str(refund.amount) if refund is not None else str(ZERO)
    _event(db, "bill.cancelled", bill, "bill", bill.id, refunded=refunded)
    audit.record(
        db,
        "bill.cancel",
        "bill",
        bill.id,
        {"bill_no": bill.bill_no, "visit_id": str(visit.id), "refunded": refunded},
        user_id=principal.user_id,
        branch_id=branch.id,
    )
    if refund is not None:
        audit.record(
            db,
            "refund.record",
            "refund",
            refund.id,
            {"refund_no": refund.refund_no, "bill_id": str(bill.id), "amount": refunded},
            user_id=principal.user_id,
            branch_id=branch.id,
        )
    return bill
