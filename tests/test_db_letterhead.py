"""Setting a branch's letterhead: draft, upload, publish and discard, the preview and the
calibration page, and who may do it."""

import dataclasses
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core import lab_settings
from labra.core.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from labra.core.files import read_file
from labra.core.ids import utcnow
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.printing import service
from labra.printing.models import LetterheadLayout
from tests.frontdesk import as_user, branch, post, sign_in, upload
from tests.test_letterhead import _chars, _pdf_letterhead, _picture

pytestmark = [pytest.mark.item("M17"), pytest.mark.item("EC-K03")]

SVG_WITH_SCRIPT = (
    b"<svg xmlns='http://www.w3.org/2000/svg' width='210mm' height='297mm'"
    b" viewBox='0 0 210 297'><rect width='210' height='30' fill='#124'"
    b" onclick='alert(1)'/><script>alert(1)</script></svg>"
)


def _layout(margin_top: str = "40", **changes: str) -> service.LayoutInput:
    return service.LayoutInput(margin_top_mm=margin_top, **changes)


def _actions(db: Session, layout_id: object) -> list[str]:
    rows = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == str(layout_id)).order_by(AuditLog.id)
    )
    return [row.action for row in rows]


def test_a_draft_is_published_as_a_version_and_the_next_draft_starts_from_it(
    seeded: Session, platform: Platform
) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    main = branch(db, "MAIN")
    store = platform.filestore

    drafted = service.save_draft(db, anil, main.id, "report_a4", _layout("45"), 0)
    assert drafted.status == "draft" and drafted.margin_top_mm == Decimal(45)
    drafted, removed = service.upload(
        db, store, anil, main.id, "report_a4", _picture(), "head.png", drafted.row_version
    )
    assert removed == {}
    assert drafted.file_type == "raster" and drafted.raster_dpi == 150
    assert drafted.optimised_bytes < drafted.original_bytes
    first = service.publish(db, anil, main.id, "report_a4", drafted.row_version)
    assert (first.status, first.version) == ("published", 1)
    assert service.draft(db, main.id, "report_a4") is None

    second = service.save_draft(db, anil, main.id, "report_a4", _layout("50"), 0)
    assert second.id != first.id
    assert second.letterhead_file_id == first.letterhead_file_id
    assert second.file_type == "raster"
    service.publish(db, anil, main.id, "report_a4", second.row_version)
    assert service.published(db, main.id, "report_a4").version == 2  # type: ignore[union-attr]
    assert first.published_at is not None and second.published_at is not None
    older = service.published(db, main.id, "report_a4", at=first.published_at)
    assert older is not None and older.version == 1
    assert service.published(db, main.id, "report_a4", at=utcnow() - timedelta(days=1)) is None
    assert service.published(db, main.id, "bill_a4") is None
    assert _actions(db, first.id) == ["letterhead.draft", "letterhead.upload", "letterhead.publish"]


def test_an_svg_letterhead_is_stored_without_what_the_sanitiser_removed(
    seeded: Session, platform: Platform
) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    main = branch(db, "MAIN")
    layout, removed = service.upload(
        db, platform.filestore, anil, main.id, "report_a4", SVG_WITH_SCRIPT, "head.svg", 0
    )
    assert removed
    assert layout.file_type == "svg"
    assert layout.letterhead_file_id is not None and layout.original_file_id is not None
    _, drawn = read_file(db, platform.filestore, layout.letterhead_file_id)
    assert b"script" not in drawn and b"onclick" not in drawn
    _, kept = read_file(db, platform.filestore, layout.original_file_id)
    assert kept == SVG_WITH_SCRIPT


def test_a_pdf_letterhead_is_kept_as_its_first_page(seeded: Session, platform: Platform) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    layout, _ = service.upload(
        db, platform.filestore, anil, branch(db, "MAIN").id, "bill_a4", _pdf_letterhead(),
        "head.pdf", 0,
    )  # fmt: skip
    assert layout.file_type == "pdf" and layout.raster_dpi is None


