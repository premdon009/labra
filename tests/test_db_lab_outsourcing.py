"""Tests done by an outside lab: sending, the sheet that goes with the samples, the result
PDF that comes back, and the timeline of each test."""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.billing import service as billing
from labra.billing.models import Bill
from labra.catalog import service as catalog
from labra.core.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from labra.core.files import MAX_BYTES
from labra.core.models import AuditLog, EventOutbox, StoredFile
from labra.core.registry import Platform
from labra.extlabs.models import ExternalLab
from labra.patients.models import Patient
from labra.results import entry, outsourcing, service, signoff
from labra.results.models import ExternalDocument, OrderTestEvent, Result
from labra.seed import make_user
from labra.visits.models import OrderTest, Visit
from tests.frontdesk import as_user, branch, post, sign_in, upload
from tests.test_db_lab_routing import _collect, _ids, _lab, _sample, _tests, _visit
from tests.test_uploads import SMALL_PDF

LAB_NAME = "Synthetic Referral Lab A"


def _vitd(
    db: Session, platform: Platform, collected: bool = True
) -> tuple[Visit, OrderTest, ExternalLab]:
    """A vitamin D test ordered at Branch 2 and routed to an outside lab at ₹700."""
    visit = _visit(db, platform, "priya", "vitd")
    (ordered,) = _tests(db, visit)
    if collected:
        _collect(db, as_user(db, platform, "priya"), _sample(db, visit))
    lab = _lab(db, as_user(db, platform, "anil"), LAB_NAME, "700", 48)
    suresh = as_user(db, platform, "suresh")
    service.route_test(db, suresh, ordered.id, ordered.row_version, external_lab_id=lab.id)
    return visit, ordered, lab


def _sent(db: Session, platform: Platform) -> tuple[Visit, OrderTest, ExternalLab]:
    visit, ordered, lab = _vitd(db, platform)
    suresh = as_user(db, platform, "suresh")
    outsourcing.mark_sent(db, suresh, ordered.id, ordered.row_version, "RL-2291")
    return visit, ordered, lab


def _value_row(db: Session, platform: Platform) -> uuid.UUID:
    """One row on the vitamin D test, so its value can be typed."""
    row = catalog.ParameterInput(
        code="VITD", name="Vitamin D", result_type="numeric", unit_ucum="ng/mL", decimals=1
    )
    admin = as_user(db, platform, "anil")
    return catalog.save_parameter(db, admin, _ids(db, platform)["vitd"], row).id


def _centre_technician(db: Session, platform: Platform) -> str:
    """A technician of Branch 3 only."""
    make_user(
        db, platform.identity, "b3tech", "Ravi Synthetic", [(branch(db, "B3").id, "technician")]
    )
    return "b3tech"


def _problem(call) -> str:
    with pytest.raises(ValidationFailedError) as refused:
        call()
    return " ".join(refused.value.errors.values())


