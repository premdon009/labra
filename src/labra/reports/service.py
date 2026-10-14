"""The report screen for a signatory: which of a visit's tests a report would carry, and the
preview of it before anything is released.

A signatory reports the tests performed at a branch where they may release reports, once
those tests are signed off. The visit's other tests that are not yet signed off are listed
as pending.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.catalog.models import Test
from labra.core.errors import NotFoundError, PermissionDeniedError
from labra.core.ids import utcnow
from labra.core.lab_settings import get_value
from labra.core.ports import FileStore
from labra.org.models import AppUser
from labra.patients.models import Patient
from labra.printing.pdf import Rendered
from labra.printing.service import published, render_report
from labra.reports.content import PAPERS, Options, snapshot, view
from labra.results.worklist import SIGNED_OFF
from labra.visits.models import OrderTest, Visit


@dataclass(frozen=True)
class Line:
    order_test_id: uuid.UUID
    name: str
    status: str


@dataclass(frozen=True)
class Reportable:
    """A visit as the report screen shows it: what a report would carry, and what waits."""

    visit: Visit
    patient: Patient
    tests: list[OrderTest]
    pending: list[OrderTest]
    lines: list[Line]
    waiting: list[Line]


def reportable(db: Session, principal: Principal, visit_id: uuid.UUID) -> Reportable:
    """The visit's signed-off tests this signatory may report, and the ones still pending.
    Not found when there is nothing for them to report."""
    if not principal.branches_with("report.release"):
        raise PermissionDeniedError()
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise NotFoundError()
    found = db.execute(
        select(OrderTest, Test.name)
        .join(Test, Test.id == OrderTest.test_id)
        .where(OrderTest.visit_id == visit.id, OrderTest.status != "cancelled")
        .order_by(Test.name, OrderTest.id)
    )
    tests: list[tuple[OrderTest, str]] = []
    pending: list[tuple[OrderTest, str]] = []
    for ordered, name in found:
        if ordered.status not in SIGNED_OFF:
            pending.append((ordered, name))
        elif principal.can("report.release", ordered.perform_branch_id):
            tests.append((ordered, name))
    if not tests:
        raise NotFoundError()
    return Reportable(
        visit=visit,
        patient=db.get_one(Patient, visit.patient_id),
        tests=[t for t, _ in tests],
        pending=[t for t, _ in pending],
        lines=[Line(t.id, name, t.status) for t, name in tests],
        waiting=[Line(t.id, name, t.status) for t, name in pending],
    )


def options(
    db: Session, paper: str = "", reference: str = "", tests: list[str] | None = None
) -> Options:
    """The output choices from a form; the lab's settings where nothing was chosen."""
    setting = get_value(db, "report.reference_column")
    shown = reference == "1" if reference else setting == "show"
    return Options(
        paper=paper if paper in PAPERS else PAPERS[0],
        reference=shown,
        tests=frozenset(t for t in tests or [] if t),
    )


def preview_content(db: Session, principal: Principal, found: Reportable) -> dict[str, Any]:
    """What the report would print if this signatory released it now."""
    signatory = db.get_one(AppUser, principal.user_id)
    return snapshot(db, found.visit, found.tests, found.pending, signatory, reported_at=utcnow())


def preview(
    db: Session, store: FileStore, principal: Principal, visit_id: uuid.UUID, chosen: Options
) -> Rendered:
    """The report as it would be released now, marked as a preview on every page."""
    found = reportable(db, principal, visit_id)
    content = preview_content(db, principal, found)
    known = {str(t.id) for t in found.tests}
    chosen = Options(chosen.paper, chosen.reference, chosen.tests & known)
    return render_report(
        db,
        store,
        found.visit.branch_id,
        view(content, chosen, preview=True),
        "digital",
        layout=published(db, found.visit.branch_id, "report_a4"),
        paper=chosen.paper,
    )
