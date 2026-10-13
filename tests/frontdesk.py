"""Helpers shared by the front-desk tests: signing in and making synthetic patients."""

import re
import uuid
from collections.abc import Mapping

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth import service as auth
from labra.auth.principal import Principal
from labra.core.ids import utcnow
from labra.core.registry import Platform
from labra.org.models import Branch
from labra.patients import service as patients
from labra.patients.models import Patient
from labra.seed import DEMO_PASSWORD
from labra.visits.models import Visit
from tests.conftest import SEED_DAY

_TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


def as_user(db: Session, platform: Platform, username: str) -> Principal:
    signed = auth.login(db, platform.identity, username, DEMO_PASSWORD, "10.0.0.5", utcnow())
    return auth.principal_for(db, signed.session)


def branch(db: Session, code: str) -> Branch:
    found = db.scalar(select(Branch).where(Branch.code == code))
    assert found is not None
    return found


def sign_in(client: TestClient, username: str) -> None:
    client.cookies.clear()
    token = _TOKEN.search(client.get("/login").text)
    assert token is not None
    form = {"username": username, "password": DEMO_PASSWORD, "csrf_token": token.group(1)}
    assert client.post("/login", data=form, follow_redirects=False).status_code == 303


def post(client: TestClient, url: str, data: Mapping[str, object]):
    token = _TOKEN.search(client.get("/").text)
    assert token is not None
    return client.post(url, data={**data, "csrf_token": token.group(1)}, follow_redirects=False)


def patient_input(**changes: object) -> patients.PatientInput:
    values: dict[str, object] = {
        "full_name": "Sunita Testcase",
        "sex": "F",
        "age_years": 34,
        "phone": "9000000001",
    }
    return patients.PatientInput(**{**values, **changes})  # type: ignore[arg-type]


def register(db: Session, principal: Principal, **changes: object) -> Patient:
    return patients.register_patient(db, principal, patient_input(**changes), SEED_DAY)


def visit_at(db: Session, patient: Patient, branch_code: str) -> Visit:
    """A bare visit row, enough to make the patient known at that branch."""
    visit = Visit(
        visit_no=f"{branch_code}/V/{uuid.uuid4().hex[:8]}",
        branch_id=branch(db, branch_code).id,
        patient_id=patient.id,
        promised_at=utcnow(),
        client_ref=uuid.uuid4(),
    )
    db.add(visit)
    db.flush()
    return visit
