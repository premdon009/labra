"""After the first release (design §7): a released test reopened and corrected comes out as
an amended version, an outside lab's PDF goes after the report when nothing was typed from
it, and in separate mode each outside lab's PDF is a report of its own."""

import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core.errors import ConflictError, ValidationFailedError
from labra.core.files import read_file
from labra.core.models import AuditLog, EventOutbox
from labra.core.registry import Platform
from labra.reports import release, service
from labra.reports.models import Report
from labra.results import outsourcing, signoff
from labra.results import service as lab_service
from labra.results.models import ExternalDocument
from labra.visits.models import OrderTest, Sample, Visit
from tests import test_db_report_content as content
from tests.frontdesk import as_user, post, sign_in
from tests.test_attach import runnable, scripted_pdf
from tests.test_db_lab_entry import _enter
from tests.test_db_lab_outsourcing import LAB_NAME, _vitd
from tests.test_db_lab_routing import _lab, _visit
from tests.test_db_report_content import _day, _ordered, _pages, _sign
from tests.test_db_report_release import _release

lab = content.lab

REASON = "Typing slip in cholesterol"
OUTSIDE = "Synthetic outside value 32.5"
VITD = "Vitamin D (25-OH)"


def _flat(pdf: bytes) -> str:
    return " ".join(" ".join(_pages(pdf)).split())


def _outside_pdf(
    db: Session, platform: Platform, visit: Visit, ordered: OrderTest, lab_id: uuid.UUID
) -> ExternalDocument:
    """The outside lab's PDF, carrying a script, attached to the test with no value typed."""
    suresh = as_user(db, platform, "suresh")
    outsourcing.mark_sent(db, suresh, ordered.id, ordered.row_version, "RL-2291")
    return outsourcing.attach_result(
        db, platform.filestore, suresh, visit.id, lab_id, scripted_pdf(OUTSIDE), [ordered.id]
    )


def _separate(
    db: Session, platform: Platform
) -> tuple[Visit, OrderTest, OrderTest, ExternalDocument]:
    """Haemoglobin done here and vitamin D done outside, both signed off, the outside lab's
    PDF attached to vitamin D."""
    visit = _visit(db, platform, "priya", "vitd", "hb")
    priya, suresh = as_user(db, platform, "priya"), as_user(db, platform, "suresh")
    samples = db.scalars(select(Sample).where(Sample.visit_id == visit.id)).all()
    for sample in samples:
        content.visits.collect_sample(db, priya, sample.sample_no, priya.user_id)
    vitd, hb = _ordered(db, visit, "vitd"), _ordered(db, visit, "hb")
    outside = _lab(db, as_user(db, platform, "anil"), LAB_NAME, "700", 48)
    lab_service.route_test(db, suresh, vitd.id, vitd.row_version, external_lab_id=outside.id)
    lab_service.receive_sample(db, suresh, db.get_one(Sample, hb.sample_id).sample_no)
    _enter(db, platform, hb, test="hb", HB="10.5")
    _sign(db, platform, hb)
    document = _outside_pdf(db, platform, visit, vitd, outside.id)
    _sign(db, platform, vitd)
    return visit, hb, vitd, document