def test_the_raster_resolution_follows_the_setting(seeded: Session, platform: Platform) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    lab_settings.set_value(db, "letterhead.raster_dpi", "200", anil.user_id)
    layout, _ = service.upload(
        db, platform.filestore, anil, branch(db, "MAIN").id, "report_a4", _picture(), "a.png", 0
    )
    assert layout.raster_dpi == 200
    assert layout.letterhead_file_id is not None
    _, drawn = read_file(db, platform.filestore, layout.letterhead_file_id)
    with Image.open(io.BytesIO(drawn)) as image:
        assert image.size == (1654, 2339)


def test_removing_the_file_brings_back_the_built_in_header(
    seeded: Session, platform: Platform
) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    main = branch(db, "MAIN")
    layout, _ = service.upload(
        db, platform.filestore, anil, main.id, "report_a4", _picture(), "a.png", 0
    )
    layout = service.remove_file(db, anil, main.id, "report_a4", layout.row_version)
    assert layout.letterhead_file_id is None and layout.file_type is None
    spec = service.spec_of(layout)
    assert spec.file_id is None
    rendered = service.render_sample(db, platform.filestore, main, spec, "short", "digital")
    text = "".join(c for c, _, _ in _chars(rendered.pdf)[0])
    assert "Labra Diagnostics" in text


def test_a_stale_or_vanished_draft_is_refused(seeded: Session, platform: Platform) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    main = branch(db, "MAIN")
    layout = service.save_draft(db, anil, main.id, "report_a4", _layout(), 0)
    old = layout.row_version
    service.save_draft(db, anil, main.id, "report_a4", _layout("41"), old)
    with pytest.raises(ConflictError):
        service.save_draft(db, anil, main.id, "report_a4", _layout("42"), old)
    service.discard(db, anil, main.id, "report_a4", layout.row_version)
    assert service.draft(db, main.id, "report_a4") is None
    with pytest.raises(ConflictError, match="published or discarded"):
        service.save_draft(db, anil, main.id, "report_a4", _layout("43"), layout.row_version)
    with pytest.raises(ConflictError, match="no draft"):
        service.publish(db, anil, main.id, "report_a4", 0)


def test_wrong_values_name_each_field(seeded: Session, platform: Platform) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    data = service.LayoutInput(
        margin_top_mm="200", margin_left_mm="x", font_size_pt="3", apply_on="odd"
    )
    with pytest.raises(ValidationFailedError) as refused:
        service.save_draft(db, anil, branch(db, "MAIN").id, "report_a4", data, 0)
    assert refused.value.errors == {
        "margin_top_mm": "Enter a number from 0 to 120 mm.",
        "margin_left_mm": "Enter a number from 0 to 60 mm.",
        "font_size_pt": "Enter a number from 7 to 14 pt.",
        "apply_on": "Choose every page or the first page only.",
    }
    with pytest.raises(ValidationFailedError) as not_a_file:
        service.upload(
            db, platform.filestore, anil, branch(db, "MAIN").id, "report_a4", b"hello", "a.txt", 0
        )
    assert list(not_a_file.value.errors) == ["file"]


def test_only_an_admin_of_that_branch_may_set_its_letterhead(
    seeded: Session, platform: Platform
) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    b2, main = branch(db, "B2"), branch(db, "MAIN")
    b2_only = dataclasses.replace(anil, grants={b2.id: anil.grants[b2.id]})
    assert [row.branch.code for row in service.overview(db, b2_only)] == ["B2"]
    service.save_draft(db, b2_only, b2.id, "report_a4", _layout(), 0)
    with pytest.raises(PermissionDeniedError):
        service.save_draft(db, b2_only, main.id, "report_a4", _layout(), 0)
    with pytest.raises(PermissionDeniedError):
        service.overview(db, as_user(db, platform, "priya"))


