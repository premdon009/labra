"""Who does a test, samples arriving at the lab, and the bill that can no longer be cancelled."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.billing import service as billing
from labra.billing.models import Bill
from labra.catalog.models import Test
from labra.core import lab_settings
from labra.core.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from labra.core.ids import utcnow
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.extlabs import service as extlabs
from labra.extlabs.models import ExternalLab
from labra.patients.models import Patient
from labra.results import service
from labra.results.models import OrderTestEvent
from labra.visits import service as visits
from labra.visits.models import OrderTest, Sample, Visit
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, branch, menu, post, sign_in, visit_input


def _ids(db: Session, platform: Platform) -> dict[str, uuid.UUID]:
    """The small catalog's test ids by code; made on first use."""
    found = {row.code: row.id for row in db.execute(select(Test.code, Test.id))}
    return found or dict(menu(db, as_user(db, platform, "anil")))


def _visit(db: Session, platform: Platform, username: str, *codes: str) -> Visit:
    data = visit_input(_ids(db, platform), *codes)
    return visits.save_visit(db, as_user(db, platform, username), data, SEED_DAY)


def _tests(db: Session, visit: Visit) -> list[OrderTest]:
    return list(db.scalars(select(OrderTest).where(OrderTest.visit_id == visit.id)))


def _sample(db: Session, visit: Visit) -> Sample:
    """The visit's only sample."""
    return db.scalars(select(Sample).where(Sample.visit_id == visit.id)).one()


def _collect(db: Session, by: Principal, sample: Sample) -> None:
    visits.collect_sample(db, by, sample.sample_no, by.user_id)


def _lab(db: Session, admin: Principal, name: str, cost: str, hours: int) -> ExternalLab:
    lab = extlabs.create_lab(db, admin, extlabs.LabInput(name), SEED_DAY)
    extlabs.set_rate(db, admin, lab.id, "vitd", cost, hours)
    return lab


def _problem(call) -> str:
    with pytest.raises(ValidationFailedError) as refused:
        call()
    return " ".join(refused.value.errors.values())


@pytest.mark.item("M11.3")
def test_a_sample_from_another_branch_is_in_the_lab_only_after_the_scan(
    seeded: Session, platform: Platform
) -> None:
    visit = _visit(seeded, platform, "priya", "lipid", "vitd")
    sample = _sample(seeded, visit)
    priya = as_user(seeded, platform, "priya")
    suresh = as_user(seeded, platform, "suresh")

    assert "isn't marked as collected yet" in _problem(
        lambda: service.receive_sample(seeded, suresh, sample.sample_no)
    )
    _collect(seeded, priya, sample)
    assert {t.status for t in _tests(seeded, visit)} == {"collected"}

    at = utcnow()
    service.receive_sample(seeded, suresh, f" {sample.sample_no.lower()} ", at)

    assert {t.status for t in _tests(seeded, visit)} == {"in_lab"}
    assert (sample.status, sample.received_at, sample.received_by) == (
        "received",
        at,
        suresh.user_id,
    )
    events = seeded.scalars(select(OrderTestEvent)).all()
    assert [(e.event, e.by, e.at) for e in events] == [("received", suresh.user_id, at)] * 2
    logged = seeded.scalars(select(AuditLog).where(AuditLog.action == "sample.receive")).one()
    assert logged.detail == {
        "sample_no": sample.sample_no,
        "visit_id": str(visit.id),
        "tests": 2,
    }
    assert logged.branch_id == branch(seeded, "MAIN").id

    assert "already in the lab" in _problem(
        lambda: service.receive_sample(seeded, suresh, sample.sample_no)
    )
    assert "No sample has the number" in _problem(
        lambda: service.receive_sample(seeded, suresh, "B2000000000000")
    )
    assert "Scan or type" in _problem(lambda: service.receive_sample(seeded, suresh, " "))
    # The front desk collects; it doesn't receive.
    with pytest.raises(PermissionDeniedError):
        service.receive_sample(seeded, priya, sample.sample_no)


