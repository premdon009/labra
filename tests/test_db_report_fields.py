"""What the report will print, set on the admin screens and the result grid: a test's order,
research use and NABL scope, a branch's NABL number, a signatory's qualification,
registration number and signature, the sample's remarks and the method for each test."""

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.catalog import service as catalog
from labra.catalog.models import Test, TestMethod
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.files import read_file
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.org import service as org
from labra.org.models import AppUser
from labra.results import entry
from labra.seed import seed
from labra.visits.models import Sample
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, branch, post, sign_in
from tests.test_db_lab_entry import _approve, _enter, _in_lab, _test_id
from tests.test_signature import _scan


@pytest.fixture
def lab(db: Session, platform: Platform) -> Session:
    """The demo cast with the starter catalog, the lipid ranges approved."""
    seed(db, platform.identity, SEED_DAY, with_catalog=True)
    _approve(db, platform, "lipid")
    return db


def _user(db: Session, username: str) -> AppUser:
    return db.scalars(select(AppUser).where(AppUser.username == username)).one()


@pytest.mark.item("M12.1")
def test_a_tests_report_fields_are_saved_from_the_test_screen(
    lab: Session, db_client: TestClient
) -> None:
    seeded = lab
    test = lab.scalars(select(Test).where(Test.code == "lipid")).one()
    sign_in(db_client, "anil")
    form = {
        "test_id": str(test.id),
        "row_version": str(test.row_version),
        "code": test.code,
        "name": test.name,
        "department_id": str(test.department_id),
        "is_active": "true",
        "display_order": "15",
        "research_use": "true",
        "in_nabl_scope": "true",
    }
    page = db_client.get(f"/admin/catalog/tests/{test.id}").text
    assert 'name="display_order"' in page and 'name="in_nabl_scope"' in page

    assert post(db_client, "/admin/catalog/tests", form).status_code == 303
    seeded.refresh(test)
    assert (test.display_order, test.research_use, test.in_nabl_scope) == (15, True, True)

    form |= {"row_version": str(test.row_version), "display_order": "10000"}
    refused = post(db_client, "/admin/catalog/tests", form)
    assert refused.status_code == 422 and "Between 0 and 9999." in refused.text
    form |= {"display_order": "two"}
    assert post(db_client, "/admin/catalog/tests", form).status_code == 422
    del form["research_use"], form["in_nabl_scope"]
    assert post(db_client, "/admin/catalog/tests", form | {"display_order": "3"}).status_code == 303
    seeded.refresh(test)
    assert (test.display_order, test.research_use, test.in_nabl_scope) == (3, False, False)


