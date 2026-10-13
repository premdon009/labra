"""Branches and staff through the org service against real Postgres, using the demo cast."""

import re
import uuid
from datetime import date
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from labra.auth import service as auth
from labra.auth.principal import Principal
from labra.core import consent, lab_settings
from labra.core.currency import load_format
from labra.core.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.ids import utcnow
from labra.core.models import AuditLog, ConsentNotice, NumberSeries
from labra.core.numbering import DEFAULT_SERIES, next_number
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
@pytest.mark.item("EC-B03")
def test_branch_edit_with_stale_version_names_who_changed_it(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    b2 = _branch(seeded, "B2")
    data = org.BranchInput(code="B2", name="Renamed", kind="collection_centre")
    org.update_branch(seeded, admin, b2.id, data, b2.row_version)
    with pytest.raises(ConflictError) as exc:
        org.update_branch(seeded, admin, b2.id, data, b2.row_version - 1)
    assert exc.value.public_message.startswith("Anil Kumar changed this record at ")
    assert exc.value.public_message.endswith("Reload to see their changes, then make yours again.")


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


# Number series


@pytest.mark.item("M07")
@pytest.mark.item("M02")
def test_new_branch_gets_number_series(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    branch = org.create_branch(
        seeded, admin, org.BranchInput(code="B4", name="Branch 4", kind="collection_centre")
    )
    have = seeded.scalars(select(NumberSeries.doc_type).where(NumberSeries.branch_id == branch.id))
    assert set(have) == set(DEFAULT_SERIES)
    day = date(2026, 10, 9)
    assert next_number(seeded, "bos", branch.id, "B4", day) == "B4/2627/00001"
    assert next_number(seeded, "sample", branch.id, "B4", day) == "B42627000001"


def _series(db: Session, code: str, doc_type: str) -> NumberSeries:
    return db.scalars(
        select(NumberSeries)
        .join(Branch, Branch.id == NumberSeries.branch_id)
        .where(Branch.code == code, NumberSeries.doc_type == doc_type)
    ).one()


@pytest.mark.item("M07.1")
def test_series_format_change(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    bos = _series(seeded, "MAIN", "bos")
    with pytest.raises(ValidationFailedError) as long:
        org.set_series_format(seeded, admin, bos.id, "{BR}/BILL/{FY2}/{SEQ:5}", bos.format)
    assert "at most 16 characters" in long.value.errors[str(bos.id)]
    assert org.set_series_format(seeded, admin, bos.id, "{BR}-{FY2}-{SEQ:5}", bos.format)
    assert _actions(seeded, bos.id) == ["number_series.update"]
    # The form showed the old format, so this edit is from before the change above.
    with pytest.raises(ConflictError):
        org.set_series_format(seeded, admin, bos.id, "{BR}/{FY2}/{SEQ:5}", "{BR}/{FY2}/{SEQ:5}")
    with pytest.raises(PermissionDeniedError):
        org.set_series_format(
            seeded, _as(seeded, platform, "b3desk"), bos.id, "{BR}/{SEQ:5}", bos.format
        )


@pytest.mark.item("M02.1")
def test_a_longer_branch_code_is_refused_when_a_number_would_no_longer_fit(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    branch = org.create_branch(
        seeded, admin, org.BranchInput(code="B4", name="Branch 4", kind="collection_centre")
    )
    admin = _as(seeded, platform, "anil")
    bos = _series(seeded, "B4", "bos")
    # Sixteen characters with a two-letter code: B4/BS/2627/00001.
    assert org.set_series_format(seeded, admin, bos.id, "{BR}/BS/{FY2}/{SEQ:5}", bos.format)

    def renamed(code: str) -> org.BranchInput:
        return org.BranchInput(code=code, name="Branch 4", kind="collection_centre")

    with pytest.raises(ValidationFailedError) as refused:
        org.update_branch(seeded, admin, branch.id, renamed("B44"), branch.row_version)
    assert "bill number no longer fits" in refused.value.errors["code"]
    assert "reaches 17" in refused.value.errors["code"]
    seeded.refresh(branch)
    assert branch.code == "B4"
    # A code of the same length still fits, and so does a longer one once the format is short.
    org.update_branch(seeded, admin, branch.id, renamed("C4"), branch.row_version)
    assert org.set_series_format(seeded, admin, bos.id, "{BR}/{FY2}/{SEQ:5}", bos.format)
    org.update_branch(seeded, admin, branch.id, renamed("C444"), branch.row_version)
    assert next_number(seeded, "bos", branch.id, branch.code, date(2026, 10, 9)) == (
        "C444/2627/00001"
    )


@pytest.mark.item("M02.1")
def test_upgrade_gives_older_branches_the_series_they_lack(seeded: Session) -> None:
    migration = import_module("labra.migrations.versions.0005_default_number_series")
    b2, b3 = (seeded.scalars(select(Branch).where(Branch.code == c)).one() for c in ("B2", "B3"))
    kept = _series(seeded, "B2", "bos")
    kept.format, kept.next_value = "{BR}-{SEQ:6}", 41
    seeded.flush()
    seeded.execute(delete(NumberSeries).where(NumberSeries.branch_id == b3.id))
    seeded.execute(
        delete(NumberSeries).where(
            NumberSeries.branch_id == b2.id, NumberSeries.doc_type.in_(("sample", "refund"))
        )
    )

    for _ in range(2):  # running it again adds nothing
        seeded.execute(text(migration.ADD_MISSING_SERIES))
    seeded.expire_all()
    for branch in (b2, b3):
        rows = seeded.scalars(select(NumberSeries).where(NumberSeries.branch_id == branch.id)).all()
        formats = {r.doc_type: r.format for r in rows}
        assert len(rows) == len(DEFAULT_SERIES)
        assert formats == DEFAULT_SERIES | ({"bos": "{BR}-{SEQ:6}"} if branch is b2 else {})
    assert _series(seeded, "B2", "bos").next_value == 41
    day = date(2026, 10, 13)
    assert next_number(seeded, "sample", b3.id, "B3", day) == "B32627000001"
    assert next_number(seeded, "refund", b2.id, "B2", day) == "B2/RF/2627/00001"


def _token(html: str) -> str:
    token = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert token is not None
    return token.group(1)


def _sign_in(client: TestClient, username: str) -> None:
    client.cookies.clear()
    form = {
        "username": username,
        "password": DEMO_PASSWORD,
        "csrf_token": _token(client.get("/login").text),
    }
    assert client.post("/login", data=form, follow_redirects=False).status_code == 303


def _post(client: TestClient, url: str, data: dict[str, object]):
    token = _token(client.get("/").text)
    return client.post(url, data={**data, "csrf_token": token}, follow_redirects=False)


@pytest.mark.item("M07.1")
def test_numbering_form_shows_16_char_problem(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    page = db_client.get("/admin/settings/numbering")
    assert page.status_code == 200
    assert "{BR}/P/{SEQ:6}" in page.text
    bos = _series(seeded, "B2", "bos")
    r = _post(
        db_client,
        "/admin/settings/numbering",
        {"series": str(bos.id), "was": bos.format, "fmt": "{BR}/BILL/{FY2}/{SEQ:5}"},
    )
    assert r.status_code == 422
    assert "at most 16 characters" in r.text
    assert "{BR}/BILL/{FY2}/{SEQ:5}" in r.text
    assert _series(seeded, "B2", "bos").format == "{BR}/{FY2}/{SEQ:5}"


# Consent notice


@pytest.mark.item("EC-C01")
def test_consent_notice_publishes_new_versions(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    first = consent.current_notice(seeded)
    assert first.version == 1
    _sign_in(db_client, "anil")
    page = db_client.get("/admin/settings/consent")
    assert page.status_code == 200
    assert "Version 1" in page.text
    assert "Replace this with your lab" in page.text

    wording = "I agree to these tests and to sharing my sample with a referral lab."
    r = _post(db_client, "/admin/settings/consent", {"body_text": wording + "\r\n", "was": 1})
    assert r.status_code == 303
    second = consent.current_notice(seeded)
    assert (second.version, second.body_text) == (2, wording)
    assert seeded.get(ConsentNotice, first.id) is not None
    assert seeded.scalar(select(AuditLog).where(AuditLog.action == "consent_notice.publish"))

    # The same words again publish nothing; an edit of an older version is refused.
    assert (
        _post(db_client, "/admin/settings/consent", {"body_text": wording, "was": 2}).status_code
        == 303
    )
    assert consent.current_notice(seeded).version == 2
    assert (
        _post(db_client, "/admin/settings/consent", {"body_text": "Old", "was": 1}).status_code
        == 409
    )
    r = _post(db_client, "/admin/settings/consent", {"body_text": "  ", "was": 2})
    assert r.status_code == 422
    assert "Write the notice" in r.text
    assert consent.current_notice(seeded).version == 2


@pytest.mark.item("EC-C01")
def test_only_admin_publishes_consent_notice(seeded: Session, platform: Platform) -> None:
    manager = _as(seeded, platform, "b3desk")
    with pytest.raises(PermissionDeniedError):
        org.publish_consent_notice(seeded, manager, "New words", 1)
    assert consent.current_notice(seeded).version == 1


# Currency


def _currency_form(**changes: str) -> dict[str, object]:
    keys = [k for k, d in lab_settings.DEFINITIONS.items() if d.group == "currency"]
    values = [
        changes.get(k.removeprefix("currency."), lab_settings.DEFINITIONS[k].default) for k in keys
    ]
    return {"key": keys, "value": values}


@pytest.mark.item("M23")
def test_currency_screen_saves_per_branch(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    _sign_in(db_client, "b3desk")
    page = db_client.get("/admin/settings/currency")
    assert page.status_code == 200
    assert "₹1,23,456.50" in page.text
    assert "Rupees one lakh twenty-three thousand four hundred fifty-six and fifty paise only" in (
        page.text
    )
    # The preview shows the change before it is saved.
    preview = _post(
        db_client, "/admin/settings/currency/preview", _currency_form(grouping="international")
    )
    assert "₹123,456.50" in preview.text
    assert load_format(seeded, _branch(seeded, "B3").id).grouping == "indian"
    # A branch manager may change their own branch's currency display.
    r = _post(
        db_client,
        "/admin/settings/currency",
        _currency_form(grouping="international", symbol_position="after_space"),
    )
    assert r.status_code == 303, r.text
    assert "123,456.50 ₹" in db_client.get("/admin/settings/currency").text
    assert load_format(seeded, _branch(seeded, "B3").id).grouping == "international"
    assert load_format(seeded, _branch(seeded, "B2").id).grouping == "indian"
    bad = _post(db_client, "/admin/settings/currency", _currency_form(decimals="3"))
    assert bad.status_code == 422
    assert "Choose one of the listed values." in bad.text


@pytest.mark.item("M23")
def test_currency_screen_needs_settings_permission(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    _sign_in(db_client, "priya")
    assert db_client.get("/admin/settings/currency").status_code == 403


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
    assert user in org.user_page(seeded, admin, 1).items
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
@pytest.mark.item("EC-B03")
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
    with pytest.raises(ConflictError) as exc:
        org.update_user(seeded, admin, priya.id, data, priya.row_version - 1)
    assert exc.value.public_message.startswith("Anil Kumar changed this record at ")
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
