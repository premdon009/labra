"""The lab worklist and the result grid as screens: who sees which tests, and what of the
patient."""

import re
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from labra.catalog.models import Department, Test
from labra.core.errors import NotFoundError, PermissionDeniedError
from labra.core.registry import Platform
from labra.patients.models import Patient
from labra.results import entry, service, worklist
from labra.seed import make_user, seed
from labra.visits import service as visits
from labra.visits.models import OrderTest, Sample, Visit
from labra.web.shortcuts import SHORTCUTS
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, branch, patient_input, sign_in
from tests.test_db_lab_entry import _approve, _param

ADDRESS = "14 Synthetic Lane"


@pytest.fixture
def lab(db: Session, platform: Platform) -> Session:
    """The demo cast and starter catalog, with a technician at Branch 2 as well."""
    seed(db, platform.identity, SEED_DAY, with_catalog=True)
    _approve(db, platform, "lipid")
    make_user(
        db,
        platform.identity,
        "b2tech",
        "Tara Testcase",
        [(branch(db, "B2").id, "technician")],
        True,
    )
    db.flush()
    return db


def _visit(db: Session, platform: Platform, *codes: str, name: str = "Sunita Testcase") -> Visit:
    """A Branch 2 visit, its samples collected there."""
    priya = as_user(db, platform, "priya")
    tests = {row.code: row.id for row in db.execute(select(Test.code, Test.id))}
    data = visits.VisitInput(
        client_ref=uuid.uuid4(),
        patient=patient_input(
            full_name=name, phone=f"90000{uuid.uuid4().int % 10**5:05d}", address=ADDRESS
        ),
        consent=True,
        items=[("test", tests[code]) for code in codes],
    )
    visit = visits.save_visit(db, priya, data, SEED_DAY)
    for sample in db.scalars(select(Sample).where(Sample.visit_id == visit.id)):
        visits.collect_sample(db, priya, sample.sample_no, priya.user_id)
    return visit


def _receive(db: Session, platform: Platform, visit: Visit) -> None:
    suresh = as_user(db, platform, "suresh")
    for sample in db.scalars(select(Sample).where(Sample.visit_id == visit.id)):
        service.receive_sample(db, suresh, sample.sample_no)


def _test(db: Session, visit: Visit, code: str) -> OrderTest:
    return db.scalars(
        select(OrderTest)
        .join(Test, Test.id == OrderTest.test_id)
        .where(OrderTest.visit_id == visit.id, Test.code == code)
    ).one()


def _listed(db: Session, platform: Platform, username: str, **filters) -> list[tuple[str, str]]:
    page = worklist.work_page(db, as_user(db, platform, username), **filters)
    return [(item.patient_name, item.test_code) for item in page.items]


@pytest.mark.item("M11")
def test_the_worklist_shows_the_tests_a_branch_performs(lab: Session, platform: Platform) -> None:
    first = _visit(lab, platform, "lipid", "urine", name="Asha Testcase")
    second = _visit(lab, platform, "fbs", name="Bala Testcase")
    _receive(lab, platform, first)
    # Branch 2 keeps the glucose test and does it there.
    kept = _test(lab, second, "fbs")
    service.route_test(
        lab,
        as_user(lab, platform, "anil"),
        kept.id,
        kept.row_version,
        branch_id=branch(lab, "B2").id,
    )
    b2 = branch(lab, "B2").id

    assert sorted(_listed(lab, platform, "suresh")) == [
        ("Asha Testcase", "lipid"),
        ("Asha Testcase", "urine"),
    ]
    assert _listed(lab, platform, "b2tech") == [("Bala Testcase", "fbs")]
    # The main lab can look at a centre's list; a centre can't look at the main lab's.
    assert _listed(lab, platform, "suresh", branch_id=b2) == [("Bala Testcase", "fbs")]
    main = branch(lab, "MAIN").id
    assert _listed(lab, platform, "b2tech", branch_id=main) == [("Bala Testcase", "fbs")]
    for username in ("priya", "anil"):
        with pytest.raises(PermissionDeniedError):
            _listed(lab, platform, username)

    item = worklist.work_page(lab, as_user(lab, platform, "suresh")).items[0]
    sample = lab.scalars(select(Sample).where(Sample.visit_id == first.id)).first()
    assert sample is not None
    assert (item.visit_no, item.age, item.sex, item.from_branch, item.done_at, item.status) == (
        first.visit_no,
        "34 Y",
        "F",
        "B2",
        "MAIN",
        "in_lab",
    )
    assert item.sample_no.startswith("B2")

    # Filters: a department, a status, and work that has left the list.
    lipid_dept = lab.scalars(select(Test.department_id).where(Test.code == "lipid")).one()
    urine_dept = lab.scalars(select(Test.department_id).where(Test.code == "urine")).one()
    assert lipid_dept != urine_dept
    assert _listed(lab, platform, "suresh", department_id=urine_dept) == [
        ("Asha Testcase", "urine")
    ]
    _test(lab, first, "urine").status = "verified"
    lab.flush()
    assert _listed(lab, platform, "suresh") == [("Asha Testcase", "lipid")]
    assert _listed(lab, platform, "suresh", status="verified") == [("Asha Testcase", "urine")]
    assert _listed(lab, platform, "suresh", status="nonsense") == [("Asha Testcase", "lipid")]
    assert _listed(lab, platform, "suresh", status="sent_out") == []


