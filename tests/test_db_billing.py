"""Bills: issuing, part payments, cancelling with a full refund, and the events and audit
rows each of them leaves."""

import json
import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from labra.billing import service
from labra.billing.models import Bill, BillLine, Payment, Refund
from labra.billing.service import PaymentInput
from labra.catalog.models import Department, Test
from labra.core import lab_settings
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.ids import utcnow
from labra.core.models import AuditLog, EventOutbox
from labra.core.registry import Platform
from labra.seed import seed
from labra.visits.models import OrderItem, OrderTest, Sample, Visit
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, billed, sample

CASH_300 = PaymentInput("cash", Decimal(300))
UTR = "426112345678"


def _audit(db: Session, entity_id: object) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog).where(AuditLog.entity_id == str(entity_id)).order_by(AuditLog.id)
        )
    )


def _events(db: Session, bill: Bill) -> list[EventOutbox]:
    rows = db.scalars(select(EventOutbox).order_by(EventOutbox.created_at, EventOutbox.id))
    return [e for e in rows if e.payload.get("bill_no") == bill.bill_no]


def _pay(db: Session, principal, bill: Bill, payment: PaymentInput, ref: uuid.UUID | None = None):
    return service.take_payment(db, principal, bill.id, payment, ref or uuid.uuid4(), SEED_DAY)


