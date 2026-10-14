"""The report tables: a released report can only be superseded, what was printed or handed
over is append-only, a published letterhead is final, and who may release, see and deliver."""

import secrets
import uuid
from importlib import import_module
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from labra.core.models import NumberSeries, StoredFile
from labra.core.numbering import next_number
from labra.core.registry import Platform
from labra.org.models import Branch
from labra.org.permissions import PERMISSIONS, SYSTEM_ROLES
from labra.printing.models import LetterheadLayout
from labra.reports.models import Report, ReportDelivery, ReportPrint, ReportTest
from labra.results.models import OrderTestEvent
from labra.visits import service as visits
from labra.visits.models import OrderTest, Visit
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, branch, menu, visit_input


def _file(db: Session) -> StoredFile:
    stored = StoredFile(
        sha256="0" * 64, storage_key="synthetic", size=1, filename="r.pdf", mime="application/pdf"
    )
    db.add(stored)
    db.flush()
    return stored


def _report(db: Session, visit: Visit, user_id: uuid.UUID, **changes: Any) -> Report:
    values: dict[str, Any] = {
        "report_no": f"B2/R/2627/{uuid.uuid4().int % 10**6:06d}",
        "visit_id": visit.id,
        "released_by": user_id,
        "file_id": _file(db).id,
        "sha256": "a" * 64,
        "content": {"tests": []},
        "verify_token": secrets.token_urlsafe(16),
    }
    values.update(changes)
    report = Report(**values)
    db.add(report)
    db.flush()
    return report


@pytest.fixture
def released(seeded: Session, platform: Platform) -> tuple[Report, OrderTest, uuid.UUID]:
    """A released report with one test, one print and one delivery."""
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    priya = as_user(seeded, platform, "priya")
    visit = visits.save_visit(seeded, priya, visit_input(ids, "fbs"), SEED_DAY)
    ordered = seeded.scalars(select(OrderTest).where(OrderTest.visit_id == visit.id)).one()
    report = _report(seeded, visit, priya.user_id)
    seeded.add_all(
        [
            ReportTest(report_id=report.id, order_test_id=ordered.id),
            ReportPrint(report_id=report.id, output="print", printed_by=priya.user_id),
            ReportDelivery(
                report_id=report.id,
                delivered_to="Asha Testcase",
                mode="counter",
                delivered_by=priya.user_id,
            ),
        ]
    )
    seeded.flush()
    return report, ordered, priya.user_id


@pytest.mark.item("M12")
@pytest.mark.parametrize(
    "statement",
    [
        "update report set content = '{}'",
        "update report set sha256 = repeat('b', 64)",
        "update report set report_no = 'B2/R/2627/999999'",
        "update report set amendment_reason = 'Later'",
        "update report set status = 'superseded', amendment_reason = 'Later'",
        "update report set verify_token = 'x'",
    ],
)
def test_a_released_report_cannot_change(
    seeded: Session, released: tuple[Report, OrderTest, uuid.UUID], statement: str
) -> None:
    with pytest.raises(DBAPIError, match="can only be superseded"), seeded.begin_nested():
        seeded.execute(text(statement))


@pytest.mark.item("M12")
def test_a_released_report_is_kept(
    seeded: Session, released: tuple[Report, OrderTest, uuid.UUID]
) -> None:
    with pytest.raises(DBAPIError, match="is kept"), seeded.begin_nested():
        seeded.execute(text("delete from report"))
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(text("truncate report cascade"))


