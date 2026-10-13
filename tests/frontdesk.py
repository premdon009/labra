"""Helpers shared by the front-desk tests: signing in and making synthetic patients."""

import re
import uuid
from collections.abc import Mapping, Sequence
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth import service as auth
from labra.auth.principal import Principal
from labra.billing import service as billing
from labra.billing.models import Bill
from labra.catalog import service as catalog
from labra.core.ids import utcnow
from labra.core.registry import Platform
from labra.org.models import Branch
from labra.patients import service as patients
from labra.patients.models import Patient
from labra.seed import DEMO_PASSWORD
from labra.visits import service as visits
from labra.visits.models import OrderItem, Sample, Visit
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


def charge(db: Session, visit: Visit, rate: str, discount: str = "0") -> OrderItem:
    """An order line that needs no catalog: an extra charge."""
    item = OrderItem(
        visit_id=visit.id,
        item_type="extra_charge",
        description=f"Charge {rate}",
        reason="Synthetic charge",
        list_price=Decimal(rate),
        discount_amt=Decimal(discount),
        net_price=Decimal(rate) - Decimal(discount),
    )
    db.add(item)
    db.flush()
    return item


def sample(db: Session, visit: Visit, status: str = "pending") -> Sample:
    row = Sample(
        sample_no=f"S{uuid.uuid4().hex[:12]}",
        visit_id=visit.id,
        status=status,
        collected_at=None if status == "pending" else utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def billed(
    db: Session,
    principal: Principal,
    lines: Sequence[tuple[str, str]] = (("350", "0"), ("450", "0")),
    discount_reason: str = "",
    payment: billing.PaymentInput | None = None,
    **patient: object,
) -> Bill:
    """A new patient's visit at the user's branch with a bill for `lines` (rate, discount)."""
    assert principal.branch_id is not None
    code = db.get_one(Branch, principal.branch_id).code
    # A phone of their own, so a second bill in the same test isn't a possible duplicate.
    patient.setdefault("phone", f"90000{uuid.uuid4().int % 10**5:05d}")
    visit = visit_at(db, register(db, principal, **patient), code)
    items = [charge(db, visit, rate, discount) for rate, discount in lines]
    person = db.get_one(Patient, visit.patient_id)
    return billing.issue_bill(
        db, principal, visit, person, items, discount_reason, payment=payment, today=SEED_DAY
    )


def menu(db: Session, admin: Principal) -> dict[str, uuid.UUID]:
    """A small synthetic catalog with prices: four tests over three kinds of tube, one of
    them outsourced, and a package. Their ids by code."""
    dept = catalog.save_department(db, admin, "Biochemistry", 20)
    tubes = {
        code: catalog.save_specimen_type(db, admin, code, name, container).id
        for code, name, container in (
            ("FLUORIDE", "Fluoride plasma", "Grey top"),
            ("SERUM", "Serum", "Red top"),
            ("URINE", "Urine", "Urine cup"),
        )
    }
    ids: dict[str, uuid.UUID] = {}
    for code, name, aliases, tube, hours, in_house, price in (
        ("fbs", "Glucose, fasting", ["sf"], "FLUORIDE", 6, True, "80"),
        ("lipid", "Lipid profile", [], "SERUM", 24, True, "450"),
        ("urine", "Urine routine", ["urm"], "URINE", 6, True, "100"),
        ("vitd", "Vitamin D, 25-hydroxy", [], "SERUM", 72, False, "1300"),
    ):
        test = catalog.save_test(
            db,
            admin,
            catalog.TestInput(
                code=code,
                name=name,
                department_id=dept.id,
                aliases=aliases,
                short_name=code.upper(),
                specimen_type_id=tubes[tube],
                default_tat_hours=hours,
                in_house_available=in_house,
            ),
        )
        catalog.set_price(db, admin, "test", test.id, price)
        ids[code] = test.id
    package = catalog.save_package(db, admin, "basic", "Basic check", [ids["fbs"], ids["lipid"]])
    catalog.set_price(db, admin, "package", package.id, "500")
    ids["basic"] = package.id
    return ids


def visit_input(ids: Mapping[str, uuid.UUID], *codes: str, **changes: object) -> visits.VisitInput:
    """A new patient's visit for the tests and packages named by code, consent ticked."""
    values: dict[str, object] = {
        "client_ref": uuid.uuid4(),
        "patient": patient_input(phone=f"90000{uuid.uuid4().int % 10**5:05d}"),
        "consent": True,
        "items": [("package" if code == "basic" else "test", ids[code]) for code in codes],
    }
    return visits.VisitInput(**{**values, **changes})  # type: ignore[arg-type]
