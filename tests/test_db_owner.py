"""The owner's figures (design §13): a day's collection by branch and mode, bills,
cancellations and what was owed at the end of the day, outsourcing margin, and pending
tests, each limited to the branches where the user holds owner.reports."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.billing import service as billing
from labra.billing.models import Bill
from labra.billing.service import PaymentInput
from labra.core.errors import NotFoundError
from labra.core.ids import lab_today, utcnow
from labra.core.registry import Platform
from labra.owner import service as owner
from labra.visits import service as visits
from labra.visits.models import OrderTest, Visit
from tests.frontdesk import as_user, branch, sign_in, visit_input
from tests.test_db_lab_outsourcing import LAB_NAME, _sent
from tests.test_db_lab_routing import _ids


def _visit(db: Session, platform: Platform, username: str, *codes: str, paid: str = "") -> Visit:
    payment = PaymentInput("cash", Decimal(paid)) if paid else None
    data = visit_input(_ids(db, platform), *codes, payment=payment)
    return visits.save_visit(db, as_user(db, platform, username), data, lab_today())


def _bill(db: Session, visit: Visit) -> Bill:
    return db.scalars(select(Bill).where(Bill.visit_id == visit.id)).one()


def _day(db: Session, platform: Platform) -> dict[str, Visit]:
    """At Branch 2: lipid (₹450) paid ₹200 cash and ₹250 card; fasting sugar and urine
    (₹180) paid by UPI, then cancelled and refunded in cash; vitamin D (₹1300) sent out at
    ₹700, unpaid. At Branch 3: fasting sugar paid ₹80 cash."""
    priya, anil = as_user(db, platform, "priya"), as_user(db, platform, "anil")
    lipid = _visit(db, platform, "priya", "lipid", paid="200")
    billing.take_payment(
        db, priya, _bill(db, lipid).id, PaymentInput("card", Decimal(250), "4242"), uuid.uuid4()
    )
    sugar = visits.save_visit(
        db,
        priya,
        visit_input(
            _ids(db, platform),
            "fbs",
            "urine",
            payment=PaymentInput("upi", Decimal(180), "UTR12345678"),
        ),
        lab_today(),
    )
    bill = _bill(db, sugar)
    billing.cancel_bill(db, anil, bill.id, "Patient left", True, bill.row_version)
    vitd, _, _ = _sent(db, platform)
    centre = _visit(db, platform, "b3desk", "fbs", paid="80")
    db.flush()
    return {"lipid": lipid, "sugar": sugar, "vitd": vitd, "centre": centre}


def _late(db: Session, visit: Visit) -> OrderTest:
    ordered = db.scalars(select(OrderTest).where(OrderTest.visit_id == visit.id)).one()
    ordered.due_at = utcnow() - timedelta(hours=1)
    db.flush()
    return ordered


@pytest.mark.item("M13")
def test_the_daily_figures(seeded: Session, platform: Platform) -> None:
    db = seeded
    made = _day(db, platform)
    _late(db, made["lipid"])
    anil = as_user(db, platform, "anil")

    d = owner.daily(db, anil, lab_today())

    rows = {c.branch: c for c in d.collection}
    b2, b3 = branch(db, "B2").name, branch(db, "B3").name
    assert rows[b2].modes == {"cash": Decimal(200), "upi": Decimal(180), "card": Decimal(250)}
    assert rows[b2].refunds == Decimal(180) and rows[b2].net == Decimal(450)
    assert rows[b3].modes["cash"] == Decimal(80) and rows[b3].net == Decimal(80)
    assert d.total.net == Decimal(530) and d.total.taken == Decimal(710)
    # The vitamin D bill was dated the seed day by its helper, so three bills today.
    assert (d.bills, d.gross, d.discount, d.net) == (3, Decimal(710), Decimal(0), Decimal(710))
    assert (d.cancelled, d.cancelled_net) == (1, Decimal(180))
    assert (d.dues_bills, d.dues) == (1, Decimal(1300))
    out = d.outsourced
    assert (out.tests, out.cost, out.revenue, out.margin) == (
        1,
        Decimal(700),
        Decimal(1300),
        Decimal(600),
    )
    assert out.percent == Decimal("46.2")
    # Lipid, vitamin D and the centre's sugar are still being worked on; lipid is late.
    assert (d.pending, d.overdue) == (3, 1)

    # Owed at the end of a day is what was owed then: yesterday nothing had been billed.
    before = owner.daily(db, anil, lab_today() - timedelta(days=1))
    assert (before.bills, before.dues_bills, before.dues, before.total.net) == (
        0,
        0,
        Decimal(0),
        Decimal(0),
    )
    assert before.outsourced.tests == 0

    # One branch only.
    alone = owner.daily(db, anil, lab_today(), branch(db, "B3").id)
    assert [c.branch for c in alone.collection] == [b3] and alone.bills == 1
    assert alone.outsourced.tests == 0 and alone.pending == 1


@pytest.mark.item("M13")
def test_a_branch_manager_sees_only_their_branch(seeded: Session, platform: Platform) -> None:
    db = seeded
    made = _day(db, platform)
    b3desk = as_user(db, platform, "b3desk")

    d = owner.daily(db, b3desk, lab_today())
    assert [c.branch for c in d.collection] == [branch(db, "B3").name]
    assert d.total.net == Decimal(80) and d.bills == 1 and d.dues == 0
    assert d.outsourced.tests == 0 and d.pending == 1
    with pytest.raises(NotFoundError):
        owner.daily(db, b3desk, lab_today(), branch(db, "B2").id)

    pending = owner.pending(db, b3desk, 1)
    assert [t.visit_id for t in pending.items] == [made["centre"].id]
    lines, total = owner.outsourcing(db, b3desk, lab_today(), lab_today())
    assert lines == [] and total.tests == 0


@pytest.mark.item("M13")
def test_pending_overdue_first_and_margin_by_outside_lab(
    seeded: Session, platform: Platform
) -> None:
    db = seeded
    made = _day(db, platform)
    late = _late(db, made["vitd"])
    anil = as_user(db, platform, "anil")

    pending = owner.pending(db, anil, 1)
    assert pending.items[0].order_test_id == late.id and pending.items[0].overdue
    assert not any(t.overdue for t in pending.items[1:])
    assert {t.visit_id for t in pending.items} == {
        made["lipid"].id,
        made["vitd"].id,
        made["centre"].id,
    }

    lines, total = owner.outsourcing(db, anil, lab_today() - timedelta(days=7), lab_today())
    assert [(line.lab, line.figures.tests) for line in lines] == [(LAB_NAME, 1)]
    assert total.margin == Decimal(600) and total.percent == Decimal("46.2")
    # Days before anything was sent count nothing.
    early = lab_today() - timedelta(days=3)
    assert owner.outsourcing(db, anil, early, early) == (
        [],
        owner.Margin(0, Decimal(0), Decimal(0)),
    )


@pytest.mark.item("M13")
def test_the_owner_screens(seeded: Session, platform: Platform, db_client: TestClient) -> None:
    db = seeded
    made = _day(db, platform)
    db.commit()

    sign_in(db_client, "anil")
    assert 'href="/owner/daily"' in db_client.get("/").text
    page = db_client.get("/owner/daily")
    assert page.status_code == 200
    assert "Collection" in page.text and "46.2%" in page.text
    dues = db_client.get("/owner/dues").text
    assert _bill(db, made["vitd"]).bill_no in dues
    assert _bill(db, made["lipid"]).bill_no not in dues
    assert made["lipid"].visit_no in db_client.get("/owner/pending").text
    assert LAB_NAME in db_client.get("/owner/outsourcing").text
    assert db_client.get("/owner/daily", params={"branch": "nonsense"}).status_code == 404

    sign_in(db_client, "b3desk")
    assert db_client.get("/owner/daily").status_code == 200
    b2 = str(branch(db, "B2").id)
    assert db_client.get("/owner/daily", params={"branch": b2}).status_code == 404
    assert made["vitd"].visit_no not in db_client.get("/owner/pending").text

    for username in ("priya", "suresh", "meera"):
        sign_in(db_client, username)
        assert 'href="/owner/daily"' not in db_client.get("/").text
        for path in ("/owner/daily", "/owner/dues", "/owner/pending", "/owner/outsourcing"):
            assert db_client.get(path).status_code == 403
