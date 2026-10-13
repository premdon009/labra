"""A front-desk user at one branch can't reach another branch's records by any URL."""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.billing.models import Payment
from labra.billing.service import PaymentInput
from labra.core.registry import Platform
from tests.frontdesk import as_user, billed, post, register, sign_in, visit_at


@pytest.mark.item("EC-A05")
@pytest.mark.item("M03")
def test_patients_of_another_branch_are_not_found(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    patient = register(seeded, as_user(seeded, platform, "priya"))
    edit = {
        "full_name": "Changed Testcase",
        "sex": "F",
        "age_years": "34",
        "patient_id": str(patient.id),
        "row_version": str(patient.row_version),
    }

    sign_in(db_client, "b3desk")
    assert "Sunita Testcase" not in db_client.get("/frontdesk/patients").text
    assert "Sunita Testcase" not in db_client.get("/frontdesk/patients?q=9000000001").text
    assert db_client.get(f"/frontdesk/patients/{patient.id}").status_code == 404
    assert post(db_client, "/frontdesk/patients", edit).status_code == 404
    seeded.refresh(patient)
    assert patient.full_name == "Sunita Testcase"

    # Once the patient has visited B3, B3 sees them.
    visit_at(seeded, patient, "B3")
    assert "Sunita Testcase" in db_client.get("/frontdesk/patients").text
    assert db_client.get(f"/frontdesk/patients/{patient.id}").status_code == 200


@pytest.mark.item("EC-A05")
def test_frontdesk_screens_need_a_frontdesk_role(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    sign_in(db_client, "suresh")
    home = db_client.get("/").text
    assert "/frontdesk/patients" not in home
    assert "/frontdesk/referrers" not in home
    for url in (
        "/frontdesk/patients",
        "/frontdesk/patients/new",
        "/frontdesk/referrers",
        "/frontdesk/referrers/new",
    ):
        assert db_client.get(url).status_code == 403
    assert post(db_client, "/frontdesk/patients", {"full_name": "X"}).status_code == 403
    assert post(db_client, "/frontdesk/referrers", {"name": "X"}).status_code == 403
    for url in (
        "/frontdesk/visits/new",
        "/frontdesk/visits/new/patient?phone=9000000001",
        "/frontdesk/visits/new/tests?q=fbs",
        "/frontdesk/referrers/pick",
        "/frontdesk/bills",
        "/frontdesk/dues",
        "/frontdesk/collect",
    ):
        assert db_client.get(url).status_code == 403
        assert f'href="{url}"' not in home
    assert post(db_client, "/frontdesk/collect", {"sample_no": "X"}).status_code == 403
    assert post(db_client, "/frontdesk/visits", {"full_name": "X"}).status_code == 403
    assert post(db_client, "/frontdesk/visits/new/preview", {"op": "code"}).status_code == 403
    assert post(db_client, "/frontdesk/referrers/quick", {"name": "X"}).status_code == 403
    sign_in(db_client, "priya")
    home = db_client.get("/").text
    assert 'href="/frontdesk/patients"' in home
    assert 'href="/frontdesk/referrers"' in home


@pytest.mark.item("EC-A05")
@pytest.mark.item("M07")
@pytest.mark.item("M18")
def test_visits_and_bills_of_another_branch_are_not_found(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    bill = billed(
        seeded, as_user(seeded, platform, "priya"), payment=PaymentInput("cash", Decimal(300))
    )
    payment = seeded.scalars(select(Payment).where(Payment.bill_id == bill.id)).one()
    cancel = {"reason": "Entered twice", "confirm": "yes", "row_version": str(bill.row_version)}
    pay = {"client_ref": str(uuid.uuid4()), "mode": "cash", "amount": "500"}
    urls = (
        f"/frontdesk/visits/{bill.visit_id}",
        f"/frontdesk/bills/{bill.id}/print",
        f"/frontdesk/payments/{payment.id}/print",
        f"/frontdesk/bills/{bill.id}/pay",
        f"/frontdesk/visits/{bill.visit_id}/labels",
        f"/frontdesk/bills/{bill.id}/cancel",
    )

    # b3desk is front desk and branch manager, but at B3.
    sign_in(db_client, "b3desk")
    for url in urls:
        assert db_client.get(url).status_code == 404
    assert bill.bill_no not in db_client.get("/frontdesk/bills").text
    assert bill.bill_no not in db_client.get("/frontdesk/dues").text
    assert post(db_client, f"/frontdesk/bills/{bill.id}/pay", pay).status_code == 404
    assert post(db_client, f"/frontdesk/bills/{bill.id}/cancel", cancel).status_code == 404
    seeded.refresh(bill)
    assert (bill.status, bill.paid) == ("open", Decimal(300))

    # At her own branch priya reaches all of it except cancelling.
    sign_in(db_client, "priya")
    for url in urls[:5]:
        assert db_client.get(url).status_code == 200
    assert db_client.get(urls[5]).status_code == 403
    assert post(db_client, f"/frontdesk/bills/{bill.id}/cancel", cancel).status_code == 403
    assert "Cancel bill" not in db_client.get(urls[0]).text
    seeded.refresh(bill)
    assert bill.status == "open"
