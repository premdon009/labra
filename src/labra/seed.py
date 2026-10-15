"""Synthetic demo data: the cast of the design's worked example (§1e), plus a few extra staff
from Faker, and on request a priced catalog, referrers and patients for a demo day. Every
name and number here is made up. Tests reuse the factory functions.
"""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.auth.service import grants_for
from labra.catalog import service as catalog
from labra.catalog.models import Test
from labra.catalog.starter import import_starter
from labra.core import lab_settings
from labra.core.errors import ConfigError
from labra.core.numbering import ensure_series
from labra.core.ports import IdentityProvider
from labra.extlabs import service as extlabs
from labra.extlabs.models import ExternalLab
from labra.org.models import AppUser, Branch, Role, UserBranchRole
from labra.org.service import sync_system_roles
from labra.patients import service as patients
from labra.patients.models import Patient, Referrer

if TYPE_CHECKING:
    from faker import Faker

DEMO_PASSWORD = "demo-password-1"  # noqa: S105  synthetic demo data only
DEMO_STATE_CODE = "29"
FAKER_SEED = 2026

# (username, full name, can_login, [(branch code, role code)])
CAST: list[tuple[str, str, bool, list[tuple[str, str]]]] = [
    ("anil", "Anil Kumar", True, [("MAIN", "admin"), ("B2", "admin"), ("B3", "admin")]),
    ("priya", "Priya Sharma", True, [("B2", "front_desk")]),
    ("suresh", "Suresh Iyer", True, [("MAIN", "technician")]),
    ("meera", "Dr Meera Nair, MD", True, [("MAIN", "signatory")]),
    ("b3desk", "Kavya Rao", True, [("B3", "front_desk"), ("B3", "branch_manager")]),
]

# Lab-wide demo prices by test code. The starter catalog ships without prices.
DEMO_PRICES = {"fbs": "80", "lipid": "500", "urine": "150", "vitd": "1200"}

# Invented referral labs with a different cost and wait for the outsourced demo test:
# (name, certificate, cost, hours, their code).
DEMO_EXTERNAL_LABS = [
    ("Demo Referral Lab A", "MC-0000A", "700", 48, "VD25"),
    ("Demo Referral Lab B", "MC-0000B", "620", 72, "D-TOTAL"),
]

# (branch code, sex, age in years) of the demo patients; their phones are 9000000001 onwards.
DEMO_PATIENTS = [
    ("B2", "F", 34),
    ("B2", "M", 61),
    ("B2", "F", 8),
    ("B2", "M", 45),
    ("B3", "F", 27),
    ("B3", "M", 72),
]


def make_branch(db: Session, code: str, name: str, kind: str = "collection_centre") -> Branch:
    branch = db.scalar(select(Branch).where(Branch.code == code))
    if branch is None:
        branch = Branch(code=code, name=name, kind=kind)
        db.add(branch)
        db.flush()
    return branch


def make_user(
    db: Session,
    identity: IdentityProvider | None,
    username: str,
    full_name: str,
    roles: Sequence[tuple[uuid.UUID, str]] = (),
    can_login: bool = True,
    password: str = DEMO_PASSWORD,
) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.username == username))
    if user is None:
        user = AppUser(username=username, full_name=full_name, can_login=can_login)
        db.add(user)
        db.flush()
        if can_login and identity is not None:
            identity.set_password(db, user.id, password)
    for branch_id, role_code in roles:
        role_id = db.scalar(select(Role.id).where(Role.code == role_code))
        if role_id is None:
            raise ConfigError(f"Role {role_code} is missing; run sync_system_roles first.")
        exists = db.get(UserBranchRole, (user.id, branch_id, role_id))
        if exists is None:
            db.add(UserBranchRole(user_id=user.id, branch_id=branch_id, role_id=role_id))
    db.flush()
    return user


def _acting(db: Session, username: str, branch: Branch | None = None) -> Principal:
    user = db.scalars(select(AppUser).where(AppUser.username == username)).one()
    return Principal(
        user.id, user.username, user.full_name, branch and branch.id, grants_for(db, user.id)
    )