def test_the_calibration_page_moves_by_the_branch_printer_offset(
    seeded: Session, platform: Platform
) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    b2 = branch(db, "B2")
    plain = _chars(service.calibration(db, platform.filestore, anil, b2.id, "report_a4").pdf)[0]
    lab_settings.set_value(db, "print.offset_x_mm", "4", anil.user_id, branch_id=b2.id)
    moved = _chars(service.calibration(db, platform.filestore, anil, b2.id, "report_a4").pdf)[0]
    assert len(moved) == len(plain)
    assert moved[0][1] - plain[0][1] == pytest.approx(4 * 72 / 25.4, abs=0.2)
    main = branch(db, "MAIN")
    other = _chars(service.calibration(db, platform.filestore, anil, main.id, "report_a4").pdf)[0]
    assert other[0][1] != moved[0][1]


def test_a_published_layout_cannot_be_changed(seeded: Session, platform: Platform) -> None:
    db = seeded
    anil = as_user(db, platform, "anil")
    main = branch(db, "MAIN")
    layout = service.save_draft(db, anil, main.id, "report_a4", _layout(), 0)
    service.publish(db, anil, main.id, "report_a4", layout.row_version)
    with pytest.raises(ConflictError):
        service.discard(db, anil, main.id, "report_a4", layout.row_version)
    assert db.get(LetterheadLayout, layout.id) is not None


# Through the web


def _base(db: Session, code: str = "MAIN", kind: str = "report_a4") -> str:
    return f"/admin/letterheads/{branch(db, code).id}/{kind}"


def test_the_letterhead_screens_work_through_the_web(
    seeded: Session, db_client: TestClient
) -> None:
    db = seeded
    sign_in(db_client, "anil")
    listing = db_client.get("/admin/letterheads")
    assert listing.status_code == 200 and "Report (A4)" in listing.text
    url = _base(db)
    assert db_client.get(url).status_code == 200

    fields = dataclasses.asdict(service.LayoutInput())
    shown = post(db_client, f"{url}/preview", {**fields, "sample": "three_pages"})
    assert shown.status_code == 200 and 'src="data:image/png;base64,' in shown.text
    assert shown.text.count("data:image/png") == 3
    wrong = post(db_client, f"{url}/preview", {**fields, "margin_top_mm": "400"})
    assert wrong.status_code == 200 and "allowed value" in wrong.text

    calib = db_client.get(f"{url}/calibration")
    assert calib.status_code == 200
    assert calib.headers["content-type"] == "application/pdf"
    assert calib.headers["content-disposition"].startswith("inline;")

    refused = post(db_client, f"{url}/draft", {**fields, "margin_top_mm": "-1"})
    assert refused.status_code == 422 and "from 0 to 120" in refused.text
    saved = post(db_client, f"{url}/draft", {**fields, "margin_top_mm": "44"})
    assert saved.status_code == 303
    layout = service.draft(db, branch(db, "MAIN").id, "report_a4")
    assert layout is not None and layout.margin_top_mm == Decimal(44)

    sent = upload(
        db_client, f"{url}/upload", {"row_version": layout.row_version}, "h.svg", SVG_WITH_SCRIPT
    )
    assert sent.status_code == 200 and "removed" in sent.text.lower()
    db.refresh(layout)
    bad = upload(db_client, f"{url}/upload", {"row_version": layout.row_version}, "h.txt", b"hi")
    assert bad.status_code == 422

    done = post(db_client, f"{url}/publish", {"row_version": layout.row_version})
    assert done.status_code == 303
    assert service.published(db, branch(db, "MAIN").id, "report_a4") is not None


@pytest.mark.parametrize("username", ["priya", "b3desk", "meera"])
def test_people_who_are_not_admins_cannot_open_the_letterhead_screens(
    seeded: Session, db_client: TestClient, username: str
) -> None:
    sign_in(db_client, username)
    url = _base(seeded)
    assert db_client.get("/admin/letterheads").status_code == 403
    assert db_client.get(url).status_code == 403
    assert db_client.get(f"{url}/calibration").status_code == 403
    assert post(db_client, f"{url}/draft", {"margin_top_mm": "40"}).status_code == 403


def test_an_unknown_document_kind_is_not_found(seeded: Session, db_client: TestClient) -> None:
    sign_in(db_client, "anil")
    assert db_client.get(_base(seeded, kind="label")).status_code == 404
