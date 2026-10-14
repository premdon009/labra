"""What a report carries (design §7, §7.0; ISO 15189 §7.4.1.6), read back from the PDF the
signatory previews, and who may see that preview."""

import io
import re
import uuid
from decimal import Decimal

import pdfplumber
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.catalog import service as catalog
from labra.catalog.models import Test, TestMethod
from labra.core import lab_settings
from labra.core.errors import NotFoundError, PermissionDeniedError
from labra.core.registry import Platform
from labra.org.models import AppUser, Branch
from labra.patients.models import Patient
from labra.reports import service as reports
from labra.reports.content import Options
from labra.results import entry, outsourcing, service, signoff
from labra.seed import seed
from labra.visits import service as visits
from labra.visits.models import OrderTest, Sample, Visit
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, branch, sign_in, visit_input
from tests.test_db_lab_entry import _approve, _enter, _range, _result
from tests.test_db_lab_outsourcing import _value_row, _vitd
from tests.test_db_lab_routing import _ids
from tests.test_uploads import SMALL_PDF

MM = 72 / 25.4


@pytest.fixture
def lab(db: Session, platform: Platform) -> Session:
    """The demo cast and starter catalog, lipid and haemoglobin ranges approved."""
    seed(db, platform.identity, SEED_DAY, with_catalog=True)
    return _ready(db, platform)


def _ready(db: Session, platform: Platform) -> Session:
    """On a seeded database: lipid and haemoglobin ranges approved, prices for haemoglobin
    and TSH, and the signatory's qualification and registration number."""
    _approve(db, platform, "lipid")
    _approve(db, platform, "hb")
    anil = as_user(db, platform, "anil")
    for code in ("hb", "tsh"):
        test = db.scalars(select(Test).where(Test.code == code)).one()
        if not catalog.lab_prices(db, [test.id]):
            catalog.set_price(db, anil, "test", test.id, "200")
    meera = db.scalars(select(AppUser).where(AppUser.username == "meera")).one()
    meera.qualification = "MD (Pathology)"
    meera.council_reg_no = "XMC 00000"
    db.flush()
    return db


def _received(db: Session, platform: Platform, *codes: str) -> Visit:
    """A visit at Branch 2 whose samples are collected there and received at the main lab."""
    priya, suresh = as_user(db, platform, "priya"), as_user(db, platform, "suresh")
    visit = visits.save_visit(db, priya, visit_input(_ids(db, platform), *codes), SEED_DAY)
    for sample in db.scalars(select(Sample).where(Sample.visit_id == visit.id)).all():
        visits.collect_sample(db, priya, sample.sample_no, priya.user_id)
        service.receive_sample(db, suresh, sample.sample_no)
    return visit


def _ordered(db: Session, visit: Visit, code: str) -> OrderTest:
    return db.scalars(
        select(OrderTest)
        .join(Test, Test.id == OrderTest.test_id)
        .where(OrderTest.visit_id == visit.id, Test.code == code)
    ).one()


def _sign(db: Session, platform: Platform, ordered: OrderTest) -> None:
    signoff.submit(db, as_user(db, platform, "suresh"), ordered.id, ordered.row_version)
    signoff.verify(db, as_user(db, platform, "meera"), ordered.id, ordered.row_version)


def _day(db: Session, platform: Platform) -> Visit:
    """Lipid with a critical total cholesterol, haemoglobin by its second method on a sample
    with a remark, both signed off; TSH still in the lab."""
    _range(db, "lipid", "TC").critical_high = Decimal(400)
    db.flush()
    visit = _received(db, platform, "lipid", "hb", "tsh")
    suresh = as_user(db, platform, "suresh")
    lipid, hb = _ordered(db, visit, "lipid"), _ordered(db, visit, "hb")
    _enter(db, platform, lipid, TC=420, TG=120, HDL=45)
    told = _result(db, lipid, "TC")
    assert told is not None
    signoff.log_critical(db, suresh, told.id, informed_to="Dr Kavya Testcase", mode="phone")
    _enter(db, platform, hb, test="hb", HB="10.5")
    other = db.scalars(
        select(TestMethod).where(TestMethod.test_id == hb.test_id, ~TestMethod.is_default)
    ).first()
    assert other is not None
    entry.set_method(db, suresh, hb.id, other.id, hb.row_version)
    sample = db.get_one(Sample, hb.sample_id)
    entry.set_sample_remarks(db, suresh, sample.id, "Mildly haemolysed", sample.row_version)
    _sign(db, platform, lipid)
    _sign(db, platform, hb)
    return visit


