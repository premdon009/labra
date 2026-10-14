"""The owner's figures (design §13, M13): a day's collection, bills, cancellations and dues,
what went to outside labs and what it earned, and the tests still pending.

Every figure is limited to the branches where the user holds `owner.reports`, and a branch's
figures are its own: money taken at its counter, its bills, and the tests of its visits
wherever they were done. The accounting export computes the same figures here, so the
screen and the file always agree.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.billing.models import PAYMENT_MODES, Bill, Payment, Refund
from labra.catalog.models import Test
from labra.core.errors import NotFoundError
from labra.core.ids import IST, utcnow
from labra.core.money import PAISA, ZERO
from labra.core.paging import Page, page_of
from labra.extlabs.models import ExternalLab
from labra.org.models import Branch
from labra.patients.models import Patient
from labra.results.models import OrderTestEvent
from labra.results.worklist import charged_for
from labra.visits.models import OrderItem, OrderTest, Visit

PERMISSION = "owner.reports"
# Tests that still need work: not yet verified, released or cancelled.
DONE = ("verified", "released", "cancelled")


@dataclass(frozen=True)
class BranchChoice:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class Collection:
    """Money taken at one branch on the day, by mode, less the refunds paid out there."""

    branch: str
    modes: dict[str, Decimal]
    refunds: Decimal

    @property
    def taken(self) -> Decimal:
        return sum(self.modes.values(), ZERO)

    @property
    def net(self) -> Decimal:
        return self.taken - self.refunds


@dataclass(frozen=True)
class Margin:
    tests: int
    cost: Decimal
    revenue: Decimal

    @property
    def margin(self) -> Decimal:
        return self.revenue - self.cost

    @property
    def percent(self) -> Decimal | None:
        """The margin as a share of what the patients paid, to one decimal place."""
        if not self.revenue:
            return None
        return (self.margin * 100 / self.revenue).quantize(Decimal("0.1"))


@dataclass(frozen=True)
class Daily:
    day: date
    branch_id: uuid.UUID | None
    branches: list[BranchChoice]
    collection: list[Collection]
    total: Collection
    bills: int
    gross: Decimal
    discount: Decimal
    net: Decimal
    cancelled: int
    cancelled_net: Decimal
    dues_bills: int
    dues: Decimal
    outsourced: Margin
    pending: int
    overdue: int
    modes: tuple[str, ...] = field(default=PAYMENT_MODES)


def branch_choices(db: Session, principal: Principal) -> list[BranchChoice]:
    allowed = principal.branches_with(PERMISSION)
    return [
        BranchChoice(i, name)
        for i, name in db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_(allowed)).order_by(Branch.name)
        )
    ]


def scope(principal: Principal, branch_id: uuid.UUID | None) -> set[uuid.UUID]:
    """The branches to count: the one asked for, or every branch the user may see."""
    allowed = principal.branches_with(PERMISSION)
    if branch_id is None:
        return allowed
    if branch_id not in allowed:
        raise NotFoundError()
    return {branch_id}


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """The lab day runs from IST midnight to IST midnight."""
    start = datetime.combine(day, time.min, tzinfo=IST)
    return start, start + timedelta(days=1)


def _sum(column: Any) -> Any:
    return func.coalesce(func.sum(column), ZERO)


def _collection(
    db: Session, branches: list[BranchChoice], start: datetime, end: datetime
) -> list[Collection]:
    ids = [b.id for b in branches]
    taken: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(dict)
    for branch_id, mode, amount in db.execute(
        select(Payment.branch_id, Payment.mode, _sum(Payment.amount))
        .where(Payment.branch_id.in_(ids), Payment.received_at >= start, Payment.received_at < end)
        .group_by(Payment.branch_id, Payment.mode)
    ):
        taken[branch_id][mode] = amount
    refunded = dict(
        db.execute(
            select(Refund.branch_id, _sum(Refund.amount))
            .where(Refund.branch_id.in_(ids), Refund.refunded_at >= start, Refund.refunded_at < end)
            .group_by(Refund.branch_id)
        ).all()
    )
    return [
        Collection(
            b.name,
            {m: taken[b.id].get(m, ZERO) for m in PAYMENT_MODES},
            refunded.get(b.id, ZERO),
        )
        for b in branches
    ]


def _dues_at(db: Session, ids: set[uuid.UUID], end: datetime) -> tuple[int, Decimal]:
    """Bills issued by the end of the day, not cancelled by then, and what was still owed on
    them at that moment."""
    paid = (
        select(_sum(Payment.amount))
        .where(Payment.bill_id == Bill.id, Payment.received_at < end)
        .scalar_subquery()
    )
    owed = (
        select((Bill.net - paid).label("owed"))
        .where(
            Bill.branch_id.in_(ids),
            Bill.issued_at < end,
            or_(Bill.cancelled_at.is_(None), Bill.cancelled_at >= end),
        )
        .subquery()
    )
    count, total = db.execute(select(func.count(), _sum(owed.c.owed)).where(owed.c.owed > 0)).one()
    return count, total


def revenue_of(db: Session, ordered: OrderTest, item: OrderItem) -> Decimal:
    """What the patient paid for the test: the item's price, or its share of a package's."""
    if item.item_type == "package":
        return charged_for(db, ordered)
    return item.net_price


def _sent(ids: set[uuid.UUID], start: datetime, end: datetime) -> Select[OrderTest, OrderItem]:
    """Tests sent to an outside lab between `start` and `end`, counted once however many
    times their samples went, and not since cancelled."""
    first_sent = (
        select(OrderTestEvent.order_test_id, func.min(OrderTestEvent.at).label("at"))
        .where(OrderTestEvent.event == "sent")
        .group_by(OrderTestEvent.order_test_id)
        .subquery()
    )
    return (
        select(OrderTest, OrderItem)
        .join(first_sent, first_sent.c.order_test_id == OrderTest.id)
        .join(OrderItem, OrderItem.id == OrderTest.order_item_id)
        .join(Visit, Visit.id == OrderTest.visit_id)
        .where(
            Visit.branch_id.in_(ids),
            OrderTest.route == "external",
            OrderTest.status != "cancelled",
            first_sent.c.at >= start,
            first_sent.c.at < end,
        )
        .order_by(OrderTest.id)
    )


def _margin(db: Session, rows: list[tuple[OrderTest, OrderItem]]) -> Margin:
    cost = sum((o.external_cost or ZERO for o, _ in rows), ZERO)
    revenue = sum((revenue_of(db, o, i) for o, i in rows), ZERO)
    return Margin(len(rows), cost, revenue)


def _pending(ids: set[uuid.UUID]) -> Select[OrderTest]:
    return (
        select(OrderTest)
        .join(Visit, Visit.id == OrderTest.visit_id)
        .where(Visit.branch_id.in_(ids), OrderTest.status.not_in(DONE))
    )


def daily(
    db: Session, principal: Principal, day: date, branch_id: uuid.UUID | None = None
) -> Daily:
    ids = scope(principal, branch_id)
    branches = branch_choices(db, principal)
    counted = [b for b in branches if b.id in ids]
    start, end = day_bounds(day)
    collection = _collection(db, counted, start, end)
    total = Collection(
        "All branches",
        {m: sum((c.modes[m] for c in collection), ZERO) for m in PAYMENT_MODES},
        sum((c.refunds for c in collection), ZERO),
    )
    bills, gross, discount, net = db.execute(
        select(func.count(), _sum(Bill.gross), _sum(Bill.discount), _sum(Bill.net)).where(
            Bill.branch_id.in_(ids), Bill.bill_date == day
        )
    ).one()
    cancelled, cancelled_net = db.execute(
        select(func.count(), _sum(Bill.net)).where(
            Bill.branch_id.in_(ids), Bill.cancelled_at >= start, Bill.cancelled_at < end
        )
    ).one()
    dues_bills, dues = _dues_at(db, ids, end)
    sent = [(o, i) for o, i in db.execute(_sent(ids, start, end)).tuples()]
    waiting_tests = _pending(ids).subquery()
    waiting, late = db.execute(
        select(func.count(), func.count().filter(waiting_tests.c.due_at < utcnow())).select_from(
            waiting_tests
        )
    ).one()
    return Daily(
        day=day,
        branch_id=branch_id,
        branches=branches,
        collection=collection,
        total=total,
        bills=bills,
        gross=gross,
        discount=discount,
        net=net,
        cancelled=cancelled,
        cancelled_net=cancelled_net,
        dues_bills=dues_bills,
        dues=dues.quantize(PAISA),
        outsourced=_margin(db, sent),
        pending=waiting,
        overdue=late,
    )


@dataclass(frozen=True)
class PendingLine:
    order_test_id: uuid.UUID
    visit_id: uuid.UUID
    visit_no: str
    patient: str
    test: str
    status: str
    branch: str
    due_at: datetime
    overdue: bool


def pending(
    db: Session, principal: Principal, page: int, branch_id: uuid.UUID | None = None
) -> Page[PendingLine]:
    """Tests still being worked on, the overdue ones first, then by when they are due."""
    ids = scope(principal, branch_id)
    now = utcnow()
    stmt = (
        select(OrderTest, Visit.visit_no, Patient.full_name, Test.name, Branch.name)
        .join(Visit, Visit.id == OrderTest.visit_id)
        .join(Patient, Patient.id == Visit.patient_id)
        .join(Test, Test.id == OrderTest.test_id)
        .join(Branch, Branch.id == OrderTest.perform_branch_id)
        .where(Visit.branch_id.in_(ids), OrderTest.status.not_in(DONE))
        .order_by(OrderTest.due_at, OrderTest.id)
    )
    found = page_of(db, stmt, page)
    lines = [
        PendingLine(
            o.id, o.visit_id, visit_no, patient, test, o.status, branch, o.due_at, o.due_at < now
        )
        for o, visit_no, patient, test, branch in found.items
    ]
    return Page(lines, found.number, found.size, found.has_next)


@dataclass(frozen=True)
class LabMargin:
    lab: str
    figures: Margin


def outsourcing(
    db: Session,
    principal: Principal,
    start_day: date,
    end_day: date,
    branch_id: uuid.UUID | None = None,
) -> tuple[list[LabMargin], Margin]:
    """Tests sent out between the two days (both included), by outside lab, with the total."""
    ids = scope(principal, branch_id)
    start, _ = day_bounds(start_day)
    _, end = day_bounds(end_day)
    by_lab: dict[uuid.UUID, list[tuple[OrderTest, OrderItem]]] = defaultdict(list)
    for ordered, item in db.execute(_sent(ids, start, end)).tuples():
        if ordered.external_lab_id is not None:
            by_lab[ordered.external_lab_id].append((ordered, item))
    names = dict(
        db.execute(select(ExternalLab.id, ExternalLab.name).where(ExternalLab.id.in_(by_lab))).all()
    )
    lines = sorted(
        (LabMargin(names[lab_id], _margin(db, rows)) for lab_id, rows in by_lab.items()),
        key=lambda line: line.lab,
    )
    total = Margin(
        sum(line.figures.tests for line in lines),
        sum((line.figures.cost for line in lines), ZERO),
        sum((line.figures.revenue for line in lines), ZERO),
    )
    return lines, total