@pytest.mark.item("M11")
def test_the_grid_holds_the_visits_tests_done_here(lab: Session, platform: Platform) -> None:
    visit = _visit(lab, platform, "lipid", "fbs")
    _receive(lab, platform, visit)
    kept = _test(lab, visit, "fbs")
    anil = as_user(lab, platform, "anil")
    service.route_test(lab, anil, kept.id, kept.row_version, branch_id=branch(lab, "B2").id)
    suresh = as_user(lab, platform, "suresh")
    lipid = _test(lab, visit, "lipid")
    entry.save_value(lab, suresh, lipid.id, _param(lab, "lipid", "TC").id, "250")
    entry.save_value(lab, suresh, lipid.id, _param(lab, "lipid", "HDL").id, "30")
    lab.flush()

    # At the main lab every branch's tests are in view, so both show.
    sheet = worklist.visit_sheet(lab, suresh, visit.id)
    assert (sheet.visit_no, sheet.patient_name, sheet.age, sheet.sex) == (
        visit.visit_no,
        "Sunita Testcase",
        "34 Y",
        "F",
    )
    assert [b.name for b in sheet.blocks] == ["Glucose, fasting", "Lipid profile"]
    glucose, panel = sheet.blocks
    # The centre's test can be read at the main lab but not typed there.
    assert (glucose.editable, panel.editable) == (False, True)
    assert not any(r.editable for r in glucose.rows)
    assert [r.parameter.code for r in panel.rows][:3] == ["TC", "TG", "HDL"]
    # Total cholesterol is high and so is what is calculated from it; HDL is low.
    assert panel.count("high") >= 1
    assert (panel.count("low"), panel.count("critical")) == (1, 0)
    assert panel.missing == 1
    assert sheet.elsewhere == []

    # The centre sees only its own test, and is told where the other one is.
    tara = as_user(lab, platform, "b2tech")
    theirs = worklist.visit_sheet(lab, tara, visit.id)
    assert [b.name for b in theirs.blocks] == ["Glucose, fasting"]
    # Collected where it is done, it needs no scan and can be typed at once.
    assert theirs.blocks[0].editable
    assert theirs.elsewhere == ["Lipid profile (MAIN)"]

    other = _visit(lab, platform, "lipid")
    with pytest.raises(NotFoundError):
        worklist.visit_sheet(lab, tara, other.id)
    with pytest.raises(NotFoundError):
        worklist.visit_sheet(lab, suresh, uuid.uuid4())
    with pytest.raises(PermissionDeniedError):
        worklist.visit_sheet(lab, anil, visit.id)

    # Once verified, nothing on the test can be typed.
    lipid.status = "verified"
    lab.flush()
    assert not worklist.visit_sheet(lab, suresh, visit.id).blocks[1].editable


