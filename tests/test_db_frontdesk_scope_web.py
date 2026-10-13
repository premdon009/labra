"""A front-desk user at one branch can't reach another branch's records by any URL."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from labra.core.registry import Platform
from tests.frontdesk import as_user, post, register, sign_in, visit_at


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
    sign_in(db_client, "priya")
    home = db_client.get("/").text
    assert 'href="/frontdesk/patients"' in home
    assert 'href="/frontdesk/referrers"' in home