def _pdf(db: Session, platform: Platform, visit: Visit, **options: object) -> bytes:
    chosen = Options(**options)  # type: ignore[arg-type]
    meera = as_user(db, platform, "meera")
    return reports.preview(db, platform.filestore, meera, visit.id, chosen).pdf


def _pages(pdf: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return [page.extract_text() or "" for page in doc.pages]


@pytest.mark.item("M12")
@pytest.mark.item("M12.1")
def test_the_report_carries_everything_iso_15189_asks_for(lab: Session, platform: Platform) -> None:
    visit = _day(lab, platform)
    text = "\n".join(_pages(_pdf(lab, platform, visit)))
    flat = " ".join(text.split())
    hb = _ordered(lab, visit, "hb")
    sample = lab.get_one(Sample, hb.sample_id)
    method = lab.get_one(TestMethod, hb.method_id)
    checklist = {
        "the lab that issued it": lab_settings.get_value(lab, "lab.display_name"),
        "the patient": "Sunita Testcase",
        "their number": lab.get_one(Patient, visit.patient_id).patient_no,
        "age and sex": "34 Y / F",
        "who asked for it": "Ref. by Self",
        "the visit": visit.visit_no,
        "the collecting branch": "Branch 2",
        "when collected, received and reported": "Received",
        "the department": "HAEMATOLOGY",
        "the test": "Lipid profile",
        "the specimen": "Serum",
        "the sample": sample.sample_no,
        "the method": f"Method: {method.name}",
        "a result with its unit": "420 HH mg/dL",
        "the reference interval": "Bio. ref. interval",
        "a calculated row": "(calc.)",
        "the critical call": "informed to Dr Kavya Testcase at",
        "the sample's condition": "Sample remarks",
        "the interpretation": "Friedewald",
        "what is still pending": "Pending: Thyroid stimulating hormone (expected",
        "that it is partial": "PARTIAL REPORT",
        "that it is a preview": "PREVIEW: not released",
        "who signs": "Dr Meera Nair",
        "their qualification": "MD (Pathology)",
        "their registration": "Reg. no. XMC 00000",
        "the page count": "Page 1 of 2",
        "the end": "End of report",
    }
    missing = [what for what, words in checklist.items() if words and words not in flat]
    assert missing == []
    # Departments in the catalog's report order, values in bold only when flagged.
    assert flat.index("HAEMATOLOGY") < flat.index("BIOCHEMISTRY")
    assert re.search(r"Haemoglobin 10\.5 L g/dL", flat)
    # No test is in a NABL scope, so no certificate number is claimed.
    assert "NABL" not in flat


@pytest.mark.item("M12")
def test_values_out_of_range_are_bold_and_nothing_is_in_colour(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    with pdfplumber.open(io.BytesIO(_pdf(lab, platform, visit))) as doc:
        chars = doc.pages[0].chars
    colours = {tuple(c.get("non_stroking_color") or ()) for c in chars}
    assert colours <= {(), (0,), (0, 0, 0), (0.2, 0.2, 0.2), (0.2,)}
    bold = "".join(c["text"] for c in chars if "Bold" in c["fontname"])
    assert "420" in bold and "10.5" in bold
    assert "120" not in bold  # triglycerides inside the interval


@pytest.mark.item("M20")
def test_the_options_choose_paper_reference_column_and_tests(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    lipid = _ordered(lab, visit, "lipid")

    a5 = _pdf(lab, platform, visit, paper="A5")
    with pdfplumber.open(io.BytesIO(a5)) as doc:
        page = doc.pages[0]
        assert (round(page.width / MM), round(page.height / MM)) == (148, 210)

    plain = " ".join(_pages(_pdf(lab, platform, visit, reference=False)))
    assert "Bio. ref. interval" not in plain and "Lipid profile" in plain

    chosen = " ".join(_pages(_pdf(lab, platform, visit, tests=frozenset({str(lipid.id)}))))
    assert "Lipid profile" in chosen and "Haemoglobin" not in chosen
    assert "Selected tests only: 1 of 2 on this report" in " ".join(chosen.split())
    # A test that isn't on the report can't be chosen to widen it.
    stray = frozenset({str(uuid.uuid4())})
    assert "Selected tests only" not in " ".join(_pages(_pdf(lab, platform, visit, tests=stray)))


@pytest.mark.item("M12")
def test_the_nabl_number_prints_only_when_every_test_is_in_scope(
    lab: Session, platform: Platform
) -> None:
    visit = _day(lab, platform)
    main = branch(lab, "MAIN")
    main.nabl_cert_no = "MC-0000"
    lipid = _ordered(lab, visit, "lipid")
    hb = _ordered(lab, visit, "hb")
    lab.get_one(Test, lipid.test_id).in_nabl_scope = True
    lab.flush()
    assert "NABL" not in " ".join(_pages(_pdf(lab, platform, visit)))
    only_lipid = frozenset({str(lipid.id)})
    assert "NABL certificate no. MC-0000" in " ".join(
        _pages(_pdf(lab, platform, visit, tests=only_lipid))
    )
    lab.get_one(Test, hb.test_id).in_nabl_scope = True
    lab.flush()
    assert "NABL certificate no. MC-0000" in " ".join(_pages(_pdf(lab, platform, visit)))


@pytest.mark.item("M12")
def test_an_outside_test_is_marked_with_its_lab_and_a_research_test_is_flagged(
    seeded: Session, platform: Platform
) -> None:
    db = seeded
    visit, ordered, lab = _vitd(db, platform)
    lab.nabl_cert_no = "MC-9999"
    row = _value_row(db, platform)
    suresh = as_user(db, platform, "suresh")
    outsourcing.mark_sent(db, suresh, ordered.id, ordered.row_version, "RL-2291")
    outsourcing.attach_result(
        db, platform.filestore, suresh, visit.id, lab.id, SMALL_PDF, [ordered.id]
    )
    entry.save_value(db, suresh, ordered.id, row, "32.5", 0)
    db.get_one(Test, ordered.test_id).research_use = True
    _sign(db, platform, ordered)
    # Done outside, so never under the main lab's NABL number.
    db.get_one(Test, ordered.test_id).in_nabl_scope = True
    db.get_one(Branch, ordered.perform_branch_id).nabl_cert_no = "MC-0000"
    db.flush()

    flat = " ".join(" ".join(_pages(_pdf(db, platform, visit))).split())
    assert "Vitamin D, 25-hydroxy * †" in flat
    assert (
        f"* Vitamin D, 25-hydroxy: performed by {lab.name} (NABL MC-9999), accession RL-2291"
        in flat
    )
    assert "† For research use only" in flat
    # A value was typed from the outside lab's PDF, so the PDF isn't added.
    assert "See the attached" not in flat and "Attached after the last page" not in flat
    assert "PARTIAL" not in flat
    assert "NABL certificate no." not in flat


@pytest.mark.item("M12")
def test_only_a_signatory_where_the_tests_were_done_sees_the_report(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _day(lab, platform)
    nothing_yet = _received(lab, platform, "tsh")
    for username in ("priya", "suresh", "anil", "b3desk"):
        with pytest.raises(PermissionDeniedError):
            reports.preview(
                lab, platform.filestore, as_user(lab, platform, username), visit.id, Options()
            )
    meera = as_user(lab, platform, "meera")
    with pytest.raises(NotFoundError):
        reports.plan(lab, meera, nothing_yet.id)
    with pytest.raises(NotFoundError):
        reports.plan(lab, meera, uuid.uuid4())
    lab.commit()

    sign_in(db_client, "meera")
    screen = db_client.get(f"/reports/visits/{visit.id}")
    assert screen.status_code == 200
    assert "Lipid profile" in screen.text and "Thyroid stimulating hormone" in screen.text
    grid = db_client.get(f"/lab/visits/{visit.id}")
    assert f'href="/reports/visits/{visit.id}"' in grid.text
    shown = db_client.get(f"/reports/visits/{visit.id}/preview?paper=A5&reference=0")
    assert shown.status_code == 200
    assert shown.headers["content-type"] == "application/pdf"
    assert shown.headers["content-disposition"] == 'inline; filename="report-preview.pdf"'
    assert db_client.get(f"/reports/visits/{nothing_yet.id}").status_code == 404

    sign_in(db_client, "priya")
    assert db_client.get(f"/reports/visits/{visit.id}").status_code == 403
    assert db_client.get(f"/reports/visits/{visit.id}/preview").status_code == 403
