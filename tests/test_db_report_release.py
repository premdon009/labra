"""Releasing a report (design §7): the number and version, the stored copy, the tests marked
released, the audit row and event, the next version superseding the last, the block on a
value read against an unapproved range, the QR code and its public check page, and the
reports queue."""

import hashlib
import re
import uuid

import pytest
import segno
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from labra.core import lab_settings
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.files import read_file
from labra.core.models import AuditLog, EventOutbox
from labra.core.registry import Platform
from labra.org.models import Branch
from labra.printing.reportpage import qr
from labra.reports import release, service, verify
from labra.reports.models import Report, ReportTest
from labra.results.models import OrderTestEvent
from labra.visits.models import OrderTest, Visit
from tests import test_db_report_content as content
from tests.frontdesk import as_user, post, sign_in
from tests.test_db_lab_entry import _approve, _enter
from tests.test_db_report_content import _day, _ordered, _pages, _received, _sign

lab = content.lab

NUMBER = re.compile(r"B2/R/\d{4}/000001")


def _release(db: Session, platform: Platform, visit: Visit, username: str = "meera") -> Report:
    meera = as_user(db, platform, username)
    planned = service.plan(db, meera, visit.id)
    expected = {t.id for t in planned.new}
    return release.release(db, platform.filestore, meera, visit.id, expected, True)


def _tsh(db: Session, platform: Platform, visit: Visit, approved: bool = True) -> OrderTest:
    """The visit's TSH resulted and signed off; its range approved first if asked."""
    if approved:
        _approve(db, platform, "tsh")
    tsh = _ordered(db, visit, "tsh")
    _enter(db, platform, tsh, test="tsh", TSH="2.1")
    _sign(db, platform, tsh)
    return tsh