@pytest.mark.item("M11.3")
def test_a_sample_is_received_only_where_its_tests_are_done(
    seeded: Session, platform: Platform
) -> None:
    visit = _visit(seeded, platform, "b3desk", "fbs")
    sample = _sample(seeded, visit)
    kavya = as_user(seeded, platform, "b3desk")
    (ordered,) = _tests(seeded, visit)
    service.route_test(
        seeded, kavya, ordered.id, ordered.row_version, branch_id=branch(seeded, "B3").id
    )
    lab_settings.set_value(seeded, "lab.receive_step", "always", kavya.user_id)
    _collect(seeded, kavya, sample)
    assert ordered.status == "collected"

    assert "no test that is done at this branch" in _problem(
        lambda: service.receive_sample(
            seeded, as_user(seeded, platform, "suresh"), sample.sample_no
        )
    )

    cancelled = _visit(seeded, platform, "priya", "urine")
    bill = seeded.scalars(select(Bill).where(Bill.visit_id == cancelled.id)).one()
    billing.cancel_bill(
        seeded, as_user(seeded, platform, "anil"), bill.id, "Booked twice", True, bill.row_version
    )
    assert "was cancelled with its bill" in _problem(
        lambda: service.receive_sample(
            seeded, as_user(seeded, platform, "suresh"), _sample(seeded, cancelled).sample_no
        )
    )


@pytest.mark.item("M11.3")
@pytest.mark.parametrize(
    ("step", "kept_at_branch", "sent_to_main"),
    [
        ("other_branches", "in_lab", "collected"),
        ("always", "collected", "collected"),
        ("never", "in_lab", "in_lab"),
    ],
)
def test_the_receive_step_setting_decides_which_samples_wait_for_a_scan(
    seeded: Session, platform: Platform, step: str, kept_at_branch: str, sent_to_main: str
) -> None:
    kavya = as_user(seeded, platform, "b3desk")
    assert lab_settings.get_value(seeded, "lab.receive_step") == "other_branches"
    lab_settings.set_value(seeded, "lab.receive_step", step, kavya.user_id)
    kept = _visit(seeded, platform, "b3desk", "fbs")
    (ordered,) = _tests(seeded, kept)
    service.route_test(
        seeded, kavya, ordered.id, ordered.row_version, branch_id=branch(seeded, "B3").id
    )
    sent = _visit(seeded, platform, "b3desk", "urine")

    _collect(seeded, kavya, _sample(seeded, kept))
    _collect(seeded, kavya, _sample(seeded, sent))

    assert ordered.status == kept_at_branch
    assert _tests(seeded, sent)[0].status == sent_to_main
    # Collecting never marks the sample as received; only the scan does.
    assert _sample(seeded, kept).status == "collected"


