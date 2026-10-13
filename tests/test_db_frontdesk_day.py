"""One front-desk day on the demo data, through the screens: find the patient, order,
bill, label, collect, and take the balance."""

import re
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.billing.models import Bill
from labra.catalog.models import Test
from labra.core.registry import Platform
from labra.patients.models import Patient, Referrer
from labra.seed import seed
from labra.visits.models import Sample, Visit
from tests.frontdesk import post, sign_in

UTR = "426112345678"


@pytest.mark.item("M18")
@pytest.mark.item("M07")
@pytest.mark.item("M08")
@pytest.mark.item("M23")
@pytest.mark.item("M26")
def test_front_desk_day_on_the_demo_data(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    seed(seeded, platform.identity, date(2026, 10, 9), with_catalog=True, with_people=True)
    patient = seeded.scalars(select(Patient).where(Patient.phone == "9000000001")).one()
    referrer = seeded.scalars(select(Referrer).where(Referrer.council_reg_no == "DEMO-0001")).one()
    tests = {t.code: t.id for t in seeded.scalars(select(Test))}
    sign_in(db_client, "priya")

    # The phone finds the patient; each code or alias finds its test and its price.
    match = db_client.get("/frontdesk/visits/new/patient", params={"phone": patient.phone}).text
    assert f'href="/frontdesk/visits/new?patient_id={patient.id}"' in match
    for typed, code, price in (
        ("sf", "fbs", "₹80.00"),
        ("lipid", "lipid", "₹500.00"),
        ("urm", "urine", "₹150.00"),
        ("vitd", "vitd", "₹1,200.00"),
    ):
        hits = db_client.get("/frontdesk/visits/new/tests", params={"q": typed}).text
        first = hits.split("</li>")[0]
        assert f'"arg": "test:{tests[code]}"' in first and price in first
    assert "outsourced ★" in first

    form: dict[str, object] = {
        "client_ref": str(uuid.uuid4()),
        "patient_id": str(patient.id),
        "referrer_id": str(referrer.id),
        "consent": "true",
        "item": [f"test:{tests[code]}" for code in ("fbs", "lipid", "urine", "vitd")],
        "discount_value": "10",
        "discount_kind": "pct",
        "discount_reason": "Senior citizen",
        "pay_mode": "upi",
        "pay_amount": "1000",
        "pay_reference": UTR,
    }
    preview = post(db_client, "/frontdesk/visits/new/preview", form).text
    assert 'id="visit-net">₹1,737.00<' in preview and "-₹193.00" in preview

    saved = post(db_client, "/frontdesk/visits", form)
    assert saved.status_code == 303, saved.text
    visit_id = uuid.UUID(saved.headers["location"].split("/")[-1].split("?")[0])
    visit = seeded.get_one(Visit, visit_id)
    bill = seeded.scalars(select(Bill).where(Bill.visit_id == visit.id)).one()
    assert (bill.gross, bill.discount, bill.net, bill.paid) == (
        Decimal(1930),
        Decimal(193),
        Decimal(1737),
        Decimal(1000),
    )

    summary = db_client.get(f"/frontdesk/visits/{visit.id}").text
    assert "₹1,737.00" in summary and 'id="bill-due">₹737.00<' in summary
    assert f"Referred by {referrer.name}" in summary
    printed = db_client.get(f"/frontdesk/bills/{bill.id}/print").text
    assert "Bill of Supply" in printed and "999316" in printed and UTR in printed
    assert f"Referred by: {referrer.name}" in printed
    labels = db_client.get(f"/frontdesk/visits/{visit.id}/labels").text
    assert labels.count('<section class="label"') == 3 and "Container not set" not in labels

    samples = seeded.scalars(select(Sample).where(Sample.visit_id == visit.id)).all()
    for tube in samples:
        scan = {"sample_no": tube.sample_no, "collected_by": str(visit.created_by)}
        assert post(db_client, "/frontdesk/collect", scan).status_code == 303
    seeded.expire_all()
    assert {s.status for s in samples} == {"collected"}

    dues = db_client.get("/frontdesk/dues").text
    assert bill.bill_no in dues and ">737.00<" in dues
    pay = db_client.get(f"/frontdesk/bills/{bill.id}/pay").text
    ref = re.search(r'name="client_ref" value="([^"]+)"', pay)
    assert ref is not None
    paid = post(
        db_client,
        f"/frontdesk/bills/{bill.id}/pay",
        {"client_ref": ref.group(1), "mode": "cash", "amount": "737", "reference": ""},
    )
    assert paid.status_code == 303, paid.text
    seeded.refresh(bill)
    assert (bill.paid, bill.status) == (Decimal(1737), "paid")
    assert bill.bill_no not in db_client.get("/frontdesk/dues").text