@pytest.mark.item("M10")
@pytest.mark.item("M26")
@pytest.mark.item("M07.4")
def test_a_sample_is_marked_sent_once_and_the_bill_is_then_kept(
    seeded: Session, platform: Platform
) -> None:
    visit, ordered, lab = _vitd(seeded, platform, collected=False)
    suresh = as_user(seeded, platform, "suresh")
    priya = as_user(seeded, platform, "priya")

    with pytest.raises(PermissionDeniedError):
        outsourcing.mark_sent(seeded, priya, ordered.id, ordered.row_version)
    assert "isn't collected yet" in _problem(
        lambda: outsourcing.mark_sent(seeded, suresh, ordered.id, ordered.row_version)
    )
    _collect(seeded, priya, _sample(seeded, visit))
    with pytest.raises(ConflictError):
        outsourcing.mark_sent(seeded, suresh, ordered.id, ordered.row_version + 1)
    assert "at most 40" in _problem(
        lambda: outsourcing.mark_sent(seeded, suresh, ordered.id, ordered.row_version, "9" * 41)
    )
    assert "letters, digits" in _problem(
        lambda: outsourcing.mark_sent(seeded, suresh, ordered.id, ordered.row_version, "<b>")
    )
    assert ordered.status == "collected"

    outsourcing.mark_sent(seeded, suresh, ordered.id, ordered.row_version, " RL-2291 ")

    assert (ordered.status, ordered.external_accession_no) == ("sent_out", "RL-2291")
    event = seeded.scalars(select(OrderTestEvent).where(OrderTestEvent.event == "sent")).one()
    assert (event.note, event.by) == (f"To {LAB_NAME}, their number RL-2291", suresh.user_id)
    logged = seeded.scalars(select(AuditLog).where(AuditLog.action == "test.send")).one()
    assert logged.detail == {
        "visit_id": str(visit.id),
        "external_lab_id": str(lab.id),
        "external_cost": "700.00",
        "accession_no": "RL-2291",
    }
    queued = seeded.scalars(select(EventOutbox).where(EventOutbox.topic == "test.sent_out")).one()
    assert queued.payload == {
        "schema_version": 1,
        "entity": "order_test",
        "entity_id": str(ordered.id),
        "visit_id": str(visit.id),
        "test_id": str(ordered.test_id),
        "branch_id": str(branch(seeded, "B2").id),
        "perform_branch_id": str(branch(seeded, "MAIN").id),
        "external_lab_id": str(lab.id),
        "external_cost": "700.00",
    }
    with pytest.raises(ConflictError, match="already sent"):
        outsourcing.mark_sent(seeded, suresh, ordered.id, ordered.row_version)

    # The outside lab's number can be put right while the sample is with them.
    outsourcing.set_accession(seeded, suresh, ordered.id, ordered.row_version, "RL-2292")
    assert ordered.external_accession_no == "RL-2292"
    assert seeded.scalars(select(AuditLog).where(AuditLog.action == "test.accession")).one()
    with pytest.raises(PermissionDeniedError):
        outsourcing.set_accession(seeded, priya, ordered.id, ordered.row_version, "X")

    # The outside lab will charge for it, so the bill stays.
    bill = seeded.scalars(select(Bill).where(Bill.visit_id == visit.id)).one()
    with pytest.raises(ConflictError, match="can't be cancelled"):
        billing.cancel_bill(
            seeded, as_user(seeded, platform, "anil"), bill.id, "Booked twice", True, 1
        )
    assert bill.status != "cancelled"


