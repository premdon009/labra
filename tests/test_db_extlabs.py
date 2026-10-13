"""External labs and their rates: the service rules and the admin screens."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.catalog.models import Test
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.ids import utcnow
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.extlabs import service
from labra.extlabs.models import ExternalLab, ExternalLabRate
from labra.seed import DEMO_EXTERNAL_LABS, seed
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, menu, post, sign_in


def _problems(call) -> dict[str, str]:
    with pytest.raises(ValidationFailedError) as refused:
        call()
    return refused.value.errors


@pytest.mark.item("M10")
def test_add_and_change_a_lab(seeded: Session, platform: Platform) -> None:
    admin = as_user(seeded, platform, "anil")
    lab = service.create_lab(
        seeded,
        admin,
        service.LabInput("  Synthetic   Referral Lab ", phone="080 5550 0000"),
        SEED_DAY,
    )
    assert lab.name == "Synthetic Referral Lab"
    assert (lab.share_phone, lab.share_address, lab.is_active) == (False, False, True)

    again = _problems(
        lambda: service.create_lab(seeded, admin, service.LabInput("synthetic referral lab"))
    )
    assert again == {"name": "Another lab already has this name."}
    bad = service.LabInput(
        " ",
        phone="12",
        email="nobody",
        results_email="a@b",
        portal_url="portal.example.org",
        dpa_signed_on=SEED_DAY + timedelta(days=1),
    )
    assert set(_problems(lambda: service.create_lab(seeded, admin, bad, SEED_DAY))) == {
        "name",
        "phone",
        "email",
        "results_email",
        "portal_url",
        "dpa_signed_on",
    }

    changed = service.LabInput(lab.name, share_phone=True, dpa_signed_on=SEED_DAY, is_active=False)
    version = lab.row_version
    service.update_lab(seeded, admin, lab.id, changed, version, SEED_DAY)
    assert (lab.share_phone, lab.is_active, lab.dpa_signed_on) == (True, False, SEED_DAY)
    with pytest.raises(ConflictError):
        service.update_lab(seeded, admin, lab.id, changed, version, SEED_DAY)
    logged = seeded.scalars(
        select(AuditLog).where(
            AuditLog.action == "extlab.update", AuditLog.entity_id == str(lab.id)
        )
    ).one()
    assert set(logged.detail["fields"]) == {"phone", "share_phone", "dpa_signed_on", "is_active"}


@pytest.mark.item("M10")
def test_a_new_rate_closes_the_old_one(seeded: Session, platform: Platform) -> None:
    admin = as_user(seeded, platform, "anil")
    ids = menu(seeded, admin)
    lab = service.create_lab(seeded, admin, service.LabInput("Synthetic Referral Lab"))
    other = service.create_lab(seeded, admin, service.LabInput("Synthetic Second Lab"))

    first = service.set_rate(seeded, admin, lab.id, " VITD ", "700", "48", "VD25")
    between = utcnow()
    second = service.set_rate(seeded, admin, lab.id, "vitd", Decimal("650.50"), 72)
    service.set_rate(seeded, admin, other.id, "vitd", "600", "96")
    assert first.valid_to == second.valid_from
    assert [(r.test.code, r.rate.cost) for r in service.rates_of_lab(seeded, admin, lab.id)] == [
        ("vitd", Decimal("650.50"))
    ]
    assert [r.rate.id for r in service.rates_of_lab(seeded, admin, lab.id, history=True)] == [
        first.id
    ]
    logged = seeded.scalars(
        select(AuditLog).where(
            AuditLog.action == "extlab.rate_set", AuditLog.entity_id == str(second.id)
        )
    ).one()
    assert logged.detail["before"] == {"cost": "700.00", "tat_hours": 48}
    assert logged.detail["after"] == {"cost": "650.50", "tat_hours": 72}

    # Cheapest first, and what was charged at an earlier moment.
    now = [(q.lab.name, q.rate.cost) for q in service.quotes_for(seeded, admin, ids["vitd"])]
    assert now == [
        ("Synthetic Second Lab", Decimal("600.00")),
        ("Synthetic Referral Lab", Decimal("650.50")),
    ]
    then = service.quotes_for(seeded, admin, ids["vitd"], between)
    assert [(q.lab.id, q.rate.id) for q in then] == [(lab.id, first.id)]
    # A lab no longer in use, or one that stopped doing the test, is not offered.
    service.update_lab(
        seeded, admin, other.id, service.LabInput(other.name, is_active=False), other.row_version
    )
    service.end_rate(seeded, admin, lab.id, second.id)
    assert service.quotes_for(seeded, admin, ids["vitd"]) == []
    with pytest.raises(NotFoundError):
        service.end_rate(seeded, admin, lab.id, second.id)
    with pytest.raises(NotFoundError):
        service.end_rate(seeded, admin, other.id, first.id)


@pytest.mark.item("M10")
@pytest.mark.parametrize(
    ("code", "cost", "hours", "field"),
    [
        ("", "700", "48", "test_code"),
        ("nosuch", "700", "48", "test_code"),
        ("vitd", "", "48", "cost"),
        ("vitd", "-1", "48", "cost"),
        ("vitd", "7.005", "48", "cost"),
        ("vitd", "NaN", "48", "cost"),
        ("vitd", "700", "0", "tat_hours"),
        ("vitd", "700", "two", "tat_hours"),
        ("vitd", "700", "9999", "tat_hours"),
    ],
)
def test_a_rate_needs_a_test_a_cost_and_hours(
    seeded: Session, platform: Platform, code: str, cost: str, hours: str, field: str
) -> None:
    admin = as_user(seeded, platform, "anil")
    menu(seeded, admin)
    lab = service.create_lab(seeded, admin, service.LabInput("Synthetic Referral Lab"))
    assert set(_problems(lambda: service.set_rate(seeded, admin, lab.id, code, cost, hours))) == {
        field
    }
    assert seeded.scalar(select(ExternalLabRate.id)) is None


@pytest.mark.item("M10")
def test_who_may_see_and_change_external_labs(seeded: Session, platform: Platform) -> None:
    admin = as_user(seeded, platform, "anil")
    lab = service.create_lab(seeded, admin, service.LabInput("Synthetic Referral Lab"))
    technician = as_user(seeded, platform, "suresh")
    assert service.get_lab(seeded, technician, lab.id) is lab
    assert service.lab_page(seeded, technician, 1).items == [lab]
    for call in (
        lambda: service.create_lab(seeded, technician, service.LabInput("Synthetic Other")),
        lambda: service.update_lab(seeded, technician, lab.id, service.LabInput("X"), 1),
        lambda: service.set_rate(seeded, technician, lab.id, "vitd", "1", "1"),
        lambda: service.end_rate(seeded, technician, lab.id, lab.id),
        lambda: service.lab_page(seeded, as_user(seeded, platform, "priya"), 1),
        lambda: service.quotes_for(seeded, as_user(seeded, platform, "priya"), lab.id),
    ):
        with pytest.raises(PermissionDeniedError):
            call()


@pytest.mark.item("M10")
def test_external_lab_screens(seeded: Session, platform: Platform, db_client: TestClient) -> None:
    menu(seeded, as_user(seeded, platform, "anil"))
    sign_in(db_client, "anil")
    assert "No external labs yet." in db_client.get("/admin/external-labs").text
    assert ">External labs</a>" in db_client.get("/").text
    new = {"name": "Synthetic Referral Lab", "dpa_signed_on": "2026-10-01"}
    saved = post(db_client, "/admin/external-labs", new)
    assert saved.status_code == 303
    lab = seeded.scalars(select(ExternalLab)).one()
    url = f"/admin/external-labs/{lab.id}"
    assert saved.headers["location"] == url
    assert lab.dpa_signed_on == date(2026, 10, 1) and lab.is_active
    listing = db_client.get("/admin/external-labs").text
    assert "Synthetic Referral Lab" in listing and "Signed 01 Oct 2026" in listing

    form = db_client.get(url).text
    assert "No tests yet." in form and 'name="share_phone"' in form
    rate = {"test_code": "vitd", "cost": "700", "tat_hours": "48", "their_test_code": "VD25"}
    assert post(db_client, f"{url}/rates", rate).status_code == 303
    assert post(db_client, f"{url}/rates", {**rate, "cost": "650"}).status_code == 303
    form = db_client.get(url).text
    assert "650.00" in form and "Earlier costs" in form and "VD25" in form
    bad = post(db_client, f"{url}/rates", {**rate, "test_code": "nosuch", "cost": "x"})
    assert bad.status_code == 422
    assert "No test has this code." in bad.text and 'value="nosuch"' in bad.text
    open_rate = seeded.scalars(
        select(ExternalLabRate).where(ExternalLabRate.valid_to.is_(None))
    ).one()
    assert post(db_client, f"{url}/rates/{open_rate.id}/end", {}).status_code == 303
    assert "No tests yet." in db_client.get(url).text

    edit = {
        "name": lab.name,
        "share_address": "on",
        "lab_id": str(lab.id),
        "row_version": str(lab.row_version),
    }
    assert post(db_client, "/admin/external-labs", edit).status_code == 303
    seeded.refresh(lab)
    assert lab.share_address and not lab.is_active and lab.dpa_signed_on is None
    assert "Not in use" in db_client.get("/admin/external-labs").text
    assert post(db_client, "/admin/external-labs", edit).status_code == 409
    wrong = post(db_client, "/admin/external-labs", {"name": " ", "dpa_signed_on": "soon"})
    assert wrong.status_code == 422
    assert "Enter a date." in wrong.text
    assert db_client.get("/admin/external-labs/not-an-id").status_code == 404


@pytest.mark.item("M10")
def test_external_lab_screens_by_role(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    admin = as_user(seeded, platform, "anil")
    lab = service.create_lab(seeded, admin, service.LabInput("Synthetic Referral Lab"))
    # A technician sees the lab and its costs but has nothing to change.
    sign_in(db_client, "suresh")
    seen = db_client.get(f"/admin/external-labs/{lab.id}")
    assert seen.status_code == 200
    assert "<form" not in seen.text.split('class="page-head"')[1]
    assert "Add lab" not in db_client.get("/admin/external-labs").text
    assert db_client.get("/admin/external-labs/new").status_code == 403
    assert post(db_client, "/admin/external-labs", {"name": "Synthetic Other"}).status_code == 403
    # The front desk has no business with it.
    sign_in(db_client, "priya")
    assert db_client.get("/admin/external-labs").status_code == 403
    assert ">External labs</a>" not in db_client.get("/").text


@pytest.mark.item("M10")
def test_demo_seed_has_two_labs_with_different_costs(db: Session, platform: Platform) -> None:
    for _ in range(2):  # seeding again adds nothing
        seed(db, platform.identity, SEED_DAY, with_catalog=True)
    admin = as_user(db, platform, "anil")
    vitd = db.scalars(select(Test.id).where(Test.code == "vitd")).one()
    quotes = service.quotes_for(db, admin, vitd)
    assert [q.lab.name for q in quotes] == ["Demo Referral Lab B", "Demo Referral Lab A"]
    assert len({q.rate.cost for q in quotes}) == len(DEMO_EXTERNAL_LABS) == 2