@pytest.mark.item("M12")
def test_a_report_is_superseded_once_by_its_next_version(
    seeded: Session, released: tuple[Report, OrderTest, uuid.UUID]
) -> None:
    first, _, user_id = released
    visit = seeded.get_one(Visit, first.visit_id)
    # Two current versions of one number are refused.
    with pytest.raises(IntegrityError, match="uq_report_current"), seeded.begin_nested():
        _report(
            seeded,
            visit,
            user_id,
            report_no=first.report_no,
            version=2,
            supersedes_report_id=first.id,
        )
    seeded.execute(text("update report set status = 'superseded' where id = :id"), {"id": first.id})
    second = _report(
        seeded, visit, user_id, report_no=first.report_no, version=2, supersedes_report_id=first.id
    )
    assert second.status == "released"
    # A superseded version stays superseded.
    with pytest.raises(DBAPIError, match="can only be superseded"), seeded.begin_nested():
        seeded.execute(
            text("update report set status = 'released' where id = :id"), {"id": first.id}
        )


@pytest.mark.item("M12")
@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        ({"version": 0}, "ck_report_version|ck_report_supersedes"),
        ({"version": 2}, "ck_report_supersedes"),
        ({"kind": "external_forward"}, "ck_report_external_document"),
        ({"kind": "summary"}, "ck_report_kind"),
        ({"status": "draft"}, "ck_report_status"),
        ({"sha256": "abc"}, "ck_report_sha256"),
    ],
)
def test_report_db_checks(
    seeded: Session,
    released: tuple[Report, OrderTest, uuid.UUID],
    changes: dict[str, Any],
    constraint: str,
) -> None:
    report, _, user_id = released
    visit = seeded.get_one(Visit, report.visit_id)
    with pytest.raises(IntegrityError, match=constraint), seeded.begin_nested():
        _report(seeded, visit, user_id, **changes)


@pytest.mark.item("M12")
@pytest.mark.item("M21")
@pytest.mark.parametrize(
    ("table", "column"),
    [("report_test", "order_test_id"), ("report_print", "output"), ("report_delivery", "note")],
)
def test_report_tests_prints_and_deliveries_are_append_only(
    seeded: Session, released: tuple[Report, OrderTest, uuid.UUID], table: str, column: str
) -> None:
    for statement in ("update {t} set {c} = {c}", "delete from {t}", "truncate {t}"):
        with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
            seeded.execute(text(statement.format(t=table, c=column)))


@pytest.mark.item("M21")
def test_order_test_events_include_released_and_delivered(
    seeded: Session, released: tuple[Report, OrderTest, uuid.UUID]
) -> None:
    _, ordered, user_id = released
    for event in ("released", "delivered"):
        seeded.add(OrderTestEvent(order_test_id=ordered.id, event=event, by=user_id))
    seeded.flush()
    with pytest.raises(IntegrityError, match="ck_order_test_event_event"), seeded.begin_nested():
        seeded.add(OrderTestEvent(order_test_id=ordered.id, event="emailed", by=user_id))
        seeded.flush()


@pytest.mark.item("M12")
def test_visit_report_mode_is_combined_separate_or_unset(
    seeded: Session, released: tuple[Report, OrderTest, uuid.UUID]
) -> None:
    visit_id = released[0].visit_id
    for mode in ("combined", "separate", None):
        seeded.execute(
            text("update visit set report_mode = :m where id = :id"), {"m": mode, "id": visit_id}
        )
    with pytest.raises(IntegrityError, match="ck_visit_report_mode"), seeded.begin_nested():
        seeded.execute(
            text("update visit set report_mode = 'both' where id = :id"), {"id": visit_id}
        )


def _layout(db: Session, branch_id: uuid.UUID, **changes: Any) -> LetterheadLayout:
    layout = LetterheadLayout(**{"branch_id": branch_id, "doc_kind": "report_a4", **changes})
    db.add(layout)
    db.flush()
    return layout