@pytest.mark.item("EC-C02")
@pytest.mark.item("M10")
def test_the_sheet_for_an_outside_lab_has_no_phone_or_address_unless_the_lab_is_given_them(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit, ordered, lab = _vitd(seeded, platform)
    patient = seeded.get_one(Patient, visit.patient_id)
    patient.address = "12 Synthetic Street, Testpur"
    seeded.commit()
    suresh = as_user(seeded, platform, "suresh")

    sheet = outsourcing.send_sheet(seeded, suresh, lab.id)
    assert [(r.patient_name, r.test_name, r.phone, r.address) for r in sheet.rows] == [
        (patient.full_name, "Vitamin D, 25-hydroxy", "", "")
    ]
    assert sheet.rows[0].sample_no == _sample(seeded, visit).sample_no

    sign_in(db_client, "suresh")
    path = f"/lab/outsourcing/sheet/{lab.id}"
    printed = db_client.get(path).text
    assert f"Samples for {LAB_NAME}" in printed and patient.full_name in printed
    assert patient.phone not in printed and "Synthetic Street" not in printed
    assert "<th>Phone</th>" not in printed and "<th>Address</th>" not in printed

    lab.share_phone = True
    seeded.commit()
    printed = db_client.get(path).text
    assert patient.phone in printed and "Synthetic Street" not in printed
    lab.share_address = True
    seeded.commit()
    assert "Synthetic Street" in db_client.get(path).text

    # The front desk has no business with the sheet; a sent test is no longer on it.
    sign_in(db_client, "priya")
    assert db_client.get(path).status_code == 403
    outsourcing.mark_sent(seeded, suresh, ordered.id, ordered.row_version)
    assert outsourcing.send_sheet(seeded, suresh, lab.id).rows == []


@pytest.mark.item("EC-A07")
@pytest.mark.item("M10")
def test_only_a_real_pdf_is_attached_as_an_outside_labs_result(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit, ordered, lab = _sent(seeded, platform)
    other = _lab(seeded, as_user(seeded, platform, "anil"), "Synthetic Referral Lab B", "620", 72)
    centre = _centre_technician(seeded, platform)
    seeded.commit()
    path = f"/lab/visits/{visit.id}/documents"
    form = {"lab": str(lab.id), "tests": [str(ordered.id)]}

    def stored() -> int:
        files = seeded.scalar(select(func.count()).select_from(StoredFile)) or 0
        return files + (seeded.scalar(select(func.count()).select_from(ExternalDocument)) or 0)

    sign_in(db_client, "suresh")
    assert "Results from outside labs" in db_client.get(f"/lab/visits/{visit.id}").text

    # A web page with a .pdf name is not a PDF.
    page = b"<html><script>alert(1)</script></html>"
    refused = upload(db_client, path, form, "result.pdf", page)
    assert refused.status_code == 422
    assert "This is not a PDF file. Its name alone doesn&#39;t make it one." in refused.text
    # Nor is one dressed up with a PDF's first and last line.
    dressed = b"%PDF-1.7\n<script>alert(1)</script>\n%%EOF\n"
    assert upload(db_client, path, form, "result.pdf", dressed).status_code == 422
    too_big = upload(db_client, path, form, "big.pdf", SMALL_PDF + b"\n" * MAX_BYTES)
    assert too_big.status_code == 422 and "larger than 20 MB" in too_big.text
    assert upload(db_client, path, form, "empty.pdf", b"").status_code == 422
    unticked = upload(db_client, path, {"lab": str(lab.id)}, "result.pdf", SMALL_PDF)
    assert unticked.status_code == 422 and "Tick the tests" in unticked.text
    wrong_lab = upload(db_client, path, {**form, "lab": str(other.id)}, "result.pdf", SMALL_PDF)
    assert wrong_lab.status_code == 409
    assert stored() == 0
    seeded.refresh(ordered)
    assert ordered.status == "sent_out"

    # Staff who don't enter results where the test is done can't attach one.
    for username in ("priya", "anil", centre):
        sign_in(db_client, username)
        assert upload(db_client, path, form, "result.pdf", SMALL_PDF).status_code == 403
    assert stored() == 0

    sign_in(db_client, "suresh")
    done = upload(db_client, path, form, "anything at all.pdf", SMALL_PDF)
    assert (done.status_code, done.headers["location"]) == (303, f"/lab/visits/{visit.id}#outside")
    seeded.refresh(ordered)
    assert ordered.status == "in_lab"
    document = seeded.scalars(select(ExternalDocument)).one()
    file = seeded.get_one(StoredFile, document.file_id)
    # The name the outside lab gave the file is not kept.
    assert (file.filename, file.mime, file.size) == (
        f"external-result-{visit.visit_no}.pdf",
        "application/pdf",
        len(SMALL_PDF),
    )
    back = seeded.scalars(
        select(OrderTestEvent).where(OrderTestEvent.event == "received_back")
    ).one()
    assert back.note == f"Result PDF from {LAB_NAME}"
    logged = seeded.scalars(select(AuditLog).where(AuditLog.action == "result.document")).one()
    assert logged.detail["tests"] == [str(ordered.id)] and logged.detail["sha256"] == file.sha256

    again = upload(db_client, path, form, "result.pdf", SMALL_PDF)
    assert again.status_code == 422 and "already attached" in again.text

    # It comes back as a download with Labra's own name and type, never shown in the page.
    link = f"/lab/documents/{document.id}"
    assert link in db_client.get(f"/lab/visits/{visit.id}").text
    got = db_client.get(link)
    assert got.status_code == 200 and got.content == SMALL_PDF
    assert got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"] == (
        f'attachment; filename="external-result-{visit.visit_no}-{file.sha256[:8]}.pdf"'
    )
    assert got.headers["x-content-type-options"] == "nosniff"
    for username in ("priya", centre):
        sign_in(db_client, username)
        assert db_client.get(link).status_code == 403
    assert db_client.get(f"/lab/documents/{uuid.uuid4()}").status_code in (403, 404)


@pytest.mark.item("M10")
@pytest.mark.item("M11")
def test_an_outside_result_is_typed_only_after_its_pdf_and_is_then_verified(
    seeded: Session, platform: Platform
) -> None:
    visit, ordered, lab = _vitd(seeded, platform)
    row = _value_row(seeded, platform)
    suresh = as_user(seeded, platform, "suresh")
    meera = as_user(seeded, platform, "meera")

    def typed(value: str) -> Result:
        return entry.save_value(seeded, suresh, ordered.id, row, value, 0).result

    # Before it goes and while it is away, there is nothing to type or submit.
    with pytest.raises(ConflictError, match="Attach the lab's PDF first"):
        typed("32.5")
    outsourcing.mark_sent(seeded, suresh, ordered.id, ordered.row_version)
    with pytest.raises(ConflictError, match="with an outside lab"):
        typed("32.5")
    with pytest.raises(ConflictError):
        signoff.submit(seeded, suresh, ordered.id, ordered.row_version)

    # A signatory enters results too, but the front desk doesn't.
    with pytest.raises(PermissionDeniedError):
        outsourcing.attach_result(
            seeded,
            platform.filestore,
            as_user(seeded, platform, "priya"),
            visit.id,
            lab.id,
            SMALL_PDF,
            [ordered.id],
        )
    outsourcing.attach_result(
        seeded, platform.filestore, suresh, visit.id, lab.id, SMALL_PDF, [ordered.id]
    )
    assert ordered.status == "in_lab"

    saved = typed("32.5")
    assert (saved.value_num, saved.source) == (Decimal("32.5"), "external_pdf")

    # A corrected PDF can replace nothing but can be added until the test is verified.
    corrected = SMALL_PDF + b"%%EOF\n"
    outsourcing.attach_result(
        seeded, platform.filestore, suresh, visit.id, lab.id, corrected, [ordered.id]
    )
    (group,) = outsourcing.outside_results(seeded, suresh, visit.id)
    assert (group.lab_name, len(group.documents)) == (LAB_NAME, 2)
    assert group.documents[0].tests == ["Vitamin D, 25-hydroxy"]

    signoff.submit(seeded, suresh, ordered.id, ordered.row_version)
    assert ordered.status == "resulted"
    signoff.verify(seeded, meera, ordered.id, ordered.row_version)
    assert ordered.status == "verified"
    with pytest.raises(ConflictError):
        outsourcing.attach_result(
            seeded, platform.filestore, suresh, visit.id, lab.id, SMALL_PDF + b"\n", [ordered.id]
        )
    assert outsourcing.outside_results(seeded, suresh, visit.id)[0].tests == []


@pytest.mark.item("M21")
def test_the_timeline_says_what_happened_to_a_test_when_and_by_whom(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit, ordered, lab = _sent(seeded, platform)
    suresh = as_user(seeded, platform, "suresh")
    outsourcing.attach_result(
        seeded, platform.filestore, suresh, visit.id, lab.id, SMALL_PDF, [ordered.id]
    )
    signoff.submit(seeded, suresh, ordered.id, ordered.row_version)
    signoff.verify(seeded, as_user(seeded, platform, "meera"), ordered.id, ordered.row_version)
    seeded.commit()

    steps = outsourcing.timelines(seeded, [ordered.id])[ordered.id]

    assert [(s.event, s.by) for s in steps] == [
        ("registered", "Priya Sharma"),
        ("collected", "Priya Sharma"),
        ("routed", "Suresh Iyer"),
        ("sent", "Suresh Iyer"),
        ("received_back", "Suresh Iyer"),
        ("resulted", "Suresh Iyer"),
        ("verified", "Dr Meera Nair, MD"),
    ]
    assert [s.at for s in steps] == sorted(s.at for s in steps)
    assert steps[3].note == f"To {LAB_NAME}, their number RL-2291"

    sign_in(db_client, "suresh")
    grid = db_client.get(f"/lab/visits/{visit.id}").text
    assert "their number RL-2291" in grid
    grid = grid[grid.index('class="timeline"') :]
    shown = [
        grid.index(f"<strong>{label}</strong>")
        for label in (
            "Registered",
            "Sample collected",
            "Sent to the outside lab",
            "Result received",
            "Verified",
        )
    ]
    assert shown == sorted(shown)


@pytest.mark.item("M10")
@pytest.mark.item("M09")
def test_the_outsourcing_screen_takes_a_test_from_in_house_to_sent(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    visit = _visit(seeded, platform, "priya", "vitd")
    (ordered,) = _tests(seeded, visit)
    lab = _lab(seeded, as_user(seeded, platform, "anil"), LAB_NAME, "700", 48)
    patient = seeded.get_one(Patient, visit.patient_id)
    seeded.commit()

    def send(path: str, **form: object):
        seeded.refresh(ordered)
        return post(db_client, f"/lab/tests/{ordered.id}/{path}", form)

    sign_in(db_client, "priya")
    assert db_client.get("/lab/outsourcing").status_code == 403

    # The admin routes tests but doesn't enter results: this screen is where they do it.
    sign_in(db_client, "anil")
    board = db_client.get("/lab/outsourcing").text
    assert "Could go to an outside lab" in board and patient.full_name in board
    assert "cost ₹700.00, margin ₹600.00, 48 h" in board
    assert patient.phone not in board
    assert f'href="/lab/visits/{visit.id}' not in board

    moved = send("route", row_version=ordered.row_version, to=f"lab:{lab.id}", back="outsourcing")
    assert (moved.status_code, moved.headers["location"]) == (303, "/lab/outsourcing")
    board = db_client.get("/lab/outsourcing").text
    assert "Sample not collected yet" in board and "Could go to an outside lab" not in board
    assert f"/lab/outsourcing/sheet/{lab.id}" not in board

    _collect(seeded, as_user(seeded, platform, "priya"), _sample(seeded, visit))
    seeded.commit()
    board = db_client.get("/lab/outsourcing").text
    assert f"/lab/outsourcing/sheet/{lab.id}" in board and "Mark sent" in board

    bad = send("send", row_version=ordered.row_version, accession_no="<b>")
    assert bad.status_code == 422 and "letters, digits" in bad.text
    assert send("send", row_version=ordered.row_version + 1).status_code == 409
    sent = send("send", row_version=ordered.row_version, accession_no="RL-2291")
    assert sent.status_code == 303
    board = db_client.get("/lab/outsourcing").text
    assert "No test is waiting to go to an outside lab." in board
    assert 'value="RL-2291"' in board and "Sent to the outside lab" in board
    assert "Attach the result" not in board

    fixed = send("accession", row_version=ordered.row_version, accession_no="RL-2292")
    assert fixed.status_code == 303
    seeded.refresh(ordered)
    assert (ordered.status, ordered.external_accession_no) == ("sent_out", "RL-2292")

    # The technician gets the way to the visit, where the PDF is attached.
    sign_in(db_client, "suresh")
    board = db_client.get("/lab/outsourcing").text
    assert f'href="/lab/visits/{visit.id}#outside"' in board
    sign_in(db_client, "priya")
    assert send("send", row_version=ordered.row_version).status_code == 403
