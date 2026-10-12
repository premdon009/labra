"""The database itself keeps bills honest: CHECKs on every issued figure, and triggers that
refuse edits to issued bills, lines, payments and refunds."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from labra.billing.models import Bill, BillLine, Payment, Refund
from labra.core.ids import utcnow
from labra.org.models import Branch
from labra.patients.models import Patient
from labra.visits.models import OrderItem, Visit

DAY = date(2026, 10, 9)


def _visit(db: Session) -> tuple[Branch, Patient, Visit, OrderItem]:
    branch = db.scalar(select(Branch).where(Branch.code == "B2"))
    assert branch is not None
    patient = Patient(
        patient_no=f"B2/P/{uuid.uuid4().hex[:6]}",
        registered_branch_id=branch.id,
        full_name="Asha Testcase",
        sex="F",
        dob=date(1990, 1, 1),
    )
    db.add(patient)
    db.flush()
    visit = Visit(
        visit_no=f"B2/V/{uuid.uuid4().hex[:8]}",
        branch_id=branch.id,
        patient_id=patient.id,
        promised_at=utcnow(),
        client_ref=uuid.uuid4(),
    )
    db.add(visit)
    db.flush()
    item = OrderItem(
        visit_id=visit.id,
        item_type="extra_charge",
        description="Home collection",
        reason="Home visit",
        list_price=Decimal(100),
        net_price=Decimal(100),
    )
    db.add(item)
    db.flush()
    return branch, patient, visit, item


def _bill(db: Session, visit: Visit, **changes: Any) -> Bill:
    values: dict[str, Any] = {
        "bill_no": f"B2/2627/{uuid.uuid4().int % 10**5:05d}",
        "fin_year": 2026,
        "branch_id": visit.branch_id,
        "visit_id": visit.id,
        "recipient_name": "Asha Testcase",
        "bill_date": DAY,
        "place_of_supply_state": "29",
        "gross": Decimal(100),
        "discount": Decimal(0),
        "round_off": Decimal(0),
        "round_off_unit": Decimal("1.00"),
        "net": Decimal(100),
        "paid": Decimal(0),
        "status": "open",
        "print_snapshot": {},
        "client_ref": uuid.uuid4(),
    }
    values.update(changes)
    bill = Bill(**values)
    db.add(bill)
    db.flush()
    return bill


@pytest.fixture
def issued(seeded: Session) -> tuple[Bill, BillLine, Payment, Refund]:
    """One issued bill with a line, a part payment and a refund row: enough to try every
    forbidden change."""
    branch, patient, visit, item = _visit(seeded)
    bill = _bill(seeded, visit)
    line = BillLine(
        bill_id=bill.id,
        order_item_id=item.id,
        line_no=1,
        description="Home collection",
        rate=Decimal(100),
        discount=Decimal(0),
        amount=Decimal(100),
    )
    payment = Payment(
        receipt_no="B2/RC/2627/90001",
        branch_id=branch.id,
        bill_id=bill.id,
        patient_id=patient.id,
        mode="cash",
        amount=Decimal(40),
        client_ref=uuid.uuid4(),
    )
    refund = Refund(
        refund_no="B2/RF/2627/90001",
        branch_id=branch.id,
        bill_id=bill.id,
        amount=Decimal(40),
        mode="cash",
        reason="Patient left",
        client_ref=uuid.uuid4(),
    )
    seeded.add_all([line, payment, refund])
    seeded.flush()
    seeded.execute(text("update bill set paid = 40 where id = :id"), {"id": bill.id})
    return bill, line, payment, refund


@pytest.mark.item("EC-B04")
@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        ({"bill_no": "B2_2627_00001"}, "bill_no"),
        ({"bill_no": "B2 2627 1"}, "bill_no"),
        ({"doc_type": "receipt"}, "doc_type"),
        ({"status": "unpaid"}, "status"),
        ({"gross": Decimal(-10), "net": Decimal(-10)}, "gross|discount|net_not_negative|paid"),
        (
            {"discount": Decimal(120), "discount_reason": "Staff", "net": Decimal(-20)},
            "discount|net_not_negative|paid",
        ),
        ({"discount": Decimal(10), "net": Decimal(90)}, "discount_reason"),
        ({"net": Decimal(99)}, "net"),
        ({"round_off": Decimal("0.60"), "net": Decimal("100.60")}, "round_off"),
        (
            {"round_off": Decimal("0.01"), "net": Decimal("100.01"), "round_off_unit": None},
            "round_off",
        ),
        ({"paid": Decimal(-1)}, "paid"),
        ({"paid": Decimal(150)}, "paid|open_status"),
        ({"paid": Decimal(100)}, "open_status"),
        ({"status": "paid", "paid": Decimal(50)}, "paid_status"),
        ({"status": "cancelled", "cancelled_at": utcnow()}, "cancelled"),
        ({"status": "cancelled", "cancel_reason": "Wrong patient"}, "cancelled"),
    ],
)
def test_bill_db_checks(seeded: Session, changes: dict[str, Any], constraint: str) -> None:
    _, _, visit, _ = _visit(seeded)
    with pytest.raises(IntegrityError, match=rf"ck_bill_({constraint})\b"), seeded.begin_nested():
        _bill(seeded, visit, **changes)


@pytest.mark.item("EC-B04")
def test_net_zero_bill_is_issued_paid(seeded: Session) -> None:
    _, _, visit, _ = _visit(seeded)
    zero = {"gross": Decimal(0), "net": Decimal(0)}
    with pytest.raises(IntegrityError, match="ck_bill_open_status"), seeded.begin_nested():
        _bill(seeded, visit, **zero)
    assert _bill(seeded, visit, status="paid", **zero).due == 0


@pytest.mark.item("EC-B04")
def test_one_live_bill_per_visit(seeded: Session) -> None:
    _, _, visit, _ = _visit(seeded)
    _bill(seeded, visit)
    with pytest.raises(IntegrityError, match="uq_bill_visit_doc_type"), seeded.begin_nested():
        _bill(seeded, visit)


@pytest.mark.item("EC-B04")
@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        ("update bill_line set amount = 0", "ck_bill_line_amount"),
        ("update order_item set reason = '' where item_type = 'extra_charge'", "extra_charge"),
        ("update order_item set net_price = 1", "ck_order_item_net_price"),
        ("update patient set phone = '12345'", "ck_patient_phone"),
        ("update patient set full_name = '  '", "ck_patient_full_name"),
    ],
)
def test_order_and_patient_checks(
    seeded: Session, issued: tuple[Bill, BillLine, Payment, Refund], statement: str, constraint: str
) -> None:
    # Lines refuse every update outright, so their CHECKs are tried on insert instead.
    if statement.startswith("update bill_line"):
        bill, line, _, _ = issued
        bad = BillLine(
            bill_id=bill.id,
            order_item_id=line.order_item_id,
            line_no=2,
            description="Home collection",
            rate=Decimal(100),
            discount=Decimal(0),
            amount=Decimal(0),
        )
        with pytest.raises(IntegrityError, match=constraint), seeded.begin_nested():
            seeded.add(bad)
            seeded.flush()
        return
    with pytest.raises(IntegrityError, match=constraint), seeded.begin_nested():
        seeded.execute(text(statement))


@pytest.mark.item("EC-B05")
@pytest.mark.parametrize(
    "statement",
    [
        "update bill set net = 90, gross = 90",
        'update bill set print_snapshot = \'{"lab": "Other"}\'',
        "update bill set bill_no = 'B2/2627/99999'",
        "update bill set recipient_name = 'Someone Else'",
        "update bill set bill_date = bill_date + 1",
        "update bill set discount_reason = 'Later'",
    ],
)
def test_issued_bill_amounts_cannot_change(
    seeded: Session, issued: tuple[Bill, BillLine, Payment, Refund], statement: str
) -> None:
    with pytest.raises(DBAPIError, match="is issued"), seeded.begin_nested():
        seeded.execute(text(statement))


@pytest.mark.item("EC-B05")
def test_payments_only_add_to_a_bill(
    seeded: Session, issued: tuple[Bill, BillLine, Payment, Refund]
) -> None:
    bill = issued[0]
    with pytest.raises(DBAPIError, match="less paid"), seeded.begin_nested():
        seeded.execute(text("update bill set paid = 10 where id = :id"), {"id": bill.id})
    seeded.execute(
        text("update bill set paid = 100, status = 'paid' where id = :id"), {"id": bill.id}
    )
    assert seeded.scalar(text("select due from bill where id = :id"), {"id": bill.id}) == 0


@pytest.mark.item("EC-B05")
@pytest.mark.parametrize("table", ["bill_line", "payment", "refund"])
@pytest.mark.parametrize("statement", ["update {t} set created_by = null", "delete from {t}"])
def test_bill_line_payment_refund_append_only(
    seeded: Session, issued: tuple[Bill, BillLine, Payment, Refund], table: str, statement: str
) -> None:
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(text(statement.format(t=table)))


@pytest.mark.item("EC-B05")
@pytest.mark.parametrize("table", ["bill_line", "payment", "refund", "bill"])
def test_money_tables_cannot_be_truncated(
    seeded: Session, issued: tuple[Bill, BillLine, Payment, Refund], table: str
) -> None:
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(text(f"truncate {table} cascade"))


@pytest.mark.item("EC-B05")
def test_bill_cannot_be_deleted(
    seeded: Session, issued: tuple[Bill, BillLine, Payment, Refund]
) -> None:
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(text("delete from bill"))


@pytest.mark.item("EC-B05")
def test_cancelled_bill_is_final(
    seeded: Session, issued: tuple[Bill, BillLine, Payment, Refund]
) -> None:
    bill = issued[0]
    seeded.execute(
        text(
            "update bill set status = 'cancelled', cancel_reason = 'Wrong patient',"
            " cancelled_at = now() where id = :id"
        ),
        {"id": bill.id},
    )
    for statement in (
        "update bill set status = 'open'",
        "update bill set cancel_reason = 'Other'",
        "update bill set paid = 100",
    ):
        with pytest.raises(DBAPIError, match="is cancelled"), seeded.begin_nested():
            seeded.execute(text(statement))
