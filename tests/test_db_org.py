"""Branches and staff through the org service against real Postgres, using the demo cast."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth import service as auth
from labra.auth.principal import Principal
from labra.core.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.ids import utcnow
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.org import service as org
from labra.org.models import AppUser, Branch, Role
from labra.seed import DEMO_PASSWORD

NEW_PASSWORD = "brand-new-password-7"


def _as(db: Session, platform: Platform, username: str) -> Principal:
    signed = auth.login(db, platform.identity, username, DEMO_PASSWORD, "10.0.0.5", utcnow())
    return auth.principal_for(db, signed.session)


def _branch(db: Session, code: str) -> Branch:
    branch = db.scalar(select(Branch).where(Branch.code == code))
    assert branch is not None
    return branch


def _role(db: Session, code: str) -> uuid.UUID:
    role_id = db.scalar(select(Role.id).where(Role.code == code))
    assert role_id is not None
    return role_id


def _actions(db: Session, entity_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(AuditLog.action)
            .where(AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.id)
        )
    )


# Branches


@pytest.mark.item("M02")
def test_create_and_update_branch(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    branch = org.create_branch(
        seeded,
        admin,
        org.BranchInput(
            code=" b4 ",
            name="Branch 4",
            kind="collection_centre",
            state_code="27",
            phone="9000000004",
            gstin="27abcde1234f1z5",
        ),
    )
    assert (branch.code, branch.gstin) == ("B4", "27ABCDE1234F1Z5")
    # The creator holds their editing role there now, so the new branch is in their list.
    admin = _as(seeded, platform, "anil")
    assert "B4" in [b.code for b in org.list_branches(seeded, admin)]
    assert org.get_branch(seeded, admin, branch.id) is branch
    assert org.user_roles(seeded, admin.user_id) >= {(branch.id, _role(seeded, "admin"))}

    data = org.BranchInput(
        code="B4",
        name="Branch Four",
        kind="collection_centre",
        state_code="27",
        phone="9000000004",
        gstin="27ABCDE1234F1Z5",
    )
    org.update_branch(seeded, admin, branch.id, data, branch.row_version)
    assert branch.name == "Branch Four"
    # Saving the same values again changes nothing and writes no audit row.
    org.update_branch(seeded, admin, branch.id, data, branch.row_version)
    assert _actions(seeded, branch.id) == ["branch.create", "branch.update"]


@pytest.mark.item("M02")
def test_branch_edit_with_stale_version_conflicts(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    b2 = _branch(seeded, "B2")
    data = org.BranchInput(code="B2", name="Renamed", kind="collection_centre")
    with pytest.raises(ConflictError):
        org.update_branch(seeded, admin, b2.id, data, b2.row_version - 1)


@pytest.mark.item("M02")
def test_branch_validation(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    with pytest.raises(ValidationFailedError) as bad:
        org.create_branch(
            seeded,
            admin,
            org.BranchInput(
                code="TOOLONG",
                name=" ",
                kind="warehouse",
                state_code="X",
                phone="12345",
                gstin="NOTAGSTIN",
            ),
        )
    assert set(bad.value.errors) == {"code", "name", "kind", "state_code", "phone", "gstin"}
    with pytest.raises(ValidationFailedError) as clash:
        org.create_branch(seeded, admin, org.BranchInput(code="b2", name="Dup", kind="main_lab"))
    assert clash.value.errors == {
        "code": "Branch code B2 is already used.",
        "kind": "There is already a main lab.",
    }
    # The main lab may keep its own kind when edited.
    main = _branch(seeded, "MAIN")
    data = org.BranchInput(code="MAIN", name="Main lab, renamed", kind="main_lab")
    org.update_branch(seeded, admin, main.id, data, main.row_version)


@pytest.mark.item("EC-A05")
def test_branch_manager_cannot_edit_branches(seeded: Session, platform: Platform) -> None:
    manager = _as(seeded, platform, "b3desk")
    b2 = _branch(seeded, "B2")
    with pytest.raises(PermissionDeniedError):
        org.update_branch(
            seeded, manager, b2.id, org.BranchInput("B2", "Taken over", "collection_centre"), 1
        )
    with pytest.raises(NotFoundError):
        org.get_branch(seeded, _as(seeded, platform, "anil"), uuid.uuid4())


# Staff


@pytest.mark.item("M01.1")
def test_create_user_with_roles_then_sign_in(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    b2, desk = _branch(seeded, "B2").id, _role(seeded, "front_desk")
    user = org.create_user(
        seeded,
        admin,
        platform.identity,
        org.UserInput(username=" Ravi.K ", full_name="Ravi K", roles={(b2, desk)}),
        NEW_PASSWORD,
    )
    assert user.username == "ravi.k"
    assert org.user_roles(seeded, user.id) == {(b2, desk)}
    assert user in org.list_users(seeded, admin)
    assert org.get_user(seeded, admin, user.id) is user
    assert {r.code for r in org.list_roles(seeded)} >= {"admin", "front_desk"}
    signed = auth.login(seeded, platform.identity, "ravi.k", NEW_PASSWORD, "10.0.0.5", utcnow())
    assert signed.session.branch_id == b2
    assert _actions(seeded, user.id)[0] == "user.create"


@pytest.mark.item("M01.2")
def test_staff_without_sign_in_needs_no_password(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    user = org.create_user(
        seeded,
        admin,
        platform.identity,
        org.UserInput(username="phlebo1", full_name="Collection Staff", can_login=False),
        None,
    )
    assert not user.can_login


@pytest.mark.item("M01.1")
def test_user_validation(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    with pytest.raises(ValidationFailedError) as bad:
        org.create_user(
            seeded,
            admin,
            platform.identity,
            org.UserInput(
                username="x",
                full_name="",
                phone="555",
                email="nope",
                roles={(uuid.uuid4(), uuid.uuid4())},
            ),
            NEW_PASSWORD,
        )
    assert set(bad.value.errors) == {"username", "full_name", "phone", "email", "roles"}
    with pytest.raises(ValidationFailedError) as taken:
        org.create_user(
            seeded,
            admin,
            platform.identity,
            org.UserInput(username="PRIYA", full_name="Another Priya"),
            NEW_PASSWORD,
        )
    assert taken.value.errors == {"username": "That username is taken."}
    with pytest.raises(ValidationFailedError) as weak:
        org.create_user(
            seeded,
            admin,
            platform.identity,
            org.UserInput(username="newbie", full_name="New Person"),
            "short",
        )
    assert set(weak.value.errors) == {"password"}


@pytest.mark.item("M01.1")
def test_update_user_fields_and_roles(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    priya = seeded.scalar(select(AppUser).where(AppUser.username == "priya"))
    assert priya is not None
    b3, desk = _branch(seeded, "B3").id, _role(seeded, "front_desk")
    data = org.UserInput(
        username="priya",
        full_name=priya.full_name,
        phone="9000000002",
        roles={(b3, desk)},
    )
    org.update_user(seeded, admin, priya.id, data, priya.row_version)
    assert priya.phone == "9000000002"
    assert org.user_roles(seeded, priya.id) == {(b3, desk)}
    with pytest.raises(ConflictError):
        org.update_user(seeded, admin, priya.id, data, priya.row_version - 1)
    with pytest.raises(NotFoundError):
        org.update_user(seeded, admin, uuid.uuid4(), data, 1)


@pytest.mark.item("M01.1")
def test_admin_cannot_switch_off_own_sign_in(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    me = org.get_user(seeded, admin, admin.user_id)
    roles = org.user_roles(seeded, me.id)
    for can_login, is_active in ((False, True), (True, False)):
        data = org.UserInput(
            username="anil",
            full_name=me.full_name,
            can_login=can_login,
            is_active=is_active,
            roles=roles,
        )
        with pytest.raises(ValidationFailedError) as refused:
            org.update_user(seeded, admin, me.id, data, me.row_version)
        assert set(refused.value.errors) == {"can_login"}


@pytest.mark.item("M01")
def test_reset_password_ends_sessions(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    now = utcnow()
    old = auth.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.5", now)
    with pytest.raises(ValidationFailedError):
        org.reset_password(seeded, admin, platform.identity, old.session.user_id, "short")
    org.reset_password(seeded, admin, platform.identity, old.session.user_id, NEW_PASSWORD)
    assert old.session.ended_at is not None
    with pytest.raises(AuthenticationError):
        auth.login(seeded, platform.identity, "priya", DEMO_PASSWORD, "10.0.0.5", now)
    auth.login(seeded, platform.identity, "priya", NEW_PASSWORD, "10.0.0.5", now)
    assert "user.password_reset" in _actions(seeded, old.session.user_id)
