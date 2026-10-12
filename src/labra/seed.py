"""Synthetic demo data: the cast of the design's worked example (§1e), plus a few extra staff
from Faker. Every name and number here is made up. Tests reuse the factory functions.
"""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core.errors import ConfigError
from labra.core.numbering import ensure_series
from labra.core.ports import IdentityProvider
from labra.org.models import AppUser, Branch, Role, UserBranchRole
from labra.org.service import sync_system_roles

DEMO_PASSWORD = "demo-password-1"  # noqa: S105  synthetic demo data only
FAKER_SEED = 2026

# (username, full name, can_login, [(branch code, role code)])
CAST: list[tuple[str, str, bool, list[tuple[str, str]]]] = [
    ("anil", "Anil Kumar", True, [("MAIN", "admin"), ("B2", "admin"), ("B3", "admin")]),
    ("priya", "Priya Sharma", True, [("B2", "front_desk")]),
    ("suresh", "Suresh Iyer", True, [("MAIN", "technician")]),
    ("meera", "Dr Meera Nair, MD", True, [("MAIN", "signatory")]),
    ("b3desk", "Kavya Rao", True, [("B3", "front_desk"), ("B3", "branch_manager")]),
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


def seed(db: Session, identity: IdentityProvider, today: date) -> None:
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


def run() -> None:
    from labra.core.db import get_engine
    from labra.core.ids import lab_today
    from labra.core.registry import get_platform

    with Session(get_engine()) as db:
        seed(db, get_platform().identity, lab_today())
        db.commit()
