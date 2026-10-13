"""Saving a visit: the order, its samples and bill, consent, and saving the same form twice."""

import threading
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from labra.billing.models import Bill, BillLine, Payment
from labra.billing.service import PaymentInput
from labra.core.consent import publish_notice
from labra.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from labra.core.models import AuditLog, Consent
from labra.core.registry import Platform
from labra.patients.models import Patient
from labra.seed import seed
from labra.visits import service
from labra.visits.models import OrderItem, OrderTest, Sample, Visit
from labra.visits.service import ChargeInput
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, menu, visit_input

UTR = "426112345678"


def _count(db: Session, model: type, visit: Visit) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.visit_id == visit.id)) or 0


def _problems(db: Session, principal, data: service.VisitInput) -> dict[str, str]:
    with pytest.raises(ValidationFailedError) as refused:
        service.save_visit(db, principal, data, SEED_DAY)
    return refused.value.errors


@pytest.mark.item("M07")
@pytest.mark.item("M18")
@pytest.mark.item("M08")
@pytest.mark.item("M07.2")
def test_save_visit_issues_bill_receipt_samples(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")
    data = visit_input(
        ids,
        "fbs",
        "lipid",
        "urine",
        "vitd",
        discount_kind="pct",
        discount_value="10",
        discount_reason="Senior citizen",
        payment=PaymentInput("upi", Decimal(1000), UTR),
    )

    visit = service.save_visit(seeded, priya, data, SEED_DAY)

    patient = seeded.get_one(Patient, visit.patient_id)
    assert patient.patient_no.startswith("B2/P/")
    assert visit.visit_no.startswith("B2/") and visit.status == "open"
    bill = seeded.scalars(select(Bill).where(Bill.visit_id == visit.id)).one()
    assert (bill.gross, bill.discount, bill.net) == (Decimal(1930), Decimal(193), Decimal(1737))
    assert (bill.paid, bill.due, bill.status) == (Decimal(1000), Decimal(737), "open")
    assert bill.discount_reason == "Senior citizen"
    lines = seeded.scalars(
        select(BillLine).where(BillLine.bill_id == bill.id).order_by(BillLine.line_no)
    ).all()
    assert [ln.rate for ln in lines] == [Decimal(80), Decimal(450), Decimal(100), Decimal(1300)]
    assert sum(ln.discount for ln in lines) == Decimal(193)
    assert all(ln.price_id is not None for ln in lines)
    payment = seeded.scalars(select(Payment).where(Payment.bill_id == bill.id)).one()
    assert (payment.mode, payment.reference, payment.patient_id) == ("upi", UTR, patient.id)

    # Four tests, three tubes: lipid and vitamin D share the serum sample.
    samples = seeded.scalars(select(Sample).where(Sample.visit_id == visit.id)).all()
    assert sorted(s.container for s in samples) == ["Grey top", "Red top", "Urine cup"]
    assert all(s.status == "pending" for s in samples)
    assert sorted(bill.print_snapshot["sample_nos"]) == sorted(s.sample_no for s in samples)
    tests = seeded.scalars(select(OrderTest).where(OrderTest.visit_id == visit.id)).all()
    assert len(tests) == 4 and all(t.sample_id is not None for t in tests)
    serum = next(s for s in samples if s.container == "Red top")
    assert {t.test_id for t in tests if t.sample_id == serum.id} == {ids["lipid"], ids["vitd"]}

    actions = [
        row.action
        for row in seeded.scalars(select(AuditLog).order_by(AuditLog.id))
        if row.entity_id in {str(visit.id), str(patient.id), str(bill.id), str(payment.id)}
    ]
    # In the order things happened at the counter: the bill belongs to the visit.
    assert actions == ["patient.create", "visit.create", "bill.issue", "payment.receive"]


@pytest.mark.item("M18")
def test_promised_time_defaults_to_latest_tat(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")

    visit = service.save_visit(seeded, priya, visit_input(ids, "fbs", "vitd"), SEED_DAY)

    due = dict(
        seeded.execute(
            select(OrderTest.test_id, OrderTest.due_at).where(OrderTest.visit_id == visit.id)
        ).all()
    )
    assert due[ids["fbs"]] == visit.visited_at + timedelta(hours=6)
    assert due[ids["vitd"]] == visit.visited_at + timedelta(hours=72)
    assert visit.promised_at == due[ids["vitd"]]

    # The counter can promise another time, but not one already past.
    later = visit.visited_at + timedelta(days=5)
    kept = service.save_visit(seeded, priya, visit_input(ids, "fbs", promised_at=later), SEED_DAY)
    assert kept.promised_at == later
    past = visit_input(ids, "fbs", promised_at=visit.visited_at - timedelta(hours=1))
    assert "promised_at" in _problems(seeded, priya, past)


@pytest.mark.item("M07")
def test_package_expands_to_order_tests(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")

    visit = service.save_visit(seeded, priya, visit_input(ids, "basic", "urine"), SEED_DAY)

    items = seeded.scalars(select(OrderItem).where(OrderItem.visit_id == visit.id)).all()
    assert sorted((i.item_type, i.list_price) for i in items) == [
        ("package", Decimal(500)),
        ("test", Decimal(100)),
    ]
    package = next(i for i in items if i.item_type == "package")
    tests = seeded.scalars(select(OrderTest).where(OrderTest.visit_id == visit.id)).all()
    assert {t.test_id for t in tests if t.order_item_id == package.id} == {
        ids["fbs"],
        ids["lipid"],
    }
    assert len(tests) == 3
    assert seeded.scalars(select(Bill.net).where(Bill.visit_id == visit.id)).one() == Decimal(600)


@pytest.mark.item("M07")
def test_duplicate_test_in_visit_refused(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")

    twice = _problems(seeded, priya, visit_input(ids, "fbs", "fbs"))
    assert twice["items"] == "Glucose, fasting is already on this visit."
    in_package = _problems(seeded, priya, visit_input(ids, "basic", "lipid"))
    assert in_package["items"] == "Lipid profile is already on this visit."

    # The database refuses it too, whatever the code above it does.
    visit = service.save_visit(seeded, priya, visit_input(ids, "fbs"), SEED_DAY)
    first = seeded.scalars(select(OrderTest).where(OrderTest.visit_id == visit.id)).one()
    again = OrderTest(
        visit_id=visit.id,
        order_item_id=first.order_item_id,
        test_id=first.test_id,
        due_at=first.due_at,
    )
    with pytest.raises(IntegrityError, match="uq_order_test_visit_test"), seeded.begin_nested():
        seeded.add(again)
        seeded.flush()


@pytest.mark.item("M07")
def test_unpriced_or_retired_items_are_refused(seeded: Session, platform: Platform) -> None:
    admin = as_user(seeded, platform, "anil")
    ids = menu(seeded, admin)
    priya = as_user(seeded, platform, "priya")
    seeded.execute(text("update test set is_active = false where code = 'urine'"))
    seeded.execute(text("delete from price where item_id = :id"), {"id": ids["lipid"]})
    seeded.expire_all()

    assert "no longer in use" in _problems(seeded, priya, visit_input(ids, "urine"))["items"]
    assert "has no price" in _problems(seeded, priya, visit_input(ids, "lipid"))["items"]
    assert "Add at least one" in _problems(seeded, priya, visit_input(ids))["items"]


@pytest.mark.item("M18")
@pytest.mark.item("M07")
def test_extra_charge_without_reason_refused(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")

    for charge in (
        ChargeInput("Home collection", "100", ""),
        ChargeInput("", "100", "Patient asked"),
        ChargeInput("Home collection", "0", "Patient asked"),
        ChargeInput("Home collection", "abc", "Patient asked"),
    ):
        assert "charge" in _problems(seeded, priya, visit_input(ids, "fbs", charges=[charge]))

    charge = ChargeInput("Home collection", "100", "Patient asked")
    half = {"discount_kind": "pct", "discount_value": "50", "discount_reason": "Staff"}
    data = visit_input(ids, "fbs", charges=[charge], **half)
    visit = service.save_visit(seeded, priya, data, SEED_DAY)
    items = seeded.scalars(select(OrderItem).where(OrderItem.visit_id == visit.id)).all()
    extra = next(i for i in items if i.item_type == "extra_charge")
    # A discount comes off tests and packages, never off an extra charge.
    assert (extra.reason, extra.list_price, extra.discount_amt) == (
        "Patient asked",
        Decimal(100),
        Decimal(0),
    )
    assert seeded.scalars(select(Bill.net).where(Bill.visit_id == visit.id)).one() == Decimal(140)


@pytest.mark.item("M18")
@pytest.mark.item("M07")
def test_discount_without_reason_refused(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")

    no_reason = visit_input(ids, "lipid", discount_value="50")
    assert _problems(seeded, priya, no_reason) == {
        "discount_reason": "Give the reason for the discount."
    }
    for kind, value in (("amount", "451"), ("pct", "101"), ("amount", "-5"), ("amount", "ten")):
        bad = visit_input(
            ids, "lipid", discount_kind=kind, discount_value=value, discount_reason="Camp"
        )
        assert "discount" in _problems(seeded, priya, bad)
    assert seeded.scalar(select(func.count()).select_from(Visit)) == 0


@pytest.mark.item("M07")
def test_payment_problems_are_caught_before_anything_is_saved(
    seeded: Session, platform: Platform
) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")

    too_much = visit_input(ids, "fbs", payment=PaymentInput("cash", Decimal(81)))
    assert _problems(seeded, priya, too_much) == {
        "amount": "The payment is more than the amount due."
    }
    no_utr = visit_input(ids, "fbs", payment=PaymentInput("upi", Decimal(80)))
    assert "reference" in _problems(seeded, priya, no_utr)
    assert seeded.scalar(select(func.count()).select_from(Patient)) == 0


@pytest.mark.item("EC-C01")
def test_visit_refused_without_consent(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")

    assert "consent" in _problems(seeded, priya, visit_input(ids, "fbs", consent=False))
    assert seeded.scalar(select(func.count()).select_from(Consent)) == 0

    visit = service.save_visit(seeded, priya, visit_input(ids, "fbs"), SEED_DAY)
    rows = seeded.scalars(select(Consent).where(Consent.subject_id == visit.patient_id)).all()
    assert sorted(r.purpose for r in rows) == ["referral_lab_sharing", "testing"]
    assert {(r.subject_type, r.method, r.recorded_by) for r in rows} == {
        ("patient", "counter", priya.user_id)
    }
    assert {r.notice_id for r in rows} == {service.current_notice(seeded).id}

    # With consent on file, the next visit needs no tick and records nothing new.
    again = visit_input(ids, "urine", patient=None, patient_id=visit.patient_id, consent=False)
    service.save_visit(seeded, priya, again, SEED_DAY)
    assert seeded.scalar(select(func.count()).select_from(Consent)) == 2


@pytest.mark.item("EC-C01")
def test_new_notice_version_needs_new_tick(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")
    visit = service.save_visit(seeded, priya, visit_input(ids, "fbs"), SEED_DAY)
    returning = {"patient": None, "patient_id": visit.patient_id}

    notice = publish_notice(seeded, "Synthetic notice, second version.")
    assert service.consent_on_file(seeded, visit.patient_id, notice) is None
    assert "consent" in _problems(
        seeded, priya, visit_input(ids, "urine", consent=False, **returning)
    )

    service.save_visit(seeded, priya, visit_input(ids, "urine", **returning), SEED_DAY)
    on_file = service.consent_on_file(seeded, visit.patient_id, notice)
    assert on_file is not None and on_file.notice_id == notice.id

    # A withdrawn consent no longer counts.
    seeded.execute(text("update consent set withdrawn_at = now()"))
    seeded.expire_all()
    assert service.consent_on_file(seeded, visit.patient_id, notice) is None


@pytest.mark.item("EC-B07")
def test_same_client_ref_gives_one_visit_and_bill(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")
    data = visit_input(ids, "fbs", payment=PaymentInput("cash", Decimal(80)))

    first = service.save_visit(seeded, priya, data, SEED_DAY)
    second = service.save_visit(seeded, priya, data, SEED_DAY)

    assert second.id == first.id
    for model in (Visit, Bill, Payment, Patient):
        assert seeded.scalar(select(func.count()).select_from(model)) == 1
    # Another branch's user who sends the same reference learns nothing about the visit.
    with pytest.raises(NotFoundError):
        service.save_visit(seeded, as_user(seeded, platform, "b3desk"), data, SEED_DAY)


@pytest.mark.item("EC-B07")
def test_concurrent_client_ref_one_visit(committed_engine: Engine, platform: Platform) -> None:
    with Session(committed_engine) as setup:
        seed(setup, platform.identity, SEED_DAY)
        ids = menu(setup, as_user(setup, platform, "anil"))
        priya = as_user(setup, platform, "priya")
        setup.commit()
    data = visit_input(ids, "fbs", "lipid", payment=PaymentInput("cash", Decimal(530)))
    start = threading.Barrier(2)
    saved: list[uuid.UUID] = []
    failed: list[BaseException] = []

    def save() -> None:
        try:
            with Session(committed_engine) as session:
                start.wait(timeout=30)
                saved.append(service.save_visit(session, priya, data, SEED_DAY).id)
                session.commit()
        except BaseException as exc:  # noqa: BLE001  reported by the assert below
            failed.append(exc)

    threads = [threading.Thread(target=save) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert failed == []
    assert len(saved) == 2 and saved[0] == saved[1]
    with Session(committed_engine) as check:
        for model in (Visit, Bill, Payment, Patient):
            assert check.scalar(select(func.count()).select_from(model)) == 1
        assert check.scalar(select(func.count()).select_from(Sample)) == 2


@pytest.mark.item("M18")
@pytest.mark.item("EC-A05")
def test_visits_are_saved_at_the_users_branch_only(seeded: Session, platform: Platform) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")
    visit = service.save_visit(seeded, priya, visit_input(ids, "fbs"), SEED_DAY)

    with pytest.raises(PermissionDeniedError):
        service.save_visit(
            seeded, as_user(seeded, platform, "suresh"), visit_input(ids, "fbs"), SEED_DAY
        )
    b3desk = as_user(seeded, platform, "b3desk")
    with pytest.raises(NotFoundError):
        service.visit_summary(seeded, b3desk, visit.id)
    # A patient known only at B2 can't be booked at B3 by id.
    with pytest.raises(NotFoundError):
        service.save_visit(
            seeded,
            b3desk,
            visit_input(ids, "fbs", patient=None, patient_id=visit.patient_id),
            SEED_DAY,
        )
    summary = service.visit_summary(seeded, priya, visit.id)
    assert summary.bill is not None and summary.bill.net == Decimal(80)
    assert [t.code for _, t in summary.tests] == ["fbs"]
    assert _count(seeded, Sample, visit) == 1


@pytest.mark.item("M18")
def test_test_line_shows_outsourced_marker_in_search(seeded: Session, platform: Platform) -> None:
    menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")

    hits = {h.code: h for h in service.find_items(seeded, priya, "vit")}
    assert hits["vitd"].in_house is False and hits["vitd"].price == Decimal(1300)
    # An alias typed exactly comes first, so Enter adds it.
    first = service.find_items(seeded, priya, "sf")[0]
    assert (first.code, first.in_house) == ("fbs", True)
    assert service.find_items(seeded, priya, "basic")[0].in_house is None