@pytest.mark.item("M07")
@pytest.mark.item("M07.1")
def test_issue_bill_totals_lines_and_snapshot(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    admin = as_user(seeded, platform, "anil")
    lab_settings.set_value(
        seeded, "lab.legal_name", "Labra Diagnostics Private Limited", admin.user_id
    )
    bill = billed(
        seeded,
        priya,
        [("350", "35"), ("450.40", "45"), ("100", "0")],
        "Senior citizen",
        title="Mrs",
    )

    assert bill.bill_no == "B2/2627/00001"
    assert len(bill.bill_no) <= 16
    assert (bill.fin_year, bill.bill_date, bill.doc_type) == (2026, SEED_DAY, "bill_of_supply")
    assert (bill.gross, bill.discount) == (Decimal("900.40"), Decimal("80.00"))
    # 820.40 rounds to the nearest rupee.
    assert (bill.round_off, bill.round_off_unit, bill.net) == (
        Decimal("-0.40"),
        Decimal("1.00"),
        Decimal("820.00"),
    )
    assert (bill.status, bill.paid, bill.due) == ("open", Decimal(0), Decimal("820.00"))
    assert bill.recipient_name == "Mrs Sunita Testcase"
    assert bill.discount_reason == "Senior citizen"

    lines = list(
        seeded.scalars(
            select(BillLine).where(BillLine.bill_id == bill.id).order_by(BillLine.line_no)
        )
    )
    assert [(ln.line_no, ln.rate, ln.discount, ln.amount) for ln in lines] == [
        (1, Decimal("350.00"), Decimal("35.00"), Decimal("315.00")),
        (2, Decimal("450.40"), Decimal("45.00"), Decimal("405.40")),
        (3, Decimal("100.00"), Decimal("0.00"), Decimal("100.00")),
    ]
    assert {ln.sac_code for ln in lines} == {"999316"}

    snap = bill.print_snapshot
    assert snap["supplier"]["legal_name"] == "Labra Diagnostics Private Limited"
    assert snap["supplier"]["branch_code"] == "B2"
    assert snap["recipient"]["name"] == "Mrs Sunita Testcase"
    assert snap["counter_user"] == priya.full_name
    assert snap["amount_in_words"] == "Rupees eight hundred twenty only"
    assert snap["currency"]["symbol"] == "₹"
    assert "exempt" in snap["exemption_note"]

    [row] = _audit(seeded, bill.id)
    assert (row.action, row.user_id, row.branch_id) == ("bill.issue", priya.user_id, bill.branch_id)
    assert row.detail == {"bill_no": bill.bill_no, "visit_id": str(bill.visit_id), "net": "820.00"}
    # The next bill at the branch takes the next number.
    assert billed(seeded, priya).bill_no == "B2/2627/00002"


@pytest.mark.item("M07")
def test_bill_refusals_at_issue(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    with pytest.raises(ValidationFailedError) as no_reason:
        billed(seeded, priya, [("350", "35")])
    assert "discount_reason" in no_reason.value.errors
    with pytest.raises(ValidationFailedError) as no_lines:
        billed(seeded, priya, [])
    assert "items" in no_lines.value.errors
    with pytest.raises(ValidationFailedError) as too_much:
        billed(seeded, priya, [("350", "0")], payment=PaymentInput("cash", Decimal(351)))
    assert "amount" in too_much.value.errors
    # None of the refused bills used up a bill number.
    assert billed(seeded, priya).bill_no == "B2/2627/00001"
    # A technician has no front-desk rights.
    suresh = as_user(seeded, platform, "suresh")
    visit = seeded.get_one(Visit, billed(seeded, priya).visit_id)
    with pytest.raises(PermissionDeniedError):
        service.issue_bill(seeded, suresh, visit, None, [], today=SEED_DAY)  # type: ignore[arg-type]


@pytest.mark.item("M07")
def test_zero_net_bill_is_issued_paid(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    bill = billed(seeded, priya, [("350", "350")], "Staff family")
    assert (bill.net, bill.status, bill.due) == (Decimal(0), "paid", Decimal(0))
    assert seeded.scalar(select(func.count()).select_from(Payment)) == 0
    with pytest.raises(ValidationFailedError) as nothing_due:
        _pay(seeded, priya, bill, PaymentInput("cash", Decimal(1)))
    assert nothing_due.value.errors == {"amount": "Nothing is due on this bill."}


@pytest.mark.item("M23")
@pytest.mark.item("EC-B05")
def test_currency_change_leaves_issued_bill(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    admin = as_user(seeded, platform, "anil")
    first = billed(seeded, priya, [("450.40", "0")])
    before = json.dumps(first.print_snapshot, sort_keys=True)
    assert first.net == Decimal("450.00")

    for key, value in {
        "currency.round_off_to": "none",
        "currency.symbol": "Rs",
        "currency.word_major": "taka",
        "lab.legal_name": "Renamed Labs",
        "billing.sac_code": "9993",
        "billing.exemption_note": "A new note.",
    }.items():
        lab_settings.set_value(seeded, key, value, admin.user_id)
    seeded.flush()
    seeded.expire_all()

    again = seeded.get_one(Bill, first.id)
    assert json.dumps(again.print_snapshot, sort_keys=True) == before
    assert (again.net, again.round_off_unit) == (Decimal("450.00"), Decimal("1.00"))
    assert again.print_snapshot["amount_in_words"] == "Rupees four hundred fifty only"
    old_line = seeded.scalar(select(BillLine).where(BillLine.bill_id == first.id))
    assert old_line is not None
    assert old_line.sac_code == "999316"

    new = billed(seeded, priya, [("450.40", "0")])
    assert (new.net, new.round_off, new.round_off_unit) == (Decimal("450.40"), Decimal(0), None)
    assert new.print_snapshot["currency"]["symbol"] == "Rs"
    assert new.print_snapshot["supplier"]["legal_name"] == "Renamed Labs"
    assert new.print_snapshot["exemption_note"] == "A new note."
    assert new.print_snapshot["amount_in_words"] == "Taka four hundred fifty and forty paise only"
    new_line = seeded.scalar(select(BillLine).where(BillLine.bill_id == new.id))
    assert new_line is not None
    assert new_line.sac_code == "9993"


@pytest.mark.item("M07")
@pytest.mark.item("M07.2")
def test_part_payment_then_due_cleared(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    bill = billed(seeded, priya, payment=CASH_300)
    assert (bill.net, bill.paid, bill.status) == (Decimal(800), Decimal(300), "open")
    [first] = seeded.scalars(select(Payment).where(Payment.bill_id == bill.id))
    assert (first.receipt_no, first.mode, first.received_by) == (
        "B2/RC/2627/00001",
        "cash",
        priya.user_id,
    )
    visit = seeded.get_one(Visit, bill.visit_id)
    assert first.patient_id == visit.patient_id

    refused = [
        (PaymentInput("upi", Decimal(100)), "reference"),
        (PaymentInput("upi", Decimal(100), "12-34"), "reference"),
        (PaymentInput("upi", Decimal(100), "paidbyupi"), "reference"),
        (PaymentInput("card", Decimal(100), "12345"), "reference"),
        (PaymentInput("cheque", Decimal(100)), "mode"),
        (PaymentInput("cash", None), "amount"),
        (PaymentInput("cash", Decimal(0)), "amount"),
        (PaymentInput("cash", Decimal("500.01")), "amount"),
    ]
    for payment, field in refused:
        with pytest.raises(ValidationFailedError) as exc:
            _pay(seeded, priya, bill, payment)
        assert list(exc.value.errors) == [field]

    second = _pay(seeded, priya, bill, PaymentInput("card", Decimal(200), "4321"))
    assert (second.receipt_no, second.reference) == ("B2/RC/2627/00002", "4321")
    assert (bill.paid, bill.status) == (Decimal(500), "open")
    third = _pay(seeded, priya, bill, PaymentInput("upi", Decimal(300), f" {UTR} "))
    assert third.reference == UTR
    seeded.refresh(bill)
    assert (bill.paid, bill.due, bill.status) == (Decimal(800), Decimal(0), "paid")


@pytest.mark.item("M07")
def test_amounts_as_typed() -> None:
    assert service.parse_amount(" 1,000 ") == Decimal("1000.00")
    assert service.parse_amount("499.5") == Decimal("499.50")
    for bad in ("", "abc", "10.005", "NaN", "1e400", "Infinity"):
        assert service.parse_amount(bad) is None


@pytest.mark.item("EC-B07")
def test_same_payment_client_ref_once(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    bill = billed(seeded, priya)
    ref = uuid.uuid4()
    first = _pay(seeded, priya, bill, CASH_300, ref)
    again = _pay(seeded, priya, bill, CASH_300, ref)
    assert again.id == first.id
    assert bill.paid == Decimal(300)
    assert seeded.scalar(select(func.count()).select_from(Payment)) == 1
    assert len(_audit(seeded, first.id)) == 1
    # The same reference can't be replayed against another bill.
    other = billed(seeded, priya)
    with pytest.raises(NotFoundError):
        _pay(seeded, priya, other, CASH_300, ref)
    assert other.paid == 0


@pytest.mark.item("EC-B07")
def test_concurrent_payment_client_ref_taken_once(
    committed_engine: Engine, platform: Platform
) -> None:
    with Session(committed_engine) as setup:
        seed(setup, platform.identity, SEED_DAY)
        priya = as_user(setup, platform, "priya")
        bill_id = billed(setup, priya).id
        setup.commit()

    ref = uuid.uuid4()
    start = threading.Barrier(2)
    taken: list[uuid.UUID] = []
    failures: list[BaseException] = []

    def pay() -> None:
        try:
            with Session(committed_engine) as db:
                start.wait(timeout=10)
                payment = service.take_payment(db, priya, bill_id, CASH_300, ref, SEED_DAY)
                taken.append(payment.id)
                db.commit()
        except BaseException as exc:  # noqa: BLE001  reported by the assert below
            failures.append(exc)

    threads = [threading.Thread(target=pay) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert failures == []
    assert len(taken) == 2
    assert taken[0] == taken[1]
    with Session(committed_engine) as check:
        assert check.scalar(select(func.count()).select_from(Payment)) == 1
        assert check.get_one(Bill, bill_id).paid == Decimal(300)


@pytest.mark.item("M26")
@pytest.mark.item("M07")
def test_later_payment_emits_event_and_audit(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    bill = billed(seeded, priya)
    assert [e.topic for e in _events(seeded, bill)] == ["bill.issued"]
    payment = _pay(seeded, priya, bill, PaymentInput("upi", Decimal(300), UTR))

    issued, received = _events(seeded, bill)
    assert received.topic == "payment.received"
    assert received.payload == {
        "schema_version": 1,
        "entity": "payment",
        "entity_id": str(payment.id),
        "bill_no": bill.bill_no,
        "branch_id": str(bill.branch_id),
        "visit_id": str(bill.visit_id),
        "net": "800.00",
        "paid": "300.00",
        "amount": "300.00",
        "mode": "upi",
    }
    assert issued.payload["entity"] == "bill"
    assert issued.payload["paid"] == "0.00"

    [row] = _audit(seeded, payment.id)
    assert (row.action, row.entity, row.user_id) == ("payment.receive", "payment", priya.user_id)
    assert row.detail == {
        "receipt_no": payment.receipt_no,
        "bill_id": str(bill.id),
        "mode": "upi",
        "amount": "300.00",
    }


@pytest.mark.item("M26")
def test_bill_events_in_same_transaction(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    seeded.commit()
    count = select(func.count()).select_from(EventOutbox)
    assert seeded.scalar(count) == 0

    bill = billed(seeded, priya, payment=CASH_300)
    bill_id = bill.id
    assert [e.topic for e in _events(seeded, bill)] == ["bill.issued", "payment.received"]
    # The bill and its events stand or fall together.
    seeded.rollback()
    assert seeded.scalar(count) == 0
    assert seeded.get(Bill, bill_id) is None

    kept = billed(seeded, priya, payment=CASH_300)
    seeded.commit()
    assert len(_events(seeded, kept)) == 2


@pytest.mark.item("M26")
def test_bill_event_payload_has_no_personal_data(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    admin = as_user(seeded, platform, "anil")
    bill = billed(
        seeded,
        priya,
        [("350", "35")],
        "Neighbour of the owner",
        payment=PaymentInput("upi", Decimal(100), UTR),
        full_name="Zubeida Uniquename",
        phone="9000000042",
    )
    service.cancel_bill(
        seeded, admin, bill.id, "Booked for the wrong person", True, bill.row_version
    )

    events = _events(seeded, bill)
    assert [e.topic for e in events] == ["bill.issued", "payment.received", "bill.cancelled"]
    allowed = {
        "schema_version",
        "entity",
        "entity_id",
        "bill_no",
        "branch_id",
        "visit_id",
        "net",
        "paid",
        "amount",
        "mode",
        "refunded",
    }
    for event in events:
        assert set(event.payload) <= allowed
        body = json.dumps(event.payload)
        for private in ("Zubeida", "Uniquename", "9000000042", "Neighbour", "wrong person", UTR):
            assert private not in body
    for row in seeded.scalars(select(AuditLog).where(AuditLog.branch_id == bill.branch_id)):
        body = json.dumps(row.detail)
        for private in ("Zubeida", "9000000042", "Neighbour", "wrong person", UTR):
            assert private not in body


@pytest.mark.item("M07")
@pytest.mark.item("EC-B05")
def test_cancel_needs_reason_confirm_and_version(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    admin = as_user(seeded, platform, "anil")
    bill = billed(seeded, priya)
    version = bill.row_version

    # The front desk can't cancel a bill.
    with pytest.raises(PermissionDeniedError):
        service.cancel_bill(seeded, priya, bill.id, "Wrong tests", True, version)
    with pytest.raises(ValidationFailedError) as no_reason:
        service.cancel_bill(seeded, admin, bill.id, "  ", True, version)
    assert list(no_reason.value.errors) == ["reason"]
    with pytest.raises(ValidationFailedError) as no_confirm:
        service.cancel_bill(seeded, admin, bill.id, "Wrong tests", False, version)
    assert list(no_confirm.value.errors) == ["confirm"]
    # A payment taken since the screen was opened makes the copy stale.
    _pay(seeded, priya, bill, CASH_300)
    with pytest.raises(ConflictError, match="changed this record"):
        service.cancel_bill(seeded, admin, bill.id, "Wrong tests", True, version)
    assert bill.status == "open"

    done = service.cancel_bill(seeded, admin, bill.id, "Wrong tests", True, bill.row_version)
    assert (done.status, done.cancel_reason, done.cancelled_by) == (
        "cancelled",
        "Wrong tests",
        admin.user_id,
    )
    assert done.cancelled_at is not None
    # Cancelled is final.
    with pytest.raises(ConflictError, match="already cancelled"):
        service.cancel_bill(seeded, admin, bill.id, "Again", True, done.row_version)
    with pytest.raises(ConflictError, match="cancelled"):
        _pay(seeded, priya, bill, CASH_300)


@pytest.mark.item("M07")
@pytest.mark.item("EC-B05")
def test_cancel_paid_bill_records_full_refund(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    admin = as_user(seeded, platform, "anil")
    bill = billed(seeded, priya, payment=CASH_300)
    _pay(seeded, priya, bill, PaymentInput("card", Decimal(200), "4321"))

    with pytest.raises(ValidationFailedError) as bad_mode:
        service.cancel_bill(
            seeded, admin, bill.id, "Patient left", True, bill.row_version, "cheque"
        )
    assert list(bad_mode.value.errors) == ["refund_mode"]
    service.cancel_bill(
        seeded, admin, bill.id, "Patient left", True, bill.row_version, "upi", UTR, SEED_DAY
    )

    [refund] = seeded.scalars(select(Refund).where(Refund.bill_id == bill.id))
    assert (refund.refund_no, refund.amount, refund.mode, refund.reference) == (
        "B2/RF/2627/00001",
        Decimal(500),
        "upi",
        UTR,
    )
    assert (refund.reason, refund.refunded_by) == ("Patient left", admin.user_id)
    # What was paid stays on the bill; the refund row says it went back.
    seeded.refresh(bill)
    assert (bill.status, bill.paid, bill.net) == ("cancelled", Decimal(500), Decimal(800))
    assert _events(seeded, bill)[-1].payload["refunded"] == "500.00"
    assert [r.action for r in _audit(seeded, bill.id)] == ["bill.issue", "bill.cancel"]
    [row] = _audit(seeded, refund.id)
    assert (row.action, row.detail["amount"]) == ("refund.record", "500.00")

    # Nothing paid, nothing to refund.
    unpaid = billed(seeded, priya)
    service.cancel_bill(seeded, admin, unpaid.id, "Duplicate entry", True, unpaid.row_version)
    assert seeded.scalar(select(func.count()).select_from(Refund)) == 1
    assert _events(seeded, unpaid)[-1].payload["refunded"] == "0.00"


@pytest.mark.item("M07")
@pytest.mark.item("EC-B05")
def test_cancel_marks_samples_cancelled(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    admin = as_user(seeded, platform, "anil")
    bill = billed(seeded, priya)
    visit = seeded.get_one(Visit, bill.visit_id)
    pending, collected, received = (
        sample(seeded, visit, s) for s in ("pending", "collected", "received")
    )
    department = Department(name="Synthetic department")
    seeded.add(department)
    seeded.flush()
    test = Test(code="zzsyn", name="Synthetic test", department_id=department.id)
    seeded.add(test)
    seeded.flush()
    item = seeded.scalars(select(OrderItem).where(OrderItem.visit_id == visit.id)).first()
    assert item is not None
    ordered = OrderTest(
        visit_id=visit.id,
        order_item_id=item.id,
        test_id=test.id,
        sample_id=pending.id,
        perform_branch_id=visit.branch_id,
        due_at=utcnow(),
    )
    seeded.add(ordered)
    seeded.flush()

    service.cancel_bill(seeded, admin, bill.id, "Patient left", True, bill.row_version)

    assert (pending.status, collected.status) == ("cancelled", "cancelled")
    # A sample already in the lab is left for the lab to deal with.
    assert received.status == "received"
    assert ordered.status == "cancelled"
    assert visit.status == "cancelled"
    items = list(seeded.scalars(select(OrderItem).where(OrderItem.visit_id == visit.id)))
    assert {(i.status, i.cancel_reason) for i in items} == {("cancelled", "Patient left")}
    assert (
        seeded.scalar(select(func.count()).select_from(Sample).where(Sample.status == "cancelled"))
        == 2
    )


@pytest.mark.item("EC-A05")
@pytest.mark.item("M07")
def test_other_branch_bill_not_found(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    b3desk = as_user(seeded, platform, "b3desk")
    bill = billed(seeded, priya, payment=CASH_300)
    with pytest.raises(NotFoundError):
        service.get_bill(seeded, b3desk, bill.id)
    with pytest.raises(NotFoundError):
        _pay(seeded, b3desk, bill, CASH_300)
    # A branch manager elsewhere can't cancel it either.
    with pytest.raises(NotFoundError):
        service.cancel_bill(seeded, b3desk, bill.id, "Not ours", True, bill.row_version)
    assert (bill.status, bill.paid) == ("open", Decimal(300))


@pytest.mark.item("M07.3")
def test_a_upi_reference_seen_before_is_refused_until_the_desk_confirms(
    seeded: Session, platform: Platform
) -> None:
    priya = as_user(seeded, platform, "priya")
    first = billed(seeded, priya, payment=PaymentInput("upi", Decimal(300), "AXIS426112345678"))
    [receipt] = seeded.scalars(select(Payment).where(Payment.bill_id == first.id))
    other = billed(seeded, priya)

    # Typed in another case on another bill, it is still the same reference.
    again = PaymentInput("upi", Decimal(100), "axis426112345678")
    with pytest.raises(ValidationFailedError) as exc:
        _pay(seeded, priya, other, again)
    assert list(exc.value.errors) == ["reference", "same_payment"]
    assert receipt.receipt_no in exc.value.errors["reference"]
    with pytest.raises(ValidationFailedError):
        billed(seeded, priya, payment=again)

    # A card's last four digits and a new reference are not held up.
    _pay(seeded, priya, other, PaymentInput("card", Decimal(100), "5678"))
    _pay(seeded, priya, other, PaymentInput("upi", Decimal(100), UTR))

    # One transfer for two bills goes through once the desk says so, and saving that form
    # twice still takes the money once.
    ref = uuid.uuid4()
    confirmed = PaymentInput("upi", Decimal(100), "axis426112345678", same_payment=True)
    taken = _pay(seeded, priya, other, confirmed, ref)
    assert _pay(seeded, priya, other, again, ref).id == taken.id
    assert billed(seeded, priya, payment=confirmed).paid == Decimal(100)
