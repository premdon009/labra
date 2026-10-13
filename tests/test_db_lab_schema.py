"""The lab tables: where a test is done, the external-lab check, append-only history, and
who may do what at the bench."""

import uuid
from decimal import Decimal
from importlib import import_module

import pytest
from sqlalchemy import func, select, table, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from labra.catalog.models import TestParameter
from labra.core.ids import utcnow
from labra.core.models import StoredFile
from labra.core.registry import Platform
from labra.extlabs.models import ExternalLab, ExternalLabRate
from labra.org.permissions import PERMISSIONS, SYSTEM_ROLES
from labra.results.models import (
    CriticalNotification,
    ExternalDocument,
    ExternalDocumentTest,
    OrderTestEvent,
    Result,
    ResultRevision,
    Verification,
)
from labra.visits import service as visits
from labra.visits.models import OrderTest
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, branch, menu, visit_input

# Each append-only table, with a column to try changing.
APPEND_ONLY = (
    ("verification", "note"),
    ("result_revision", "reason"),
    ("critical_notification", "informed_to"),
    ("external_document", "match_status"),
    ("external_document_test", "order_test_id"),
    ("order_test_event", "note"),
)


def _ordered(db: Session, platform: Platform, *codes: str) -> tuple[list[OrderTest], uuid.UUID]:
    """Tests ordered at Branch 2, and the id of the user who booked them."""
    ids = menu(db, as_user(db, platform, "anil"))
    priya = as_user(db, platform, "priya")
    visit = visits.save_visit(db, priya, visit_input(ids, *codes), SEED_DAY)
    tests = db.scalars(select(OrderTest).where(OrderTest.visit_id == visit.id)).all()
    return list(tests), priya.user_id


def _lab(db: Session, name: str = "Synthetic Referral Lab") -> ExternalLab:
    lab = ExternalLab(name=name)
    db.add(lab)
    db.flush()
    return lab


@pytest.fixture
def history(seeded: Session, platform: Platform) -> OrderTest:
    """One ordered test with a row in every append-only lab table."""
    (ordered,), user_id = _ordered(seeded, platform, "fbs")
    parameter = TestParameter(
        test_id=ordered.test_id, code="val", name="Value", result_type="numeric"
    )
    seeded.add(parameter)
    seeded.flush()
    result = Result(order_test_id=ordered.id, parameter_id=parameter.id, value_num=Decimal(30))
    stored = StoredFile(
        sha256="0" * 64, storage_key="synthetic", size=1, filename="r.pdf", mime="application/pdf"
    )
    seeded.add_all([result, stored])
    seeded.flush()
    document = ExternalDocument(
        visit_id=ordered.visit_id,
        external_lab_id=_lab(seeded).id,
        file_id=stored.id,
        sha256=stored.sha256,
        received_by=user_id,
    )
    seeded.add(document)
    seeded.flush()
    seeded.add_all(
        [
            Verification(order_test_id=ordered.id, verified_by=user_id),
            ResultRevision(result_id=result.id, reason="Typing slip", changed_by=user_id),
            CriticalNotification(
                result_id=result.id,
                reported_value="30",
                reported_flag="LL",
                informed_to="Dr Synthetic",
                mode="phone",
                informed_at=utcnow(),
                recorded_by=user_id,
            ),
            ExternalDocumentTest(external_document_id=document.id, order_test_id=ordered.id),
            OrderTestEvent(order_test_id=ordered.id, event="resulted", by=user_id),
        ]
    )
    seeded.flush()
    return ordered


@pytest.mark.item("M11")
@pytest.mark.item("M21")
@pytest.mark.parametrize(("name", "column"), APPEND_ONLY)
@pytest.mark.parametrize(
    "statement", ["update {t} set {c} = {c}", "delete from {t}", "truncate {t} cascade"]
)
def test_lab_history_is_append_only(
    seeded: Session, history: OrderTest, name: str, column: str, statement: str
) -> None:
    assert seeded.scalar(select(func.count()).select_from(table(name))) == 1
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(text(statement.format(t=name, c=column)))


@pytest.mark.item("M11")
def test_a_changed_result_needs_a_reason_and_a_notification_a_name(
    seeded: Session, history: OrderTest
) -> None:
    result = seeded.scalars(select(Result)).one()
    user_id = seeded.scalars(select(Verification.verified_by)).one()
    with pytest.raises(IntegrityError, match="ck_result_revision_reason"), seeded.begin_nested():
        seeded.add(ResultRevision(result_id=result.id, reason="  ", changed_by=user_id))
        seeded.flush()
    blank = CriticalNotification(
        result_id=result.id,
        reported_value="30",
        reported_flag="LL",
        informed_to=" ",
        mode="phone",
        informed_at=utcnow(),
        recorded_by=user_id,
    )
    with (
        pytest.raises(IntegrityError, match="ck_critical_notification_informed_to"),
        seeded.begin_nested(),
    ):
        seeded.add(blank)
        seeded.flush()


