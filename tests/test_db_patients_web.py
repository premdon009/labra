"""The patient and referrer screens, through the browser's requests."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core.registry import Platform
from labra.patients import service
from labra.patients.models import Patient, Referrer
from tests.frontdesk import as_user, post, register, sign_in

FORM = {"full_name": "Sunita Testcase", "sex": "F", "age_years": "34", "phone": "9000000001"}


@pytest.mark.item("M03")
def test_register_and_edit_patient_screens(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    sign_in(db_client, "priya")
    assert "No patients yet." in db_client.get("/frontdesk/patients").text
    assert db_client.get("/frontdesk/patients/new").status_code == 200
    saved = post(db_client, "/frontdesk/patients", FORM)
    assert saved.status_code == 303
    patient = seeded.scalar(select(Patient).where(Patient.phone == "9000000001"))
    assert patient is not None
    assert saved.headers["location"] == f"/frontdesk/patients?q={patient.patient_no}"

    listed = db_client.get(saved.headers["location"]).text
    assert "Sunita Testcase" in listed
    assert "34 Y (about) / Female" in listed
    assert "No patient matches" in db_client.get("/frontdesk/patients?q=Nobody+Atall").text

    form = db_client.get(f"/frontdesk/patients/{patient.id}").text
    assert f'name="dob" value="{patient.dob.isoformat()}"' in form
    changed = {**FORM, "age_years": "", "dob": "1992-05-01", "city": "Mysuru"}
    changed |= {"patient_id": str(patient.id), "row_version": str(patient.row_version)}
    assert post(db_client, "/frontdesk/patients", changed).status_code == 303
    seeded.refresh(patient)
    assert (patient.city, patient.dob_is_estimated) == ("Mysuru", False)
    # The same form again is now a stale copy.
    assert post(db_client, "/frontdesk/patients", changed).status_code == 409


@pytest.mark.item("M03")
def test_patient_form_errors_keep_what_was_typed(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    sign_in(db_client, "priya")
    bad = {"full_name": "Sunita Testcase", "sex": "F", "dob": "next week", "phone": "12345"}
    page = post(db_client, "/frontdesk/patients", bad)
    assert page.status_code == 422
    assert "Enter the date of birth as a date." in page.text
    assert "Ten digits, starting with 6 to 9." in page.text
    assert 'value="Sunita Testcase"' in page.text
    assert 'value="12345"' in page.text
    letters = post(db_client, "/frontdesk/patients", {**FORM, "age_years": "abc"})
    assert letters.status_code == 422
    assert "Enter years up to 150" in letters.text
    assert seeded.scalar(select(Patient.id)) is None


@pytest.mark.item("M03")
@pytest.mark.item("EC-B03")
def test_duplicate_warning_asks_before_registering(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    first = register(seeded, as_user(seeded, platform, "priya"))
    sign_in(db_client, "priya")
    again = {**FORM, "full_name": "Suneeta Testcase"}
    warned = post(db_client, "/frontdesk/patients", again)
    assert warned.status_code == 422
    assert "is already registered" in warned.text
    assert first.patient_no in warned.text
    assert f'href="/frontdesk/patients/{first.id}"' in warned.text
    assert 'name="confirm_new" value="true"' in warned.text
    assert seeded.scalar(select(Patient.id).where(Patient.full_name == "Suneeta Testcase")) is None
    assert (
        post(db_client, "/frontdesk/patients", {**again, "confirm_new": "true"}).status_code == 303
    )
    assert seeded.scalar(select(Patient.id).where(Patient.full_name == "Suneeta Testcase"))

    # Another branch is told one may exist, and nothing about it.
    sign_in(db_client, "b3desk")
    elsewhere = post(db_client, "/frontdesk/patients", {**FORM, "full_name": "Sunita T"})
    assert elsewhere.status_code == 422
    assert "may be registered at another branch" in elsewhere.text
    assert first.patient_no not in elsewhere.text
    assert "Sunita Testcase" not in elsewhere.text
    assert str(first.id) not in elsewhere.text


@pytest.mark.item("M04")
def test_referrer_screens(seeded: Session, platform: Platform, db_client: TestClient) -> None:
    sign_in(db_client, "priya")
    assert "No referrers yet." in db_client.get("/frontdesk/referrers").text
    new = {"kind": "doctor", "name": "Dr Asha Testcase", "qualification": "MBBS"}
    assert post(db_client, "/frontdesk/referrers", new).status_code == 303
    referrer = seeded.scalar(select(Referrer))
    assert referrer is not None and referrer.is_active
    assert "Dr Asha Testcase" in db_client.get("/frontdesk/referrers?q=asha").text
    assert "No referrer matches" in db_client.get("/frontdesk/referrers?q=zzz").text

    edit = {**new, "referrer_id": str(referrer.id), "row_version": str(referrer.row_version)}
    assert post(db_client, "/frontdesk/referrers", edit).status_code == 303
    seeded.refresh(referrer)
    assert not referrer.is_active
    assert "Not in use" in db_client.get("/frontdesk/referrers").text
    assert post(db_client, "/frontdesk/referrers", edit).status_code == 409

    bad = post(db_client, "/frontdesk/referrers", {"kind": "doctor", "name": " ", "phone": "1"})
    assert bad.status_code == 422
    assert "Enter the name." in bad.text


@pytest.mark.item("M04")
def test_referrer_form_has_no_commission_field(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    sign_in(db_client, "priya")
    form = db_client.get("/frontdesk/referrers/new").text.lower()
    for word in ("commission", "payout", "percent", "share", "incentive", "cut"):
        assert f'name="{word}' not in form
        assert not re.search(rf"\b{word}", form)
    assert not {c.name for c in Referrer.__table__.columns} & {"commission", "commission_pct"}


@pytest.mark.item("EC-F03")
@pytest.mark.item("M03")
@pytest.mark.item("M04")
def test_frontdesk_lists_paginate(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    priya = as_user(seeded, platform, "priya")
    for i in range(26):
        register(seeded, priya, full_name=f"Patient {i:02d} Testcase", phone=f"90000001{i:02d}")
        service.create_referrer(
            seeded, priya, service.ReferrerInput("doctor", f"Dr Number {i:02d}")
        )
    sign_in(db_client, "priya")
    for url in ("/frontdesk/patients", "/frontdesk/referrers"):
        first = db_client.get(f"{url}?q=e")
        assert first.text.count(">Edit</a>") == 25
        assert f'href="{url}?q=e&amp;page=2"' in first.text
        second = db_client.get(f"{url}?q=e&page=2").text
        assert second.count(">Edit</a>") == 1
        assert 'rel="prev"' in second and 'rel="next"' not in second
        junk = db_client.get(f"{url}?q=e&page=two")
        assert junk.status_code == 200
        assert 'rel="next"' in junk.text and 'rel="prev"' not in junk.text
