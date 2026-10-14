"""A patient's history (design §8): their visits newest first with tests and report versions,
signed-off results side by side, and the patient list's new filters; a scanned visit number
opens the visit."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core.errors import NotFoundError
from labra.core.ids import lab_today
from labra.core.registry import Platform
from labra.patients import service as patients
from labra.patients.models import Patient
from labra.reports import history
from labra.results import service
from labra.visits import service as visits
from labra.visits.models import Sample, Visit
from tests import test_db_report_content as content
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, sign_in
from tests.test_db_lab_entry import _enter
from tests.test_db_lab_routing import _ids
from tests.test_db_report_content import _day, _ordered, _sign
from tests.test_db_report_release import _release

lab = content.lab


def _again(db: Session, platform: Platform, visit: Visit) -> Visit:
    """A later visit of the same patient at the same branch: lipid only, signed off."""
    priya, suresh = as_user(db, platform, "priya"), as_user(db, platform, "suresh")
    data = visits.VisitInput(
        client_ref=uuid.uuid4(),
        patient_id=visit.patient_id,
        consent=True,
        items=[("test", _ids(db, platform)["lipid"])],
    )
    later = visits.save_visit(db, priya, data, SEED_DAY)
    for sample in db.scalars(select(Sample).where(Sample.visit_id == later.id)).all():
        visits.collect_sample(db, priya, sample.sample_no, priya.user_id)
        service.receive_sample(db, suresh, sample.sample_no)
    lipid = _ordered(db, later, "lipid")
    _enter(db, platform, lipid, TC=180, TG=110, HDL=50)
    _sign(db, platform, lipid)
    return later


def _row(found: history.History, test_part: str, parameter_part: str) -> history.Row:
    return next(
        r for r in found.rows if test_part in r.test and parameter_part in r.parameter.lower()
    )


@pytest.mark.item("M19")
def test_the_history_lists_visits_newest_first_with_results_side_by_side(
    lab: Session, platform: Platform, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _day(lab, platform)
    report = _release(lab, platform, first)
    later = _again(lab, platform, first)
    priya = as_user(lab, platform, "priya")

    found = history.history(lab, priya, first.patient_id, 1)

    assert [line.visit for line in found.visits.items] == [later, first]
    assert found.visits.items[1].reports == [report]
    assert found.visits.items[0].reports == []
    names = dict(found.visits.items[1].tests)
    assert set(names.values()) == {"released", "in_lab"}
    # One row per parameter, a column per visit; a flag only where the value was flagged.
    total = _row(found, "Lipid", "total")
    assert [c.value if c else None for c in total.cells] == ["180", "420"]
    assert total.cells[0] is not None and total.cells[0].flag == ""
    assert total.cells[1] is not None and total.cells[1].flag != ""
    hb = _row(found, "aemoglobin", "aemoglobin")
    assert hb.cells[0] is None and hb.cells[1] is not None and hb.cells[1].value == "10.5"
    # TSH is still in the lab, so it has no row yet.
    assert not [r for r in found.rows if "TSH" in r.test or "Thyroid" in r.test]

    # Six visits to a page; with one, the second page is the older visit alone.
    monkeypatch.setattr(history, "VISITS_PER_PAGE", 1)
    older = history.history(lab, priya, first.patient_id, 2)
    assert [line.visit for line in older.visits.items] == [first]
    assert all(len(r.cells) == 1 for r in older.rows)


@pytest.mark.item("M19")
def test_the_history_is_seen_only_where_the_reports_are(lab: Session, platform: Platform) -> None:
    visit = _day(lab, platform)

    # The bench at the main lab did the tests, so it sees the visit.
    suresh = as_user(lab, platform, "suresh")
    assert [
        line.visit for line in history.history(lab, suresh, visit.patient_id, 1).visits.items
    ] == [visit]
    with pytest.raises(NotFoundError):
        history.history(lab, as_user(lab, platform, "b3desk"), visit.patient_id, 1)
    with pytest.raises(NotFoundError):
        history.history(lab, suresh, uuid.uuid4(), 1)


@pytest.mark.item("M19")
@pytest.mark.item("M20")
def test_the_patient_list_filters_and_a_visit_number_opens_the_visit(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _day(lab, platform)
    patient = lab.get_one(Patient, visit.patient_id)
    patient.address, patient.city, patient.pincode = "12 Synthetic Lane", "Testpur", "560001"
    priya = as_user(lab, platform, "priya")
    today = lab_today()

    def found(**filters: object) -> list[Patient]:
        return patients.find_patients(lab, priya, "", 1, **filters).items  # type: ignore[arg-type]

    assert patient in found(area="testpur") and patient in found(area="5600")
    assert patient in found(area="synthetic lane")
    assert patient not in found(area="Nowhere")
    assert patient in found(visited_from=today, visited_to=today)
    assert patient not in found(visited_from=today + timedelta(days=1))
    assert patient not in found(visited_to=today - timedelta(days=1))

    assert patients.visit_by_number(lab, priya, f" {visit.visit_no.lower()} ") == visit.id
    assert patients.visit_by_number(lab, priya, patient.patient_no) is None
    assert patients.visit_by_number(lab, as_user(lab, platform, "b3desk"), visit.visit_no) is None
    lab.commit()

    sign_in(db_client, "priya")
    scanned = db_client.get(
        "/frontdesk/patients", params={"q": visit.visit_no}, follow_redirects=False
    )
    assert scanned.status_code == 303
    assert scanned.headers["location"] == f"/frontdesk/visits/{visit.id}"
    page = db_client.get("/frontdesk/patients", params={"area": "Testpur"}).text
    assert patient.patient_no in page and f'href="/reports/patients/{patient.id}"' in page
    shown = db_client.get(f"/reports/patients/{patient.id}")
    assert shown.status_code == 200
    assert "Results side by side" in shown.text and visit.visit_no in shown.text

    sign_in(db_client, "b3desk")
    assert db_client.get(f"/reports/patients/{patient.id}").status_code == 404