def _demo_catalog(db: Session, admin: Principal, today: date) -> None:
    """The starter catalog, an outsourced test it lacks, prices for a demo order, and two
    external labs that do the outsourced test."""
    import_starter(db, admin)
    tests = {code: test_id for test_id, code in db.execute(select(Test.id, Test.code))}
    if "vitd" not in tests:
        lipid = db.get_one(Test, tests["lipid"])
        vitd = catalog.save_test(
            db,
            admin,
            catalog.TestInput(
                code="vitd",
                name="Vitamin D (25-OH)",
                department_id=lipid.department_id,
                short_name="VIT D",
                specimen_type_id=lipid.specimen_type_id,
                default_tat_hours=72,
                in_house_available=False,
            ),
        )
        tests["vitd"] = vitd.id
    if not catalog.list_parameters(db, admin, tests["vitd"]):
        # One row, so the value on the outside lab's PDF can be typed next to it.
        catalog.save_parameter(
            db,
            admin,
            tests["vitd"],
            catalog.ParameterInput(
                code="VITD",
                name="Vitamin D (25-OH)",
                result_type="numeric",
                unit_ucum="ng/mL",
                decimals=1,
                display_order=10,
            ),
        )
    priced = catalog.lab_prices(db, [tests[code] for code in DEMO_PRICES])
    for code, amount in DEMO_PRICES.items():
        if tests[code] not in priced:
            catalog.set_price(db, admin, "test", tests[code], amount)
    for name, cert, cost, hours, their_code in DEMO_EXTERNAL_LABS:
        if db.scalar(select(ExternalLab.id).where(ExternalLab.name == name)) is None:
            lab = extlabs.create_lab(db, admin, extlabs.LabInput(name, cert, dpa_signed_on=today))
            extlabs.set_rate(db, admin, lab.id, "vitd", cost, hours, their_code)


def _demo_people(db: Session, fake: "Faker", branches: dict[str, Branch], today: date) -> None:
    """Three referrers and six patients. Names come from Faker; registration numbers and
    phones are written here so that none can be a real one."""
    admin = _acting(db, "anil", branches["MAIN"])
    for i in range(1, 4):
        reg_no = f"DEMO-{i:04d}"
        name = f"Dr {fake.name()}"
        if db.scalar(select(Referrer.id).where(Referrer.council_reg_no == reg_no)) is None:
            patients.create_referrer(
                db, admin, patients.ReferrerInput("doctor", name, "MBBS", reg_no)
            )
    desks = {
        "B2": _acting(db, "priya", branches["B2"]),
        "B3": _acting(db, "b3desk", branches["B3"]),
    }
    for i, (code, sex, years) in enumerate(DEMO_PATIENTS, start=1):
        phone = f"90000000{i:02d}"
        name = fake.name_female() if sex == "F" else fake.name_male()
        if db.scalar(select(Patient.id).where(Patient.phone == phone)) is None:
            data = patients.PatientInput(name, sex, age_years=years, phone=phone)
            patients.register_patient(db, desks[code], data, today)


def seed(
    db: Session,
    identity: IdentityProvider,
    today: date,
    with_catalog: bool = False,
    with_people: bool = False,
) -> None:
    known = {c[0] for c in CAST} | {f"staff{i}" for i in range(1, 4)}
    others = db.scalars(select(AppUser.username).where(AppUser.username.not_in(known))).first()
    if others is not None:
        raise ConfigError("This database has real users. The demo seed only runs on a demo.")
    try:
        from faker import Faker
    except ImportError:
        raise ConfigError("Install the seed extra first: uv sync --extra seed.") from None
    sync_system_roles(db)
    branches = {
        "MAIN": make_branch(db, "MAIN", "Main Lab", "main_lab"),
        "B2": make_branch(db, "B2", "Branch 2"),
        "B3": make_branch(db, "B3", "Branch 3"),
    }
    for branch in branches.values():
        ensure_series(db, branch.id, branch.code, today)
    if not lab_settings.get_value(db, "lab.state_code"):
        # A made-up place of supply, so demo bills print one; the branches inherit it.
        lab_settings.set_value(db, "lab.state_code", DEMO_STATE_CODE, None)
    for username, full_name, can_login, roles in CAST:
        make_user(
            db,
            identity,
            username,
            full_name,
            [(branches[b].id, r) for b, r in roles],
            can_login,
        )
    # Staff who appear on records but never sign in, e.g. home-collection phlebotomists.
    fake = Faker("en_IN")
    fake.seed_instance(FAKER_SEED)
    for i in range(1, 4):
        make_user(
            db,
            identity,
            f"staff{i}",
            fake.name(),
            [(branches["B2" if i % 2 else "MAIN"].id, "phlebotomist")],
            can_login=False,
        )
    db.flush()
    if with_catalog:
        _demo_catalog(db, _acting(db, "anil"), today)
    if with_people:
        _demo_people(db, fake, branches, today)


def run() -> None:
    from labra.core.db import get_engine
    from labra.core.ids import lab_today
    from labra.core.registry import get_platform

    with Session(get_engine()) as db:
        seed(db, get_platform().identity, lab_today(), with_catalog=True, with_people=True)
        db.commit()