@pytest.mark.item("M09")
def test_a_collection_centre_keeps_a_test_and_can_hand_it_back(
    seeded: Session, platform: Platform
) -> None:
    visit = _visit(seeded, platform, "b3desk", "fbs")
    (ordered,) = _tests(seeded, visit)
    kavya = as_user(seeded, platform, "b3desk")
    main, b2, b3 = (branch(seeded, code) for code in ("MAIN", "B2", "B3"))
    assert ordered.perform_branch_id == main.id

    # Front desk staff of another branch can't route, and an old copy is refused.
    with pytest.raises(PermissionDeniedError):
        service.route_test(
            seeded, as_user(seeded, platform, "priya"), ordered.id, ordered.row_version
        )
    with pytest.raises(ConflictError):
        service.route_test(seeded, kavya, ordered.id, ordered.row_version + 1, branch_id=b3.id)
    assert "main lab or at the branch that took the sample" in _problem(
        lambda: service.route_test(seeded, kavya, ordered.id, ordered.row_version, branch_id=b2.id)
    )
    assert "at most 200" in _problem(
        lambda: service.route_test(
            seeded, kavya, ordered.id, ordered.row_version, branch_id=b3.id, reason="x" * 201
        )
    )

    at = utcnow()
    service.route_test(
        seeded,
        kavya,
        ordered.id,
        ordered.row_version,
        branch_id=b3.id,
        reason=" Glucometer here ",
        now=at,
    )

    assert (ordered.route, ordered.perform_branch_id) == ("in_house", b3.id)
    assert (ordered.route_reason, ordered.routed_by, ordered.routed_at) == (
        "Glucometer here",
        kavya.user_id,
        at,
    )
    event = seeded.scalars(select(OrderTestEvent)).one()
    assert (event.event, event.note) == ("routed", "In-house at B3. Glucometer here")
    logged = seeded.scalars(select(AuditLog).where(AuditLog.action == "test.route")).one()
    assert logged.detail["perform_branch_id"] == str(b3.id)
    assert logged.detail["test"] == "fbs" and logged.detail["external_lab_id"] is None

    # Kept and collected at the same branch, it is in the lab without a scan. Handed back
    # to the main lab after that, it waits for the main lab's scan.
    sample = _sample(seeded, visit)
    _collect(seeded, kavya, sample)
    assert ordered.status == "in_lab"
    service.route_test(seeded, kavya, ordered.id, ordered.row_version)
    assert (ordered.perform_branch_id, ordered.status) == (main.id, "collected")
    service.receive_sample(seeded, as_user(seeded, platform, "suresh"), sample.sample_no)
    assert ordered.status == "in_lab"


@pytest.mark.item("M09")
def test_a_test_goes_to_an_outside_lab_at_that_labs_rate(
    seeded: Session, platform: Platform
) -> None:
    admin = as_user(seeded, platform, "anil")
    visit = _visit(seeded, platform, "priya", "vitd", "fbs")
    dear = _lab(seeded, admin, "Synthetic Referral Lab A", "700", 48)
    no_rate = extlabs.create_lab(seeded, admin, extlabs.LabInput("Synthetic Referral Lab C"))
    suresh = as_user(seeded, platform, "suresh")
    by_code = {t.test_id: t for t in _tests(seeded, visit)}
    ids = _ids(seeded, platform)
    vitd, fbs = by_code[ids["vitd"]], by_code[ids["fbs"]]
    booked_due = vitd.due_at

    assert "has no rate for the test" in _problem(
        lambda: service.route_test(
            seeded, suresh, vitd.id, vitd.row_version, external_lab_id=no_rate.id
        )
    )
    # The lab does vitamin D, not blood sugar.
    assert "has no rate for the test" in _problem(
        lambda: service.route_test(seeded, suresh, fbs.id, fbs.row_version, external_lab_id=dear.id)
    )

    at = utcnow()
    service.route_test(seeded, suresh, vitd.id, vitd.row_version, external_lab_id=dear.id, now=at)

    assert (vitd.route, vitd.external_lab_id, vitd.external_cost) == (
        "external",
        dear.id,
        Decimal("700.00"),
    )
    assert vitd.due_at == at + timedelta(hours=48)
    assert vitd.perform_branch_id == branch(seeded, "MAIN").id
    event = seeded.scalars(select(OrderTestEvent)).one()
    assert (event.event, event.note) == ("routed", "To Synthetic Referral Lab A")
    logged = seeded.scalars(select(AuditLog).where(AuditLog.action == "test.route")).one()
    assert logged.detail["route"] == "external" and logged.detail["external_cost"] == "700.00"
    # The patient is in the audit row by visit only.
    patient = seeded.get_one(Patient, visit.patient_id)
    assert patient.full_name not in str(logged.detail) and patient.phone not in str(logged.detail)

    # A later rate change doesn't touch what was agreed for this test.
    extlabs.set_rate(seeded, admin, dear.id, "vitd", "900", 48)
    assert vitd.external_cost == Decimal("700.00")

    # Back in-house: no lab, no cost, and due when it was first promised.
    service.route_test(seeded, suresh, vitd.id, vitd.row_version)
    assert (vitd.route, vitd.external_lab_id, vitd.external_cost) == ("in_house", None, None)
    assert vitd.due_at == booked_due

    # Once it has left the building it stays where it is.
    service.route_test(seeded, suresh, vitd.id, vitd.row_version, external_lab_id=dear.id)
    vitd.status = "sent_out"
    seeded.flush()
    with pytest.raises(ConflictError, match="can't be moved any more"):
        service.route_test(seeded, suresh, vitd.id, vitd.row_version)


