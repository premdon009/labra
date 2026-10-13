"""Standing behind results: submit, the critical-value log, verify and reopen; and the list
that says where a test can be done, with its cost and margin."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from labra.core.errors import ConflictError, PermissionDeniedError
from labra.core.ids import utcnow
from labra.core.models import AuditLog, Consent, EventOutbox
from labra.core.registry import Platform
from labra.extlabs import service as extlabs
from labra.patients.models import Patient
from labra.results import service, signoff, worklist
from labra.results.models import (
    CriticalNotification,
    OrderTestEvent,
    ResultRevision,
    Verification,
)
from labra.seed import seed
from labra.visits.models import OrderTest, Visit
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, post, sign_in
from tests.test_db_lab_entry import (
    _approve,
    _enter,
    _in_lab,
    _param,
    _problem,
    _range,
    _result,
)
from tests.test_db_lab_routing import _lab, _tests, _visit

NORMAL: dict[str, Any] = {"TC": 180, "TG": 150, "HDL": 45}


@pytest.fixture
def lab(db: Session, platform: Platform) -> Session:
    """The demo cast and starter catalog; total cholesterol of 400 or more is critical."""
    seed(db, platform.identity, SEED_DAY, with_catalog=True)
    _approve(db, platform, "lipid")
    _range(db, "lipid", "TC").critical_high = Decimal(400)
    db.flush()
    return db


def _inform(db: Session, platform: Platform, ordered: OrderTest, code: str = "TC", **changes):
    result = _result(db, ordered, code)
    assert result is not None
    values = {"informed_to": "Dr Kavya Testcase", "mode": "phone", **changes}
    return signoff.log_critical(db, as_user(db, platform, "suresh"), result.id, **values)


def _events(db: Session, ordered: OrderTest) -> list[str]:
    return list(
        db.scalars(
            select(OrderTestEvent.event)
            .where(OrderTestEvent.order_test_id == ordered.id)
            .order_by(OrderTestEvent.at, OrderTestEvent.id)
        )
    )


@pytest.mark.item("M11")
def test_results_go_to_the_signatory_and_only_the_signatory_verifies(
    lab: Session, platform: Platform
) -> None:
    ordered = _in_lab(lab, platform)
    suresh, meera = as_user(lab, platform, "suresh"), as_user(lab, platform, "meera")

    assert "at least one value" in _problem(
        lambda: signoff.submit(lab, suresh, ordered.id, ordered.row_version)
    )
    _enter(lab, platform, ordered, TC=180)
    for username in ("priya", "anil"):
        with pytest.raises(PermissionDeniedError):
            signoff.submit(lab, as_user(lab, platform, username), ordered.id, ordered.row_version)
    # Rows may still be empty: the test goes on with what it has.
    signoff.submit(lab, suresh, ordered.id, ordered.row_version)
    assert ordered.status == "resulted"

    # A value changed after that takes the test back, so nothing unseen is verified.
    seen = ordered.row_version
    _enter(lab, platform, ordered, TC=185)
    assert ordered.status == "in_lab"
    with pytest.raises(ConflictError):
        signoff.verify(lab, meera, ordered.id, seen)
    with pytest.raises(ConflictError, match="isn't waiting for verification"):
        signoff.verify(lab, meera, ordered.id, ordered.row_version)
    signoff.submit(lab, suresh, ordered.id, ordered.row_version)

    # The technician and the administrator can't sign.
    for username in ("suresh", "anil", "priya"):
        with pytest.raises(PermissionDeniedError):
            signoff.verify(lab, as_user(lab, platform, username), ordered.id, ordered.row_version)
    signed = signoff.verify(lab, meera, ordered.id, ordered.row_version)

    assert ordered.status == "verified"
    assert lab.scalars(select(Verification)).one().id == signed.id
    assert (signed.verified_by, signed.level) == (meera.user_id, 1)
    assert _events(lab, ordered)[-3:] == ["resulted", "resulted", "verified"]
    logged = lab.scalars(select(AuditLog).where(AuditLog.action == "result.verify")).one()
    assert logged.entity_id == str(ordered.id)
    # Verified values are closed.
    with pytest.raises(ConflictError, match="is verified"):
        _enter(lab, platform, ordered, TC=190)
    with pytest.raises(ConflictError):
        signoff.submit(lab, suresh, ordered.id, ordered.row_version)


@pytest.mark.item("M26")
def test_verifying_queues_an_event_with_ids_only(lab: Session, platform: Platform) -> None:
    ordered = _in_lab(lab, platform)
    suresh, meera = as_user(lab, platform, "suresh"), as_user(lab, platform, "meera")
    _enter(lab, platform, ordered, **NORMAL)
    signoff.submit(lab, suresh, ordered.id, ordered.row_version)
    signed = signoff.verify(lab, meera, ordered.id, ordered.row_version)

    event = lab.scalars(select(EventOutbox).where(EventOutbox.topic == "test.performed")).one()
    assert event.payload == {
        "schema_version": 1,
        "entity": "order_test",
        "entity_id": str(ordered.id),
        "visit_id": str(ordered.visit_id),
        "test_id": str(ordered.test_id),
        "branch_id": str(lab.get_one(Visit, ordered.visit_id).branch_id),
        "perform_branch_id": str(ordered.perform_branch_id),
        "route": "in_house",
        "external_lab_id": None,
        "verification_id": str(signed.id),
    }
    patient = lab.get_one(Patient, lab.get_one(Visit, ordered.visit_id).patient_id)
    assert patient.full_name not in str(event.payload) and patient.phone not in str(event.payload)

    # Verified again after a correction, it is sent again.
    signoff.reopen(lab, meera, ordered.id, ordered.row_version, "Repeat run")
    signoff.verify(lab, meera, ordered.id, ordered.row_version)
    sent = lab.scalars(select(EventOutbox).where(EventOutbox.topic == "test.performed")).all()
    assert len(sent) == 2 and len(lab.scalars(select(Verification)).all()) == 2


@pytest.mark.item("M11")
def test_a_critical_value_is_saved_but_goes_no_further_until_someone_is_informed(
    lab: Session, platform: Platform
) -> None:
    ordered = _in_lab(lab, platform)
    suresh, meera = as_user(lab, platform, "suresh"), as_user(lab, platform, "meera")
    _enter(lab, platform, ordered, TC=410, TG=150, HDL=45)
    saved = _result(lab, ordered, "TC")
    assert saved is not None and (saved.flag, saved.value_num) == ("HH", Decimal(410))
    grid = {
        r.parameter.code: r
        for r in worklist.test_block(lab, suresh, worklist.load_sheet(lab, ordered.id)).rows
    }
    assert (grid["TC"].state, grid["TC"].must_inform, grid["TC"].can_inform) == (
        "critical",
        True,
        True,
    )
    assert [e.parameter_name for e in worklist.critical_waiting(lab, suresh)] == [
        grid["TC"].parameter.name
    ]

    refused = _problem(lambda: signoff.submit(lab, suresh, ordered.id, ordered.row_version))
    assert "nobody on record as informed" in refused
    assert ordered.status == "in_lab"

    # Who, how and when; the when can't be ahead of the clock or before the visit.
    assert "who was informed" in _problem(lambda: _inform(lab, platform, ordered, informed_to=" "))
    assert "how they were informed" in _problem(lambda: _inform(lab, platform, ordered, mode="fax"))
    assert "in digits" in _problem(lambda: _inform(lab, platform, ordered, phone="call him"))
    later = utcnow() + timedelta(hours=1)
    assert "future" in _problem(lambda: _inform(lab, platform, ordered, informed_at=later))
    long_ago = utcnow() - timedelta(days=30)
    assert "before the visit" in _problem(
        lambda: _inform(lab, platform, ordered, informed_at=long_ago)
    )
    with pytest.raises(PermissionDeniedError):
        signoff.log_critical(
            lab, as_user(lab, platform, "priya"), saved.id, informed_to="Dr K", mode="phone"
        )
    # A value that isn't critical has no log.
    with pytest.raises(ConflictError, match="isn't critical"):
        _inform(lab, platform, ordered, "HDL")

    note = _inform(lab, platform, ordered, phone="98765 00000")
    assert (note.reported_value, note.reported_flag, note.phone, note.recorded_by) == (
        "410",
        "HH",
        "9876500000",
        suresh.user_id,
    )
    logged = lab.scalars(select(AuditLog).where(AuditLog.action == "result.critical_inform")).one()
    # The audit trail says what was done; the doctor's name and number stay in the log.
    assert logged.detail["value"] == "410" and "Kavya" not in str(logged.detail)
    assert worklist.critical_waiting(lab, suresh) == []
    entry = worklist.critical_log(lab, suresh).items[0]
    assert (entry.value, entry.flag, entry.note, entry.patient_name) == (
        "410",
        "HH",
        note,
        "Sunita Testcase",
    )

    # Corrected to another critical value, it has to be reported again.
    _enter(lab, platform, ordered, TC=450)
    assert "nobody on record" in _problem(
        lambda: signoff.submit(lab, suresh, ordered.id, ordered.row_version)
    )
    _inform(lab, platform, ordered)
    signoff.submit(lab, suresh, ordered.id, ordered.row_version)

    # The same holds at the signatory's desk: a log entry that no longer matches blocks.
    lab.execute(update(OrderTest).where(OrderTest.id == ordered.id).values(status="resulted"))
    saved.value_num = Decimal(460)
    lab.flush()
    lab.refresh(ordered)
    assert "nobody on record" in _problem(
        lambda: signoff.verify(lab, meera, ordered.id, ordered.row_version)
    )
    assert ordered.status == "resulted"
    saved.value_num = Decimal(450)
    lab.flush()
    signoff.verify(lab, meera, ordered.id, ordered.row_version)
    assert ordered.status == "verified"
    # The log keeps both calls, each with the value that was read out.
    assert [n.reported_value for n in worklist_notes(lab)] == ["410", "450"]


def worklist_notes(db: Session) -> list[CriticalNotification]:
    return list(db.scalars(select(CriticalNotification).order_by(CriticalNotification.recorded_at)))


@pytest.mark.item("M11")
def test_a_verified_test_is_reopened_with_a_reason_and_keeps_what_it_said(
    lab: Session, platform: Platform
) -> None:
    ordered = _in_lab(lab, platform)
    suresh, meera = as_user(lab, platform, "suresh"), as_user(lab, platform, "meera")
    _enter(lab, platform, ordered, **NORMAL)
    signoff.submit(lab, suresh, ordered.id, ordered.row_version)
    # Nothing is kept about changes made before the first sign-off.
    _enter(lab, platform, ordered, TC=182)
    signoff.submit(lab, suresh, ordered.id, ordered.row_version)
    signoff.verify(lab, meera, ordered.id, ordered.row_version)
    assert lab.scalars(select(ResultRevision)).all() == []

    with pytest.raises(PermissionDeniedError):
        signoff.reopen(lab, suresh, ordered.id, ordered.row_version, "Typing slip")
    assert "Say why" in _problem(
        lambda: signoff.reopen(lab, meera, ordered.id, ordered.row_version, "  ")
    )
    signoff.reopen(lab, meera, ordered.id, ordered.row_version, "Typing slip in cholesterol")

    assert ordered.status == "resulted"
    reopened = lab.scalars(select(OrderTestEvent).where(OrderTestEvent.event == "reopened")).one()
    assert (reopened.note, reopened.by) == ("Typing slip in cholesterol", meera.user_id)
    logged = lab.scalars(select(AuditLog).where(AuditLog.action == "result.reopen")).one()
    assert logged.detail["reason"] == "Typing slip in cholesterol"
    with pytest.raises(ConflictError, match="Only a verified test"):
        signoff.reopen(lab, meera, ordered.id, ordered.row_version, "Again")

    _enter(lab, platform, ordered, TC=210)
    tc, ldl = _result(lab, ordered, "TC"), _result(lab, ordered, "LDL")
    assert tc is not None and ldl is not None
    kept = {r.result_id: r for r in lab.scalars(select(ResultRevision))}
    # The typed row and each calculated row that moved with it.
    assert (kept[tc.id].old_value_num, kept[tc.id].old_flag) == (Decimal(182), "N")
    assert kept[ldl.id].old_value_num == Decimal(107)
    assert {r.reason for r in kept.values()} == {"Typing slip in cholesterol"}
    assert {r.changed_by for r in kept.values()} == {suresh.user_id}
    # It has to be submitted and verified again.
    assert ordered.status == "in_lab"
    signoff.submit(lab, suresh, ordered.id, ordered.row_version)
    signoff.verify(lab, meera, ordered.id, ordered.row_version)
    assert ordered.status == "verified"


@pytest.mark.item("M09")
def test_the_routing_list_shows_each_labs_cost_and_margin(
    seeded: Session, platform: Platform
) -> None:
    admin, suresh = as_user(seeded, platform, "anil"), as_user(seeded, platform, "suresh")
    visit = _visit(seeded, platform, "priya", "vitd", "basic")
    dear = _lab(seeded, admin, "Synthetic Referral Lab A", "700", 48)
    cheap = _lab(seeded, admin, "Synthetic Referral Lab B", "650", 72)
    extlabs.set_rate(seeded, admin, cheap.id, "fbs", "30", 24)
    by_code = {worklist.load_sheet(seeded, t.id).test.code: t for t in _tests(seeded, visit)}

    def choices(code: str, principal=suresh) -> list[worklist.RouteChoice]:
        return worklist.route_choices(
            seeded, principal, worklist.load_sheet(seeded, by_code[code].id)
        )

    # A test on its own: what it was charged at, less what the lab charges; cheapest first.
    listed = choices("vitd")
    assert [(c.name, c.current, c.cost, c.margin, c.tat_hours) for c in listed] == [
        ("In-house at MAIN", True, None, None, None),
        ("In-house at B2", False, None, None, None),
        ("Synthetic Referral Lab B", False, Decimal("650.00"), Decimal("650.00"), 72),
        ("Synthetic Referral Lab A", False, Decimal("700.00"), Decimal("600.00"), 48),
    ]
    # A test inside a package: its share of the package's 500 by list price, 80 of 530.
    assert worklist.charged_for(seeded, by_code["fbs"]) == Decimal("75.47")
    assert worklist.charged_for(seeded, by_code["lipid"]) == Decimal("424.53")
    assert [(c.name, c.cost, c.margin) for c in choices("fbs") if c.cost is not None] == [
        ("Synthetic Referral Lab B", Decimal("30.00"), Decimal("45.47"))
    ]
    # The front desk can't move a test, so it is offered nothing.
    assert choices("vitd", as_user(seeded, platform, "priya")) == []

    vitd = by_code["vitd"]
    service.route_test(seeded, suresh, vitd.id, vitd.row_version, external_lab_id=dear.id)
    extlabs.set_rate(seeded, admin, dear.id, "vitd", "900", 48)
    # Where it is now keeps the cost it was sent at; the rate change shows for a new choice.
    assert [(c.name, c.current, c.cost) for c in choices("vitd") if c.current] == [
        ("Synthetic Referral Lab A", True, Decimal("700.00"))
    ]
    block = worklist.test_block(seeded, suresh, worklist.load_sheet(seeded, vitd.id))
    assert (block.lab_name, block.external_cost, block.margin) == (
        "Synthetic Referral Lab A",
        Decimal("700.00"),
        Decimal("600.00"),
    )
    # A test with a result stays where it is.
    vitd.status = "resulted"
    seeded.flush()
    assert choices("vitd") == []


@pytest.mark.item("M09")
def test_sending_out_without_sharing_consent_warns_and_can_record_it(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    admin, suresh = as_user(seeded, platform, "anil"), as_user(seeded, platform, "suresh")
    visit = _visit(seeded, platform, "priya", "vitd")
    lab = _lab(seeded, admin, "Synthetic Referral Lab A", "700", 48)
    vitd = _tests(seeded, visit)[0]
    # The patient agreed to testing only.
    sharing = seeded.scalars(select(Consent).where(Consent.purpose == "referral_lab_sharing")).one()
    sharing.withdrawn_at = utcnow()
    seeded.flush()
    assert not worklist.has_sharing_consent(seeded, visit.patient_id)

    sign_in(db_client, "suresh")
    page = db_client.get(f"/lab/visits/{visit.id}")
    assert page.status_code == 200
    assert "No consent to share with an outside lab" in page.text
    assert "Synthetic Referral Lab A: cost ₹700.00, margin ₹600.00, 48 h" in page.text

    # It is a warning: the test can still go.
    moved = post(
        db_client,
        f"/lab/tests/{vitd.id}/route",
        {"row_version": vitd.row_version, "to": f"lab:{lab.id}", "reason": "No kit"},
    )
    assert moved.status_code == 303 and moved.headers["location"].endswith(f"#t-{vitd.id}")
    seeded.refresh(vitd)
    assert (vitd.route, vitd.external_lab_id, vitd.route_reason) == ("external", lab.id, "No kit")
    routed = seeded.scalars(select(AuditLog).where(AuditLog.action == "test.route")).one()
    assert routed.detail["sharing_consent"] is False
    page = db_client.get(f"/lab/visits/{visit.id}")
    assert "outside lab: Synthetic Referral Lab A" in page.text
    assert "cost ₹700.00 · margin ₹600.00" in page.text

    assert post(db_client, f"/lab/visits/{visit.id}/sharing-consent", {}).status_code == 303
    given = seeded.scalars(
        select(Consent).where(
            Consent.purpose == "referral_lab_sharing", Consent.withdrawn_at.is_(None)
        )
    ).one()
    assert (given.subject_id, given.recorded_by) == (visit.patient_id, suresh.user_id)
    assert seeded.scalars(select(AuditLog).where(AuditLog.action == "consent.record")).one()
    assert "No consent to share" not in db_client.get(f"/lab/visits/{visit.id}").text
    # Once is enough.
    assert service.record_sharing_consent(seeded, suresh, visit.id) is False

    refused = post(
        db_client, f"/lab/tests/{vitd.id}/route", {"row_version": vitd.row_version, "to": "x"}
    )
    assert refused.status_code == 422 and "Pick where the test is done." in refused.text
    stale = post(
        db_client,
        f"/lab/tests/{vitd.id}/route",
        {"row_version": vitd.row_version - 1, "to": f"lab:{lab.id}"},
    )
    assert stale.status_code == 409
    # The front desk has no say in where a test is done.
    sign_in(db_client, "priya")
    for path in (f"/lab/tests/{vitd.id}/route", f"/lab/visits/{visit.id}/sharing-consent"):
        assert post(db_client, path, {"row_version": 1, "to": f"lab:{lab.id}"}).status_code == 403


@pytest.mark.item("M11")
def test_the_grid_walks_a_critical_value_from_entry_to_sign_off(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    ordered = _in_lab(lab, platform)
    visit_url = f"/lab/visits/{ordered.visit_id}"
    tc = _param(lab, "lipid", "TC")
    sign_in(db_client, "suresh")

    got = post(
        db_client, f"/lab/tests/{ordered.id}/cells/{tc.id}", {"value": "410", "row_version": 0}
    )
    assert got.status_code == 200
    assert "flag-critical" in got.text and "⚠ HH" in got.text
    # The form to record the call comes back with the row, and the footer with its count.
    saved = _result(lab, ordered, "TC")
    assert saved is not None
    assert f'hx-post="/lab/results/{saved.id}/critical"' in got.text
    assert f'id="f-{ordered.id}" hx-swap-oob="true"' in got.text
    assert "1 critical" in got.text and "2 missing" in got.text

    def act(step: str, **form: object):
        lab.refresh(ordered)
        return post(
            db_client,
            f"/lab/tests/{ordered.id}/{step}",
            {"row_version": ordered.row_version, **form},
        )

    held = act("submit")
    assert held.status_code == 422 and "nobody on record as informed" in held.text
    bad = post(db_client, f"/lab/results/{saved.id}/critical", {"informed_to": "", "mode": "phone"})
    assert bad.status_code == 422 and "Enter who was informed" in bad.text
    bad = post(
        db_client,
        f"/lab/results/{saved.id}/critical",
        {"informed_to": "Dr K", "mode": "phone", "informed_at": "yesterday"},
    )
    assert bad.status_code == 422 and "Enter the date and time." in bad.text
    done = post(
        db_client,
        f"/lab/results/{saved.id}/critical",
        {"informed_to": "Dr Kavya Testcase", "mode": "phone", "phone": "9876500000"},
    )
    assert done.status_code == 200
    assert "Informed Dr Kavya Testcase, by phone" in done.text
    assert f"/lab/results/{saved.id}/critical" not in done.text

    log = db_client.get("/lab/critical")
    assert log.status_code == 200
    assert "Dr Kavya Testcase" in log.text and "Every critical value has someone" in log.text
    # The log shows the patient by name, age and sex; the phone on it is the doctor's.
    patient = lab.get_one(Patient, lab.get_one(Visit, ordered.visit_id).patient_id)
    assert patient.full_name in log.text and patient.phone not in log.text

    assert act("submit").status_code == 303
    page = db_client.get(visit_url).text
    assert "Waiting for verification" in page
    # The technician sees no way to verify, and can't by posting either.
    assert f"/lab/tests/{ordered.id}/verify" not in page
    assert act("verify").status_code == 403
    assert act("reopen", reason="x").status_code == 403

    sign_in(db_client, "meera")
    assert f"/lab/tests/{ordered.id}/verify" in db_client.get(visit_url).text
    assert act("verify").status_code == 303
    page = db_client.get(visit_url).text
    assert "<strong>Verified</strong> by Dr Meera Nair" in page
    assert f"/lab/tests/{ordered.id}/reopen" in page
    # Verified values are read, not typed.
    assert f'hx-post="/lab/tests/{ordered.id}/cells/{tc.id}"' not in page
    assert act("verify").status_code == 409
    no_reason = act("reopen", reason=" ")
    assert no_reason.status_code == 422 and "Say why the test is being reopened." in no_reason.text
    assert act("reopen", reason="Repeat run asked for").status_code == 303
    assert f'hx-post="/lab/tests/{ordered.id}/cells/{tc.id}"' in db_client.get(visit_url).text

    for username in ("priya", "anil"):
        sign_in(db_client, username)
        assert db_client.get("/lab/critical").status_code == 403
        assert act("submit").status_code == 403