@pytest.mark.item("M11")
def test_one_result_per_parameter_of_a_test(seeded: Session, history: OrderTest) -> None:
    first = seeded.scalars(select(Result)).one()
    again = Result(order_test_id=first.order_test_id, parameter_id=first.parameter_id)
    with (
        pytest.raises(IntegrityError, match="uq_result_order_test_id_parameter_id"),
        seeded.begin_nested(),
    ):
        seeded.add(again)
        seeded.flush()


@pytest.mark.item("M09")
def test_a_test_ordered_at_a_branch_is_done_at_the_main_lab(
    seeded: Session, platform: Platform
) -> None:
    tests, _ = _ordered(seeded, platform, "fbs", "lipid")
    main = branch(seeded, "MAIN")
    assert {t.perform_branch_id for t in tests} == {main.id}
    assert {t.route for t in tests} == {"in_house"}

    # Rows from before the column existed are sent the same way by the upgrade.
    migration = import_module("labra.migrations.versions.0006_lab")
    b2 = branch(seeded, "B2")
    seeded.execute(text("update order_test set perform_branch_id = :b"), {"b": b2.id})
    seeded.execute(text(migration.BACKFILL_PERFORM_BRANCH))
    seeded.expire_all()
    assert {t.perform_branch_id for t in tests} == {main.id}
    # A lab with no main lab yet keeps them where they were ordered.
    seeded.execute(text("update branch set kind = 'collection_centre'"))
    seeded.execute(text(migration.BACKFILL_PERFORM_BRANCH))
    seeded.expire_all()
    assert {t.perform_branch_id for t in tests} == {b2.id}


@pytest.mark.item("M09")
def test_an_external_test_names_its_lab_and_an_in_house_one_has_none(
    seeded: Session, platform: Platform
) -> None:
    (ordered,), _ = _ordered(seeded, platform, "vitd")
    lab = _lab(seeded)
    for route, lab_id in (("external", None), ("in_house", lab.id), ("courier", None)):
        with pytest.raises(IntegrityError, match="ck_order_test_route"), seeded.begin_nested():
            seeded.execute(
                text("update order_test set route = :r, external_lab_id = :l where id = :id"),
                {"r": route, "l": lab_id, "id": ordered.id},
            )
    ordered.route, ordered.external_lab_id, ordered.external_cost = "external", lab.id, Decimal(700)
    seeded.flush()


@pytest.mark.item("M10")
def test_a_lab_has_one_open_rate_per_test(seeded: Session, platform: Platform) -> None:
    (ordered,), _ = _ordered(seeded, platform, "vitd")
    lab = _lab(seeded)
    assert (lab.share_phone, lab.share_address) == (False, False)

    def rate(cost: str, hours: int = 48) -> ExternalLabRate:
        return ExternalLabRate(
            external_lab_id=lab.id,
            test_id=ordered.test_id,
            cost=Decimal(cost),
            tat_hours=hours,
            valid_from=utcnow(),
        )

    seeded.add(rate("700"))
    seeded.flush()
    with pytest.raises(IntegrityError, match="uq_external_lab_rate_open"), seeded.begin_nested():
        seeded.add(rate("650"))
        seeded.flush()
    for bad, name in ((rate("-1"), "cost"), (rate("700", 0), "tat_hours")):
        bad.external_lab_id = _lab(seeded, f"Synthetic lab {name}").id
        with (
            pytest.raises(IntegrityError, match=f"ck_external_lab_rate_{name}"),
            seeded.begin_nested(),
        ):
            seeded.add(bad)
            seeded.flush()


@pytest.mark.item("M11")
@pytest.mark.item("M09")
@pytest.mark.item("M10")
@pytest.mark.item("M11.3")
@pytest.mark.parametrize(
    ("permission", "roles"),
    [
        ("result.enter", {"technician", "signatory"}),
        ("result.verify", {"signatory"}),
        ("test.route", {"technician", "branch_manager", "admin"}),
        ("sample.receive", {"technician", "phlebotomist"}),
        ("extlab.view", {"technician", "branch_manager", "admin"}),
        ("extlab.edit", {"admin"}),
    ],
)
def test_lab_permissions_by_role(permission: str, roles: set[str]) -> None:
    assert permission in PERMISSIONS
    assert {r.code for r in SYSTEM_ROLES.values() if permission in r.permissions} == roles