@pytest.mark.item("M12.1")
def test_a_branch_keeps_its_nabl_number_in_capitals(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    anil = as_user(seeded, platform, "anil")
    main = branch(seeded, "MAIN")
    data = org.BranchInput(
        main.code, main.name, main.kind, main.address, main.state_code, nabl_cert_no=" mc-1234 "
    )
    org.update_branch(seeded, anil, main.id, data, main.row_version)
    assert main.nabl_cert_no == "MC-1234"

    for bad in ("MC 1234 <b>", "-1234", "M" * 41):
        data.nabl_cert_no = bad
        with pytest.raises(ValidationFailedError) as refused:
            org.update_branch(seeded, anil, main.id, data, main.row_version)
        assert "nabl_cert_no" in refused.value.errors

    sign_in(db_client, "anil")
    form = {
        "branch_id": str(main.id),
        "row_version": str(main.row_version),
        "code": main.code,
        "name": main.name,
        "kind": main.kind,
        "address": main.address,
        "state_code": main.state_code,
        "is_active": "true",
        "nabl_cert_no": "tc/5678",
    }
    assert 'value="MC-1234"' in db_client.get(f"/admin/branches/{main.id}").text
    assert post(db_client, "/admin/branches", form).status_code == 303
    seeded.refresh(main)
    assert main.nabl_cert_no == "TC/5678"


@pytest.mark.item("M12.1")
def test_a_signatory_has_a_qualification_and_registration_number(
    seeded: Session, db_client: TestClient
) -> None:
    meera = _user(seeded, "meera")
    sign_in(db_client, "anil")
    form = {
        "user_id": str(meera.id),
        "row_version": str(meera.row_version),
        "username": meera.username,
        "full_name": meera.full_name,
        "can_login": "true",
        "is_active": "true",
        "role": [f"{b}:{r}" for b, r in org.user_roles(seeded, meera.id)],
        "qualification": " MD (Pathology) ",
        "council_reg_no": "MMC 2009/01234",
    }
    assert post(db_client, "/admin/users", form).status_code == 303
    seeded.refresh(meera)
    assert (meera.qualification, meera.council_reg_no) == ("MD (Pathology)", "MMC 2009/01234")
    page = db_client.get(f"/admin/users/{meera.id}").text
    assert 'value="MD (Pathology)"' in page and 'value="MMC 2009/01234"' in page

    form |= {"row_version": str(meera.row_version), "qualification": "Q" * 81}
    refused = post(db_client, "/admin/users", form)
    assert refused.status_code == 422 and "Up to 80 characters." in refused.text


def _send_signature(client: TestClient, user: AppUser, content: bytes, version: int | None = None):
    token = client.get("/").text.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    return client.post(
        f"/admin/users/{user.id}/signature",
        data={
            "row_version": str(user.row_version if version is None else version),
            "csrf_token": token,
        },
        files={"signature": ("sig.jpg", content, "image/jpeg")},
        follow_redirects=False,
    )


@pytest.mark.item("M12")
def test_a_signature_is_uploaded_shown_and_removed(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    meera = _user(seeded, "meera")
    sign_in(db_client, "anil")
    assert "No signature yet." in db_client.get(f"/admin/users/{meera.id}").text

    assert _send_signature(db_client, meera, _scan((1800, 600))).status_code == 303
    seeded.refresh(meera)
    assert meera.signature_file_id is not None
    stored, png = read_file(seeded, platform.filestore, meera.signature_file_id)
    assert stored.mime == "image/png"
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == (600, 200)
    page = db_client.get(f"/admin/users/{meera.id}").text
    assert 'src="data:image/png;base64,' in page and "Remove the signature" in page
    audit = seeded.scalars(select(AuditLog).where(AuditLog.action == "user.signature")).one()
    assert audit.entity_id == str(meera.id) and audit.detail["removed"] is False

    # The name says JPEG; the bytes decide.
    refused = _send_signature(db_client, meera, b"%PDF-1.7 not a picture")
    assert refused.status_code == 422 and "This is not a JPEG or PNG file." in refused.text
    first, old = meera.signature_file_id, meera.row_version
    assert _send_signature(db_client, meera, _scan((900, 300))).status_code == 303
    seeded.refresh(meera)
    assert meera.signature_file_id not in {None, first}
    # What a second tab, opened before the replacement, would send.
    assert _send_signature(db_client, meera, _scan((900, 300)), old).status_code == 409
    seeded.refresh(meera)

    old = meera.row_version
    gone = post(db_client, f"/admin/users/{meera.id}/signature/remove", {"row_version": old})
    assert gone.status_code == 303
    seeded.refresh(meera)
    assert meera.signature_file_id is None
    again = post(db_client, f"/admin/users/{meera.id}/signature/remove", {"row_version": old})
    assert again.status_code == 409


@pytest.mark.item("M12")
def test_only_a_staff_editor_sets_a_signature(seeded: Session, db_client: TestClient) -> None:
    meera = _user(seeded, "meera")
    for username in ("meera", "priya", "b3desk"):
        sign_in(db_client, username)
        assert _send_signature(db_client, meera, _scan((600, 200))).status_code == 403
        url = f"/admin/users/{meera.id}/signature/remove"
        assert post(db_client, url, {"row_version": meera.row_version}).status_code == 403
    seeded.refresh(meera)
    assert meera.signature_file_id is None


def _methods(db: Session, platform: Platform, code: str = "lipid") -> list[TestMethod]:
    anil = as_user(db, platform, "anil")
    test_id = _test_id(db, code)
    return [
        catalog.save_method(db, anil, test_id, "Enzymatic (CHOD-PAP)", is_default=True),
        catalog.save_method(db, anil, test_id, "Direct homogeneous"),
    ]


@pytest.mark.item("M20")
def test_the_method_for_one_test_is_chosen_on_the_grid(lab: Session, platform: Platform) -> None:
    usual, other = _methods(lab, platform)
    ordered = _in_lab(lab, platform)
    suresh = as_user(lab, platform, "suresh")

    entry.set_method(lab, suresh, ordered.id, other.id, ordered.row_version)
    assert ordered.method_id == other.id
    entry.set_method(lab, suresh, ordered.id, None, ordered.row_version)
    assert ordered.method_id is None
    audits = lab.scalars(select(AuditLog).where(AuditLog.action == "order_test.method")).all()
    assert len(audits) == 2

    with pytest.raises(ValidationFailedError):
        entry.set_method(lab, suresh, ordered.id, uuid.uuid4(), ordered.row_version)
    elsewhere = catalog.save_method(
        lab, as_user(lab, platform, "anil"), _test_id(lab, "urine"), "Dipstick"
    )
    with pytest.raises(ValidationFailedError):
        entry.set_method(lab, suresh, ordered.id, elsewhere.id, ordered.row_version)
    with pytest.raises(ConflictError):
        entry.set_method(lab, suresh, ordered.id, other.id, ordered.row_version - 1)

    # A submitted test goes back for submission; a verified one is closed.
    _enter(lab, platform, ordered, TC="190", TG="120", HDL="50")
    ordered.status = "resulted"
    lab.flush()
    entry.set_method(lab, suresh, ordered.id, other.id, ordered.row_version)
    assert ordered.status == "in_lab"
    ordered.status = "verified"
    lab.flush()
    with pytest.raises(ConflictError):
        entry.set_method(lab, suresh, ordered.id, usual.id, ordered.row_version)
    priya = as_user(lab, platform, "priya")
    with pytest.raises(PermissionDeniedError):
        entry.set_method(lab, priya, ordered.id, usual.id, ordered.row_version)


@pytest.mark.item("M12.1")
def test_sample_remarks_are_saved_while_a_test_on_the_sample_is_open(
    lab: Session, platform: Platform
) -> None:
    ordered = _in_lab(lab, platform)
    sample = lab.get_one(Sample, ordered.sample_id)
    suresh = as_user(lab, platform, "suresh")

    entry.set_sample_remarks(lab, suresh, sample.id, "  Mildly   haemolysed ", sample.row_version)
    assert sample.remarks == "Mildly haemolysed"
    audit = lab.scalars(select(AuditLog).where(AuditLog.action == "sample.remarks")).one()
    assert audit.detail == {"chars": 17}

    with pytest.raises(ValidationFailedError):
        entry.set_sample_remarks(lab, suresh, sample.id, "x" * 301, sample.row_version)
    with pytest.raises(ConflictError):
        entry.set_sample_remarks(lab, suresh, sample.id, "Lipaemic", sample.row_version - 1)
    with pytest.raises(NotFoundError):
        entry.set_sample_remarks(lab, as_user(lab, platform, "priya"), sample.id, "x", 0)
    ordered.status = "verified"
    lab.flush()
    with pytest.raises(ConflictError):
        entry.set_sample_remarks(lab, suresh, sample.id, "Lipaemic", sample.row_version)


@pytest.mark.item("M20")
@pytest.mark.item("M12.1")
def test_the_grid_shows_and_saves_the_method_and_remarks(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    _, other = _methods(lab, platform)
    ordered = _in_lab(lab, platform)
    sample = lab.get_one(Sample, ordered.sample_id)
    sign_in(db_client, "suresh")
    grid = db_client.get(f"/lab/visits/{ordered.visit_id}").text
    assert f'action="/lab/tests/{ordered.id}/method"' in grid
    assert "Enzymatic (CHOD-PAP) (usual)" in grid
    assert f"Sample {sample.sample_no} remarks" in grid

    form = {"row_version": ordered.row_version, "method_id": str(other.id)}
    saved = post(db_client, f"/lab/tests/{ordered.id}/method", form)
    assert saved.status_code == 303
    assert saved.headers["location"] == f"/lab/visits/{ordered.visit_id}#t-{ordered.id}"
    lab.refresh(ordered)
    assert ordered.method_id == other.id

    url = f"/lab/samples/{sample.id}/remarks"
    form = {"row_version": sample.row_version, "remarks": "Lipaemic", "order_test_id": ordered.id}
    assert post(db_client, url, form).status_code == 303
    lab.refresh(sample)
    assert sample.remarks == "Lipaemic"
    too_long = post(
        db_client, url, form | {"row_version": sample.row_version, "remarks": "x" * 301}
    )
    assert too_long.status_code == 422 and "Up to 300 characters." in too_long.text

    ordered.status = "verified"
    lab.flush()
    closed = db_client.get(f"/lab/visits/{ordered.visit_id}").text
    assert f"Sample {sample.sample_no}: Lipaemic" in closed
    assert "Method: Direct homogeneous" in closed
    assert f'action="/lab/tests/{ordered.id}/method"' not in closed

    sign_in(db_client, "priya")
    assert post(db_client, url, form).status_code == 403