@pytest.mark.item("M12")
def test_a_released_test_reopened_and_corrected_comes_out_amended(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    lipid, hb = _ordered(lab, visit, "lipid"), _ordered(lab, visit, "hb")
    first = _release(lab, platform, visit)
    meera = as_user(lab, platform, "meera")

    signoff.reopen(lab, meera, lipid.id, lipid.row_version, REASON)
    assert lipid.status == "resulted"
    planned = service.plan(lab, meera, visit.id)
    assert lipid.id in {t.id for t in planned.pending}
    assert [t.id for t in planned.carried] == [hb.id] and planned.new == []

    _enter(lab, platform, lipid, TC=380)
    _sign(lab, platform, lipid)
    planned = service.plan(lab, meera, visit.id)
    assert [t.id for t in planned.amended] == [lipid.id] == [t.id for t in planned.new]
    assert planned.reasons == {lipid.id: REASON}
    second = _release(lab, platform, visit)

    line = f"Lipid profile: {REASON}"
    assert second.version == 2 and second.amendment_reason == line
    assert second.content["amended"] == {"supersedes": 1, "lines": [line]}
    _, data = read_file(lab, platform.filestore, second.file_id)
    flat = _flat(data)
    assert "AMENDED REPORT: supersedes v1" in flat and line in flat
    assert "380" in flat and "420" not in flat
    entry = lab.scalars(select(AuditLog).where(AuditLog.entity_id == str(second.id))).one()
    assert entry.detail["amended"] == ["lipid"] and entry.detail["carried"] == 1
    event = lab.scalars(
        select(EventOutbox)
        .where(EventOutbox.topic == "report.released")
        .order_by(EventOutbox.id.desc())
        .limit(1)
    ).one()
    assert event.payload["is_amended"] is True
    assert REASON not in str(event.payload) + str(entry.detail)
    # The corrected version is the one in force; the old one and its file are kept.
    lab.refresh(first)
    assert first.status == "superseded" and service.current(lab, visit.id) == second
    _, old = read_file(lab, platform.filestore, first.file_id)
    assert hashlib.sha256(old).hexdigest() == first.sha256 and "420" in _flat(old)
    # Released again, so nothing is left to amend.
    after = service.plan(lab, meera, visit.id)
    assert after.amended == [] and after.reasons == {}


@pytest.mark.item("M12")
def test_the_lab_screen_says_a_released_test_can_be_reopened(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _day(lab, platform)
    _release(lab, platform, visit)
    lab.commit()

    sign_in(db_client, "meera")
    page = db_client.get(f"/lab/visits/{visit.id}")
    assert "This test is on a released report." in page.text
    sign_in(db_client, "suresh")
    assert "This test is on a released report." not in db_client.get(f"/lab/visits/{visit.id}").text


@pytest.mark.item("M12")
def test_combined_mode_adds_the_outside_pdf_after_the_report(
    lab: Session, platform: Platform
) -> None:
    visit, vitd, outside = _vitd(lab, platform)
    document = _outside_pdf(lab, platform, visit, vitd, outside.id)
    _sign(lab, platform, vitd)
    assert visit.report_mode is None

    report = _release(lab, platform, visit)

    assert report.kind == "combined"
    _, data = read_file(lab, platform.filestore, report.file_id)
    pages = _pages(data)
    flat = _flat(data)
    assert f"See the attached report from {LAB_NAME}." in flat
    assert f"Attached after the last page: the report from {LAB_NAME} for {VITD}." in flat
    assert OUTSIDE in pages[-1] and OUTSIDE not in pages[0]
    assert runnable(data) == []
    [attached] = report.content["attachments"]
    assert attached["file_id"] == str(document.file_id) and attached["lab"] == LAB_NAME
    # The first release settles the mode for the visit.
    lab.refresh(visit)
    assert visit.report_mode == "combined"
    with pytest.raises(ConflictError):
        service.set_mode(lab, as_user(lab, platform, "meera"), visit.id, "separate")


@pytest.mark.item("M12")
def test_separate_mode_releases_the_outside_pdf_as_a_report_of_its_own(
    lab: Session, platform: Platform
) -> None:
    visit, hb, vitd, document = _separate(lab, platform)
    meera = as_user(lab, platform, "meera")

    service.set_mode(lab, meera, visit.id, "separate")
    entry = lab.scalars(select(AuditLog).where(AuditLog.action == "visit.report_mode")).one()
    assert entry.detail == {"mode": "separate"} and entry.entity_id == str(visit.id)
    planned = service.plan(lab, meera, visit.id)
    assert [t.id for t in planned.new] == [hb.id] and planned.pending == []
    assert [t.id for t in planned.separately] == [vitd.id]
    [waiting] = planned.forwards
    assert waiting.ready and waiting.lab_name == LAB_NAME and waiting.document.id == document.id

    main = _release(lab, platform, visit)
    assert main.kind == "in_house" and not main.is_partial
    flat = _flat(read_file(lab, platform.filestore, main.file_id)[1])
    assert f"Reported separately by the outside lab: {VITD}" in flat and OUTSIDE not in flat
    with pytest.raises(ConflictError):
        service.set_mode(lab, meera, visit.id, "combined")

    with pytest.raises(ValidationFailedError) as refused:
        release.forward(lab, platform.filestore, meera, visit.id, document.id, False)
    assert refused.value.errors == {f"forward:{document.id}": release.CONFIRM}
    forwarded = release.forward(lab, platform.filestore, meera, visit.id, document.id, True)

    assert forwarded.kind == "external_forward" and forwarded.version == 1
    assert forwarded.external_document_id == document.id
    assert forwarded.report_no != main.report_no and forwarded.report_no.endswith("000002")
    pages = _pages(read_file(lab, platform.filestore, forwarded.file_id)[1])
    assert "Outside laboratory report" in pages[0] and OUTSIDE in pages[-1]
    assert runnable(read_file(lab, platform.filestore, forwarded.file_id)[1]) == []
    lab.refresh(vitd)
    assert vitd.status == "released"
    assert service.current(lab, visit.id) == main
    after = service.plan(lab, meera, visit.id)
    assert not after.forwards[0].ready and after.forwards[0].current == forwarded
    with pytest.raises(ConflictError):
        release.forward(lab, platform.filestore, meera, visit.id, document.id, True)


@pytest.mark.item("M12")
def test_the_mode_and_forward_screens(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    visit, _, _, document = _separate(lab, platform)
    lab.commit()
    mode, forward = (
        f"/reports/visits/{visit.id}/mode",
        f"/reports/visits/{visit.id}/forward/{document.id}",
    )

    sign_in(db_client, "priya")
    assert post(db_client, mode, {"mode": "separate"}).status_code == 403
    assert post(db_client, forward, {"confirm": "yes"}).status_code == 403

    sign_in(db_client, "meera")
    assert "Outside lab results" in db_client.get(f"/reports/visits/{visit.id}").text
    assert post(db_client, mode, {"mode": "sideways"}).status_code == 404
    assert post(db_client, mode, {"mode": "separate"}).status_code == 303
    screen = db_client.get(f"/reports/visits/{visit.id}")
    assert "Outside lab reports" in screen.text and f"Release the {LAB_NAME} report" in screen.text
    refused = post(db_client, forward, {})
    assert refused.status_code == 422 and release.CONFIRM in refused.text
    assert lab.scalars(select(Report)).all() == []
    assert post(db_client, forward, {"confirm": "yes"}).status_code == 303
    assert "Released; nothing new since." in db_client.get(f"/reports/visits/{visit.id}").text