@pytest.mark.item("M12")
@pytest.mark.item("M26")
def test_a_release_numbers_stores_and_marks_the_tests_released(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    lipid, hb, tsh = (_ordered(lab, visit, c) for c in ("lipid", "hb", "tsh"))
    meera = as_user(lab, platform, "meera")

    planned = service.plan(lab, meera, visit.id)
    assert NUMBER.fullmatch(planned.report_no) and planned.version == 1
    assert {t.id for t in planned.new} == {lipid.id, hb.id}
    assert [t.id for t in planned.pending] == [tsh.id]

    report = _release(lab, platform, visit)

    assert report.report_no == planned.report_no and report.version == 1
    assert report.status == "released" and report.is_partial
    assert report.released_by == meera.user_id
    assert len(report.verify_token) == 22
    on_report = set(
        lab.scalars(select(ReportTest.order_test_id).where(ReportTest.report_id == report.id))
    )
    assert on_report == {lipid.id, hb.id}
    for ordered in (lipid, hb):
        lab.refresh(ordered)
        assert ordered.status == "released"
        event = lab.scalars(
            select(OrderTestEvent).where(
                OrderTestEvent.order_test_id == ordered.id, OrderTestEvent.event == "released"
            )
        ).one()
        assert event.note == f"Report {report.report_no} v1" and event.by == meera.user_id
    lab.refresh(tsh)
    assert tsh.status != "released"

    stored, data = read_file(lab, platform.filestore, report.file_id)
    assert hashlib.sha256(data).hexdigest() == report.sha256
    assert stored.filename == f"report-{report.report_no.replace('/', '-')}-v1.pdf"
    text = " ".join(" ".join(_pages(data)).split())
    assert f"Report {report.report_no} v1" in text and "PARTIAL REPORT" in text
    assert "PREVIEW" not in text and "Preview" not in text
    assert report.content["report_no"] == report.report_no and report.content["qr"]

    entry = lab.scalars(select(AuditLog).where(AuditLog.entity_id == str(report.id))).one()
    assert entry.action == "report.release"
    assert entry.detail == {
        "visit_id": str(visit.id),
        "kind": "combined",
        "version": 1,
        "tests": ["hb", "lipid"],
        "amended": [],
        "carried": 0,
        "partial": True,
    }
    event = lab.scalars(select(EventOutbox).where(EventOutbox.topic == "report.released")).one()
    assert event.payload["entity_id"] == str(report.id)
    assert event.payload["order_test_ids"] == sorted([str(lipid.id), str(hb.id)])
    # Ids are random hex, which can hold "420" by chance, so they are cut out first.
    ids = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    flat = ids.sub("", str(event.payload) + str(entry.detail))
    for private in (report.verify_token, "Sunita", "420", report.report_no):
        assert private not in flat


@pytest.mark.item("M12")
def test_the_next_release_is_a_new_version_carrying_every_test(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    first = _release(lab, platform, visit)
    tsh = _tsh(lab, platform, visit)
    meera = as_user(lab, platform, "meera")

    planned = service.plan(lab, meera, visit.id)
    assert (planned.report_no, planned.version) == (first.report_no, 2)
    assert [t.id for t in planned.new] == [tsh.id] and len(planned.carried) == 2
    assert planned.pending == []
    second = _release(lab, platform, visit)

    lab.refresh(first)
    assert first.status == "superseded"
    assert (second.report_no, second.version, second.status) == (first.report_no, 2, "released")
    assert second.supersedes_report_id == first.id and not second.is_partial
    # More tests, nothing corrected: not an amendment.
    assert second.amendment_reason == "" and second.content["amended"] is None
    assert len(lab.scalars(select(ReportTest).where(ReportTest.report_id == second.id)).all()) == 3
    assert service.current(lab, visit.id) == second
    assert [r.version for r, _ in service.versions(lab, visit.id)] == [2, 1]
    entry = lab.scalars(select(AuditLog).where(AuditLog.entity_id == str(second.id))).one()
    assert entry.detail["tests"] == ["tsh"] and entry.detail["carried"] == 2
    # The old version's file is kept.
    _, data = read_file(lab, platform.filestore, first.file_id)
    assert hashlib.sha256(data).hexdigest() == first.sha256


@pytest.mark.item("M12")
@pytest.mark.item("EC-J03")
def test_a_release_needs_the_confirmation_and_the_tests_the_signatory_saw(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    meera = as_user(lab, platform, "meera")
    lipid = _ordered(lab, visit, "lipid")
    hb = _ordered(lab, visit, "hb")
    store = platform.filestore

    with pytest.raises(ValidationFailedError) as refused:
        release.release(lab, store, meera, visit.id, {lipid.id, hb.id}, False)
    assert refused.value.errors == {"confirm": release.CONFIRM}
    with pytest.raises(ConflictError):
        release.release(lab, store, meera, visit.id, {lipid.id}, True)
    assert lab.scalars(select(Report)).all() == []

    release.release(lab, store, meera, visit.id, {lipid.id, hb.id}, True)
    with pytest.raises(ConflictError) as again:
        release.release(lab, store, meera, visit.id, set(), True)
    assert again.value.public_message == release.NOTHING_NEW


@pytest.mark.item("M12")
def test_a_value_read_against_an_unapproved_range_blocks_the_release(
    lab: Session, platform: Platform
) -> None:
    visit = _received(lab, platform, "tsh")
    tsh = _tsh(lab, platform, visit, approved=False)
    meera = as_user(lab, platform, "meera")

    planned = service.plan(lab, meera, visit.id)
    assert [t.id for t in planned.new] == [tsh.id]
    (problem,) = planned.problems
    assert "Thyroid stimulating hormone (TSH)" in problem and "not approved" in problem
    with pytest.raises(ValidationFailedError) as refused:
        release.release(lab, platform.filestore, meera, visit.id, {tsh.id}, True)
    assert "not approved" in refused.value.errors["release"]
    lab.refresh(tsh)
    assert tsh.status == "verified"


@pytest.mark.item("M12")
@pytest.mark.item("EC-B05")
def test_a_released_report_cannot_be_changed_through_the_app(
    lab: Session, platform: Platform
) -> None:
    report = _release(lab, platform, _day(lab, platform))
    lab.commit()
    report.is_partial = False
    with pytest.raises(DBAPIError):
        lab.flush()
    lab.rollback()
    lab.delete(lab.get_one(Report, report.id))
    with pytest.raises(DBAPIError):
        lab.flush()
    lab.rollback()


@pytest.mark.item("M12")
def test_who_may_release(lab: Session, platform: Platform) -> None:
    visit = _day(lab, platform)
    for username in ("priya", "suresh", "anil", "b3desk"):
        principal = as_user(lab, platform, username)
        with pytest.raises(PermissionDeniedError):
            release.release(lab, platform.filestore, principal, visit.id, set(), True)
    with pytest.raises(NotFoundError):
        _release(lab, platform, _received(lab, platform, "tsh"))


@pytest.mark.item("M12")
def test_the_qr_code_links_to_the_check_page_or_carries_a_fingerprint(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    first = _release(lab, platform, visit)
    text = first.content["qr"]
    assert re.fullmatch(rf"Report {re.escape(first.report_no)} v1 [0-9a-f]{{16}}", text)

    lab_settings.set_value(lab, "report.verify_base_url", "https://labra.example.test", None)
    _tsh(lab, platform, visit)
    second = _release(lab, platform, visit)
    assert second.content["qr"] == f"https://labra.example.test/v/{second.verify_token}"


def test_the_qr_drawing_matches_the_code() -> None:
    text = "https://labra.example.test/v/AAAAAAAAAAAAAAAAAAAAAA"
    drawn = qr(text)
    matrix = segno.make(text, error="m", micro=False).matrix
    assert drawn["size"] == len(matrix) and drawn["link"]
    dark = {(x + i, y) for x, y, w in drawn["runs"] for i in range(w)}
    assert dark == {(x, y) for y, row in enumerate(matrix) for x, v in enumerate(row) if v}
    assert not qr("Report B2/R/2627/000001 v1 0123456789abcdef")["link"]


@pytest.mark.item("M12")
def test_the_check_page_shows_the_version_and_nothing_about_the_patient(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _day(lab, platform)
    first = _release(lab, platform, visit)
    _tsh(lab, platform, visit)
    second = _release(lab, platform, visit)
    lab.commit()
    assert verify.check(lab, first.verify_token).current is False
    for bad in ("short", "x" * 22 + "!", "A" * 22):
        with pytest.raises(NotFoundError):
            verify.check(lab, bad)

    db_client.cookies.clear()
    shown = db_client.get(f"/v/{second.verify_token}")
    assert shown.status_code == 200
    assert second.report_no in shown.text and "Current" in shown.text
    assert shown.headers["cache-control"] == "no-store"
    assert shown.headers["x-robots-tag"] == "noindex, nofollow"
    old = db_client.get(f"/v/{first.verify_token}")
    assert "Superseded" in old.text
    for page in (shown.text, old.text):
        for private in ("Sunita", "Testcase", visit.visit_no, "Lipid", "420"):
            assert private not in page
        assert "Main menu" not in page
    assert db_client.get("/v/" + "A" * 22).status_code == 404


@pytest.mark.item("M12")
def test_the_queue_lists_what_waits_and_the_stored_copy_opens(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    waiting = _day(lab, platform)
    done = _day(lab, platform)
    report = _release(lab, platform, done)
    meera, priya = as_user(lab, platform, "meera"), as_user(lab, platform, "priya")

    assert [v.visit_id for v in service.to_release(lab, meera)] == [waiting.id]
    assert service.to_release(lab, meera)[0].tests == 2
    assert service.to_release(lab, priya) == []
    assert [r.report_id for r in service.released(lab, priya)] == [report.id]
    assert service.released(lab, as_user(lab, platform, "b3desk")) == []
    assert service.viewable(lab, priya, report.id) == (report, done)
    _, data = read_file(lab, platform.filestore, report.file_id)
    with pytest.raises(NotFoundError):
        service.viewable(lab, as_user(lab, platform, "b3desk"), report.id)
    lab.commit()

    sign_in(db_client, "priya")
    page = db_client.get("/reports")
    assert page.status_code == 200
    assert "To release" not in page.text and report.report_no in page.text
    pdf = db_client.get(f"/reports/{report.id}/pdf", params={"dues": "yes"})
    assert pdf.status_code == 200 and pdf.content == data
    name = f"report-{report.report_no.replace('/', '-')}-v1.pdf"
    assert pdf.headers["content-disposition"] == f'inline; filename="{name}"'
    assert db_client.get(f"/reports/visits/{waiting.id}").status_code == 403
    assert post(db_client, f"/reports/visits/{waiting.id}/release", {}).status_code == 403

    sign_in(db_client, "b3desk")
    assert db_client.get(f"/reports/{report.id}/pdf").status_code == 404
    assert db_client.get(f"/reports/{uuid.uuid4()}/pdf").status_code == 404

    sign_in(db_client, "meera")
    page = db_client.get("/reports")
    assert "To release" in page.text and waiting.visit_no in page.text


@pytest.mark.item("M12")
@pytest.mark.item("EC-J03")
def test_the_release_screen_confirms_then_releases(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _day(lab, platform)
    lipid, hb = _ordered(lab, visit, "lipid"), _ordered(lab, visit, "hb")
    lab.commit()
    sign_in(db_client, "meera")
    screen = db_client.get(f"/reports/visits/{visit.id}")
    number = re.search(r"Release (B2/R/\d{4}/\d{6}) v1", screen.text)
    assert number is not None and "Pending" in screen.text
    url = f"/reports/visits/{visit.id}/release"
    form = {"tests": [str(lipid.id), str(hb.id)]}

    refused = post(db_client, url, form)
    assert refused.status_code == 422 and release.CONFIRM in refused.text
    assert lab.scalars(select(Report)).all() == []

    done = post(db_client, url, form | {"confirm": "yes"})
    assert done.status_code == 303 and done.headers["location"] == f"/reports/visits/{visit.id}"
    after = db_client.get(f"/reports/visits/{visit.id}")
    assert f"{number.group(1)} v1" in after.text and "Current" in after.text
    assert "Nothing new to release" in after.text
    assert post(db_client, url, form | {"confirm": "yes"}).status_code == 409


@pytest.mark.item("M12")
def test_a_signatory_releases_only_tests_done_where_they_sign(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    hb = _ordered(lab, visit, "hb")
    # Pretend haemoglobin was done at a branch where meera can't release.
    meera = as_user(lab, platform, "meera")
    other = next(b for b in lab.scalars(select(Branch)) if not meera.can("report.release", b.id))
    hb.perform_branch_id = other.id
    lab.flush()
    planned = service.plan(lab, meera, visit.id)
    assert hb.id not in {t.id for t in planned.new}
    assert hb.id in {t.id for t in planned.pending}