@pytest.mark.item("M17")
def test_a_draft_letterhead_is_edited_and_a_published_one_is_final(
    seeded: Session, platform: Platform
) -> None:
    b2 = branch(seeded, "B2")
    anil = as_user(seeded, platform, "anil")
    draft = _layout(seeded, b2.id)
    with pytest.raises(IntegrityError, match="uq_letterhead_layout_draft"), seeded.begin_nested():
        _layout(seeded, b2.id)
    _layout(seeded, b2.id, doc_kind="bill_a4")  # one draft per document kind

    params = {"id": draft.id}
    seeded.execute(text("update letterhead_layout set margin_top_mm = 45 where id = :id"), params)
    publish_only = text("update letterhead_layout set status = 'published' where id = :id")
    refused = "ck_letterhead_layout_published"
    with pytest.raises(IntegrityError, match=refused), seeded.begin_nested():
        seeded.execute(publish_only, params)
    seeded.execute(
        text(
            "update letterhead_layout set status = 'published', version = 1,"
            " published_at = now(), published_by = :by where id = :id"
        ),
        params | {"by": anil.user_id},
    )
    for statement in (
        "update letterhead_layout set margin_top_mm = 50 where id = :id",
        "update letterhead_layout set status = 'draft', version = null where id = :id",
        "delete from letterhead_layout where id = :id",
    ):
        with pytest.raises(DBAPIError, match="is published"), seeded.begin_nested():
            seeded.execute(text(statement), params)
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(text("truncate letterhead_layout cascade"))
    # The next draft starts beside the published version.
    assert _layout(seeded, b2.id).status == "draft"


@pytest.mark.item("M17")
@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        ({"margin_top_mm": 121}, "margins"),
        ({"margin_left_mm": -1}, "margins"),
        ({"signature_area_mm": 81}, "signature_area"),
        ({"font_size_pt": 6}, "font_size"),
        ({"doc_kind": "label"}, "doc_kind"),
        ({"apply_on": "last"}, "apply_on"),
        ({"file_type": "svg"}, "file"),
    ],
)
def test_letterhead_db_checks(seeded: Session, changes: dict[str, Any], constraint: str) -> None:
    b2 = branch(seeded, "B2")
    refused = rf"ck_letterhead_layout_{constraint}\b"
    with pytest.raises(IntegrityError, match=refused), seeded.begin_nested():
        _layout(seeded, b2.id, **changes)


@pytest.mark.item("M12")
def test_upgrade_gives_every_branch_a_report_series(seeded: Session) -> None:
    migration = import_module("labra.migrations.versions.0007_reports")
    b2, b3 = (seeded.scalars(select(Branch).where(Branch.code == c)).one() for c in ("B2", "B3"))
    seeded.execute(
        text("delete from number_series where doc_type = 'report' and branch_id = :b"),
        {"b": b3.id},
    )
    kept = seeded.scalars(
        select(NumberSeries).where(
            NumberSeries.branch_id == b2.id, NumberSeries.doc_type == "report"
        )
    ).one()
    kept.format = "{BR}-R-{SEQ:6}"
    seeded.flush()
    for _ in range(2):  # running it again adds nothing
        seeded.execute(text(migration.ADD_REPORT_SERIES))
    seeded.expire_all()
    formats = {
        s.branch_id: s.format
        for s in seeded.scalars(select(NumberSeries).where(NumberSeries.doc_type == "report"))
    }
    assert formats[b2.id] == "{BR}-R-{SEQ:6}"
    assert formats[b3.id] == "{BR}/R/{FY2}/{SEQ:6}"
    assert next_number(seeded, "report", b3.id, "B3", SEED_DAY) == "B3/R/2627/000001"


@pytest.mark.item("M12")
@pytest.mark.item("M21")
@pytest.mark.item("M13")
@pytest.mark.item("M17")
@pytest.mark.parametrize(
    ("permission", "roles"),
    [
        ("report.release", {"signatory"}),
        ("report.view", {"front_desk", "branch_manager", "technician", "signatory", "admin"}),
        ("report.deliver", {"front_desk", "branch_manager", "admin"}),
        ("letterhead.edit", {"admin"}),
        ("owner.reports", {"branch_manager", "admin"}),
    ],
)
def test_report_permissions_by_role(permission: str, roles: set[str]) -> None:
    assert PERMISSIONS[permission].scope == "branch"
    assert {r.code for r in SYSTEM_ROLES.values() if permission in r.permissions} == roles