@pytest.mark.item("M11.3")
def test_receive_screen_shows_name_age_sex_and_tests_never_the_phone(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _visit(seeded, platform, "priya", "lipid", "vitd")
    sample = _sample(seeded, visit)
    patient = seeded.get_one(Patient, visit.patient_id)
    _collect(seeded, as_user(seeded, platform, "priya"), sample)

    sign_in(db_client, "priya")
    assert 'href="/lab/receive"' not in db_client.get("/").text
    assert db_client.get("/lab/receive", headers={"accept": "text/html"}).status_code == 403

    sign_in(db_client, "suresh")
    assert 'href="/lab/receive"' in db_client.get("/").text
    screen = db_client.get("/lab/receive").text
    # The scanner types into the box and sends Enter, which submits this plain form.
    assert 'name="sample_no" value="" autofocus' in screen
    assert "/manual/lab/receiving-samples/" in screen or "lab/receiving-samples" in screen

    wrong = post(db_client, "/lab/receive", {"sample_no": "B2999"})
    assert wrong.status_code == 422 and "No sample has the number B2999." in wrong.text

    done = post(db_client, "/lab/receive", {"sample_no": sample.sample_no})
    assert done.status_code == 303
    assert done.headers["location"] == f"/lab/receive?done={sample.sample_no}"
    shown = db_client.get(done.headers["location"]).text
    assert f"In the lab: {sample.sample_no}" in shown
    assert patient.full_name in shown and "LIPID, VITD" in shown
    assert "Male" in shown or "Female" in shown or "Other" in shown
    assert "From B2, received" in shown
    assert patient.phone and patient.phone not in shown
    assert 'name="sample_no" value="" autofocus' in shown

    again = post(db_client, "/lab/receive", {"sample_no": sample.sample_no})
    assert again.status_code == 422 and "is already in the lab" in again.text


@pytest.mark.item("M07.4")
@pytest.mark.parametrize("status", ["sent_out", "resulted", "verified", "released"])
def test_a_bill_cant_be_cancelled_once_a_test_was_sent_out_or_has_a_result(
    seeded: Session, platform: Platform, db_client: TestClient, status: str
) -> None:
    visit = _visit(seeded, platform, "priya", "fbs", "vitd")
    bill = seeded.scalars(select(Bill).where(Bill.visit_id == visit.id)).one()
    admin = as_user(seeded, platform, "anil")
    first = _tests(seeded, visit)[0]
    first.status = status
    seeded.flush()

    with pytest.raises(ConflictError, match="can't be cancelled"):
        billing.cancel_bill(seeded, admin, bill.id, "Booked twice", True, bill.row_version)

    seeded.refresh(bill)
    assert bill.status != "cancelled" and bill.cancelled_at is None
    assert seeded.get_one(Visit, visit.id).status != "cancelled"
    assert {t.status for t in _tests(seeded, visit)} == {status, "ordered"}

    sign_in(db_client, "anil")
    form = db_client.get(f"/frontdesk/bills/{bill.id}/cancel").text
    assert "This bill can't be cancelled" in form and 'name="confirm"' not in form
    sent = post(
        db_client,
        f"/frontdesk/bills/{bill.id}/cancel",
        {"reason": "Booked twice", "confirm": "yes", "row_version": bill.row_version},
    )
    assert sent.status_code == 409

    # Until then, cancelling works as before.
    first.status = "in_lab"
    seeded.flush()
    billing.cancel_bill(seeded, admin, bill.id, "Booked twice", True, bill.row_version)
    assert bill.status == "cancelled"
    assert {t.status for t in _tests(seeded, visit)} == {"cancelled"}
