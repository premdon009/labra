"""Sample labels and the collection scan."""

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.billing import service as billing
from labra.billing.models import Bill
from labra.core.errors import PermissionDeniedError, ValidationFailedError
from labra.core.ids import utcnow
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.org.models import AppUser
from labra.visits import service
from labra.visits.models import OrderTest, Sample, Visit
from labra.web.barcode import code128
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, menu, post, sign_in, visit_input


def _visit(seeded: Session, platform: Platform, username: str = "priya") -> Visit:
    """The demo order: four tests that need three containers."""
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    data = visit_input(ids, "fbs", "lipid", "urine", "vitd")
    return service.save_visit(seeded, as_user(seeded, platform, username), data, SEED_DAY)


def _samples(seeded: Session, visit: Visit) -> list[Sample]:
    return list(
        seeded.scalars(select(Sample).where(Sample.visit_id == visit.id).order_by(Sample.sample_no))
    )


def _staff(seeded: Session, username: str) -> AppUser:
    return seeded.scalars(select(AppUser).where(AppUser.username == username)).one()


@pytest.mark.item("M08")
def test_labels_one_per_container(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _visit(seeded, platform)
    samples = _samples(seeded, visit)
    sign_in(db_client, "priya")

    sheet = db_client.get(f"/frontdesk/visits/{visit.id}/labels").text

    assert len(samples) == 3
    assert sheet.count('<section class="label"') == 3
    for sample in samples:
        assert re.fullmatch(r"B2\d{4}\d{6}", sample.sample_no)
        assert f'aria-label="Barcode {sample.sample_no}"' in sheet
        assert f"<span>{sample.sample_no}</span>" in sheet
    # Lipid and vitamin D share the serum tube, so they share a label.
    assert "LIPID, VITD" in sheet
    assert "data-autoprint" not in sheet
    summary = db_client.get(f"/frontdesk/visits/{visit.id}").text
    assert f'href="/frontdesk/visits/{visit.id}/labels?print=1"' in summary


@pytest.mark.item("M08")
def test_label_has_container_and_blank_collection_time(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _visit(seeded, platform)
    priya = as_user(seeded, platform, "priya")
    grey = next(s for s in _samples(seeded, visit) if s.container == "Grey top")
    sign_in(db_client, "priya")

    before = db_client.get(f"/frontdesk/visits/{visit.id}/labels").text

    for words in ("Grey top", "Red top", "Urine cup", "FBS", "Testcase · 34 Y / F"):
        assert words in before
    assert before.count("Coll __:__") == 3
    assert "Container not set" not in before

    at = utcnow().replace(hour=4, minute=5)  # 09:35 in India
    service.collect_sample(seeded, priya, grey.sample_no, priya.user_id, at)
    after = db_client.get(f"/frontdesk/visits/{visit.id}/labels").text
    assert after.count("Coll __:__") == 2 and "09:35" in after


@pytest.mark.item("M08")
def test_barcode_svg_has_no_style_attr(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _visit(seeded, platform)
    first = _samples(seeded, visit)[0]
    sign_in(db_client, "priya")

    response = db_client.get(f"/frontdesk/visits/{visit.id}/labels?print=1")

    sheet = response.text
    assert "style=" not in sheet and "<style" not in sheet
    assert "script-src 'self'" in response.headers["content-security-policy"]
    bars = code128(first.sample_no)
    assert f'viewBox="0 0 {bars.modules} 10" width="{bars.width_mm}mm"' in sheet
    for start, width in bars.runs:
        assert f'<rect x="{start}" y="0" width="{width}" height="10" fill="#000">' in sheet
    assert sheet.count("<rect") == sum(
        len(code128(s.sample_no).runs) for s in _samples(seeded, visit)
    )
    # Opened for printing, the sheet prints itself and goes back to the visit.
    assert f'data-autoprint data-after-print="/frontdesk/visits/{visit.id}"' in sheet
    assert 'href="/static/print.css"' in sheet
    css = db_client.get("/static/print.css").text
    assert "size: 50mm 25mm" in css and "page: labels" in css


@pytest.mark.item("M08")
@pytest.mark.item("EC-J01")
def test_collect_scan_marks_collected_by_no_login_staff(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _visit(seeded, platform)
    serum = next(s for s in _samples(seeded, visit) if s.container == "Red top")
    walker = _staff(seeded, "staff1")
    assert not walker.can_login
    sign_in(db_client, "priya")

    screen = db_client.get("/frontdesk/collect").text
    # The scanner types into the box and sends Enter, which submits this plain form.
    assert 'name="sample_no" value="" autofocus' in screen
    assert "data-no-enter-submit" not in screen
    assert f'<option value="{walker.id}" >{walker.full_name}</option>' in screen
    assert 'href="/frontdesk/collect"' in db_client.get("/").text

    scan = {"sample_no": f" {serum.sample_no.lower()} ", "collected_by": str(walker.id)}
    done = post(db_client, "/frontdesk/collect", scan)

    assert done.status_code == 303
    assert done.headers["location"] == f"/frontdesk/collect?by={walker.id}&done={serum.sample_no}"
    seeded.refresh(serum)
    assert (serum.status, serum.collected_by) == ("collected", walker.id)
    assert serum.collected_at is not None and utcnow() - serum.collected_at < timedelta(minutes=1)
    tests = seeded.scalars(select(OrderTest).where(OrderTest.visit_id == visit.id)).all()
    assert sorted(t.status for t in tests) == ["collected", "collected", "ordered", "ordered"]
    assert {t.status for t in tests if t.sample_id == serum.id} == {"collected"}
    logged = seeded.scalars(select(AuditLog).where(AuditLog.action == "sample.collect")).one()
    assert logged.detail["sample_no"] == serum.sample_no
    assert "Testcase" not in str(logged.detail)

    # Ready for the next scan: the result is shown, the box is empty, the collector stays.
    again = db_client.get(done.headers["location"]).text
    assert f"Collected: {serum.sample_no}" in again and "LIPID, VITD" in again
    assert f"by {walker.full_name}" in again
    assert 'name="sample_no" value="" autofocus' in again
    assert f'<option value="{walker.id}" selected>' in again

    twice = post(db_client, "/frontdesk/collect", scan)
    assert twice.status_code == 422 and "already marked as collected" in twice.text
    unknown = post(db_client, "/frontdesk/collect", scan | {"sample_no": "B2262799"})
    assert unknown.status_code == 422 and "No sample at this branch" in unknown.text
    assert post(db_client, "/frontdesk/collect", scan | {"sample_no": " "}).status_code == 422


@pytest.mark.item("M08")
@pytest.mark.item("EC-A05")
def test_collect_is_for_the_users_branch_and_its_staff(seeded: Session, platform: Platform) -> None:
    visit = _visit(seeded, platform)
    sample = _samples(seeded, visit)[0]
    priya = as_user(seeded, platform, "priya")
    b3desk = as_user(seeded, platform, "b3desk")

    def refused(principal, who) -> dict[str, str]:
        with pytest.raises(ValidationFailedError) as error:
            service.collect_sample(seeded, principal, sample.sample_no, who)
        return error.value.errors

    # At B3 the B2 sample doesn't exist, and B3 staff can't be named at B2.
    assert "sample_no" in refused(b3desk, b3desk.user_id)
    assert service.find_sample(seeded, b3desk, sample.sample_no) is None
    assert "collected_by" in refused(priya, b3desk.user_id)
    assert "collected_by" in refused(priya, None)
    away = _staff(seeded, "staff1")
    away.is_active = False
    seeded.flush()
    assert "collected_by" in refused(priya, away.id)
    assert away.id not in {u.id for u in service.collectors(seeded, priya)}
    with pytest.raises(PermissionDeniedError):
        service.collect_sample(
            seeded, as_user(seeded, platform, "suresh"), sample.sample_no, priya.user_id
        )
    seeded.refresh(sample)
    assert sample.status == "pending"


@pytest.mark.item("M07")
@pytest.mark.item("EC-B05")
def test_collect_refuses_cancelled_sample(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _visit(seeded, platform, "b3desk")
    sample = _samples(seeded, visit)[0]
    b3desk = as_user(seeded, platform, "b3desk")
    bill = seeded.scalars(select(Bill).where(Bill.visit_id == visit.id)).one()
    billing.cancel_bill(seeded, b3desk, bill.id, "Patient left", True, bill.row_version)
    sign_in(db_client, "b3desk")

    scan = {"sample_no": sample.sample_no, "collected_by": str(b3desk.user_id)}
    refused = post(db_client, "/frontdesk/collect", scan)

    assert refused.status_code == 422
    assert "was cancelled with its bill" in refused.text
    seeded.refresh(sample)
    assert (sample.status, sample.collected_at) == ("cancelled", None)
    # Nothing left to label either.
    sheet = db_client.get(f"/frontdesk/visits/{visit.id}/labels?print=1").text
    assert "no labels to print" in sheet and "data-autoprint" not in sheet
    assert "Print labels" not in db_client.get(f"/frontdesk/visits/{visit.id}").text