@pytest.mark.item("M11")
@pytest.mark.item("M11.1")
def test_the_lab_screens(lab: Session, platform: Platform, db_client: TestClient) -> None:
    visit = _visit(lab, platform, "lipid", "urine")
    _receive(lab, platform, visit)
    patient = lab.get_one(Patient, visit.patient_id)
    lipid = _test(lab, visit, "lipid")
    suresh = as_user(lab, platform, "suresh")
    entry.save_value(lab, suresh, lipid.id, _param(lab, "lipid", "TC").id, "250")
    lab.flush()
    sign_in(db_client, "suresh")

    home = db_client.get("/").text
    assert '<span class="nav-group">Lab</span>' in home
    assert (
        f'href="/lab/worklist" data-shortcut="alt+w" aria-keyshortcuts="{SHORTCUTS["alt+w"].label}"'
        in home
    )
    assert "/static/lab.js" not in home

    listing = db_client.get("/lab/worklist")
    assert listing.status_code == 200
    assert f'href="/lab/visits/{visit.id}#t-{lipid.id}"' in listing.text
    assert "Lipid profile" in listing.text and "Urine routine" in listing.text
    assert "In the lab" in listing.text and "34 Y · Female" in listing.text
    assert '<option value="">To do</option>' in listing.text
    # The main lab may pick the branch whose list it looks at.
    assert 'name="branch"' in listing.text
    department = lab.scalars(select(Department.id).where(Department.name == "Biochemistry")).one()
    one = db_client.get(f"/lab/worklist?department={department}&status=in_lab&branch=x&page=abc")
    assert one.status_code == 200
    assert "Lipid profile" in one.text and "Urine routine" not in one.text
    none = db_client.get("/lab/worklist?status=verified").text
    assert "No tests match. Change the department or the status." in none

    grid = db_client.get(f"/lab/visits/{visit.id}")
    assert grid.status_code == 200
    assert '<script src="/static/lab.js" defer></script>' in grid.text
    assert grid.text.count("data-result-grid") == 2
    assert f'id="t-{lipid.id}"' in grid.text
    rows = re.findall(r'<tr id="r-[^"]+" class="result-row ([^"]+)"', grid.text)
    assert rows[:4] == ["flag-high", "flag-empty", "flag-empty", "flag-empty is-calculated"]
    assert grid.text.count('<span class="muted">(calc.)</span>') == 5
    assert "Legend:" in grid.text and "<kbd>Enter</kbd>" in grid.text
    # Every cell posts its own version and the token; calculated rows have nothing to post.
    cells = re.findall(
        r"<(?:input|select) class=\"(?:input|select)\" [^>]*name=\"value\"[^>]*>", grid.text
    )
    assert cells and all('"csrf_token": "' in cell and "hx-post=" in cell for cell in cells)
    ldl = grid.text.split(f'id="r-{lipid.id}-{_param(lab, "lipid", "LDL").id}"')[1].split("</tr>")[
        0
    ]
    assert "<output" in ldl and "hx-post" not in ldl
    # The urine ranges wait for approval; the lipid ones don't.
    assert "Range not approved" not in grid.text.split("Urine routine")[0]

    # Neither screen carries the patient's phone number or address.
    assert patient.phone and patient.address == ADDRESS
    for html in (listing.text, grid.text):
        assert patient.phone not in html and ADDRESS not in html

    script = db_client.get("/static/lab.js")
    assert script.status_code == 200 and "data-result-grid" in script.text
    assert db_client.get(f"/lab/visits/{uuid.uuid4()}").status_code == 404
    assert db_client.get("/lab/visits/nonsense").status_code == 404

    # A verified test is shown, not typed.
    lipid.status = "verified"
    lab.flush()
    done = db_client.get(f"/lab/visits/{visit.id}").text.split("Urine routine")[0]
    assert "Verified" in done and '<input class="input"' not in done and ">250<" in done

    sign_in(db_client, "meera")
    assert db_client.get("/lab/worklist").status_code == 200
    for username in ("priya", "anil"):
        sign_in(db_client, username)
        assert "/lab/worklist" not in db_client.get("/").text
        assert db_client.get("/lab/worklist").status_code == 403
        assert db_client.get(f"/lab/visits/{visit.id}").status_code == 403


@pytest.mark.item("EC-F01")
@pytest.mark.serial
def test_a_full_worklist_costs_no_more_queries_than_a_short_one_and_loads_in_time(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    statements: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    def load() -> tuple[int, float, str]:
        statements.clear()
        started = time.perf_counter()
        got = db_client.get("/lab/worklist")
        took = time.perf_counter() - started
        assert got.status_code == 200
        return len(statements), took, got.text

    _receive(lab, platform, _visit(lab, platform, "fbs", "lipid", "urine"))
    lab.commit()
    sign_in(db_client, "suresh")
    event.listen(lab.get_bind(), "before_cursor_execute", count)
    try:
        few, _, _ = load()
        for number in range(49):
            visit = _visit(
                lab, platform, "fbs", "lipid", "urine", name=f"Patient {number:02d} Test"
            )
            _receive(lab, platform, visit)
        lab.commit()
        waiting = lab.scalar(
            select(func.count()).select_from(OrderTest).where(OrderTest.status == "in_lab")
        )
        assert waiting == 150
        many, took, text = load()
    finally:
        event.remove(lab.get_bind(), "before_cursor_execute", count)

    # The list is one page of rows however long the queue is: no query per row.
    assert many <= few
    assert many <= 15
    assert took < 1.0
    assert "Next" in text
