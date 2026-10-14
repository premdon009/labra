"""The report screens: what a visit's report would carry if a signatory released it now, the
preview of it, the versions already released, and the queue of reports to release and to
hand over.

A signatory reports the tests performed at a branch where they may release reports, once
those tests are signed off. A visit has one report number; each release is a new version
carrying every test the last version carried and the tests signed off since. The visit's
other tests are listed as pending.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from labra.auth.principal import Principal
from labra.catalog.models import Test
from labra.core.errors import NotFoundError, PermissionDeniedError
from labra.core.files import read_file
from labra.core.ids import lab_today, utcnow
from labra.core.lab_settings import get_value
from labra.core.numbering import upcoming
from labra.core.ports import FileStore
from labra.org.models import AppUser, Branch
from labra.patients.models import Patient
from labra.printing.pdf import Rendered
from labra.printing.service import published, render_report
from labra.reports.content import PAPERS, Options, snapshot, view
from labra.reports.models import Report, ReportDelivery, ReportTest
from labra.results.models import Verification
from labra.results.worklist import SIGNED_OFF, load_sheet
from labra.visits.models import OrderTest, Visit

KIND = "combined"


@dataclass(frozen=True)
class Plan:
    """What a release by this signatory would do now: the number and version it would take,
    the tests it carries over from the last version and the new ones, what stays pending,
    and anything that stops it."""

    visit: Visit
    patient: Patient
    current: Report | None
    report_no: str
    version: int
    carried: list[OrderTest]
    new: list[OrderTest]
    pending: list[OrderTest]
    names: dict[uuid.UUID, str]
    problems: list[str]

    @property
    def tests(self) -> list[OrderTest]:
        return self.carried + self.new


def current(db: Session, visit_id: uuid.UUID) -> Report | None:
    """The visit's report version in force, if one was released."""
    return db.scalar(
        select(Report).where(
            Report.visit_id == visit_id, Report.kind == KIND, Report.status == "released"
        )
    )


def versions(db: Session, visit_id: uuid.UUID) -> list[tuple[Report, str]]:
    """Every version released for the visit with who released it, the newest first."""
    return [
        (report, name)
        for report, name in db.execute(
            select(Report, AppUser.full_name)
            .join(AppUser, AppUser.id == Report.released_by)
            .where(Report.visit_id == visit_id)
            .order_by(Report.report_no, Report.version.desc())
        )
    ]


def _unapproved(db: Session, ordered: OrderTest) -> list[str]:
    """Values read against no range because the range for this patient was not approved
    when the value was saved (design §1d)."""
    sheet = load_sheet(db, ordered.id)
    problems = []
    for parameter in sheet.parameters:
        result = sheet.results.get(parameter.id)
        if result is None or result.value_num is None or result.not_calculable:
            continue
        copied = result.ref_range_text or result.ref_low is not None or result.ref_high is not None
        if not copied and sheet.range_for(parameter.id, approved_only=False) is not None:
            problems.append(
                f"{sheet.test.name}: the reference range for {parameter.name} was not approved"
                " when the value was saved. Approve the range, then reopen the test and save"
                " the value again."
            )
    return problems


def plan(db: Session, principal: Principal, visit_id: uuid.UUID) -> Plan:
    """What a release would carry now. Not found when the visit has no signed-off test this
    signatory may report."""
    if not principal.branches_with("report.release"):
        raise PermissionDeniedError()
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise NotFoundError()
    rows = list(
        db.execute(
            select(OrderTest, Test.name)
            .join(Test, Test.id == OrderTest.test_id)
            .where(OrderTest.visit_id == visit.id, OrderTest.status != "cancelled")
            .order_by(Test.name, OrderTest.id)
        )
    )
    names = {ordered.id: name for ordered, name in rows}
    ours = [
        ordered
        for ordered, _ in rows
        if ordered.status in SIGNED_OFF
        and principal.can("report.release", ordered.perform_branch_id)
    ]
    if not ours:
        raise NotFoundError()
    now = current(db, visit.id)
    on_report = (
        set(db.scalars(select(ReportTest.order_test_id).where(ReportTest.report_id == now.id)))
        if now is not None
        else set()
    )
    # The last version's tests stay on the report, whoever released them.
    carried = [t for t, _ in rows if t.id in on_report and t.status in SIGNED_OFF]
    new = [t for t in ours if t.id not in on_report and t.status == "verified"]
    taken = {t.id for t in carried + new}
    # Not yet signed off, or signed off where this signatory can't release: still to come.
    pending = [t for t, _ in rows if t.id not in taken]
    if now is not None:
        report_no, version = now.report_no, now.version + 1
    else:
        branch = db.get_one(Branch, visit.branch_id)
        report_no, version = upcoming(db, "report", branch.id, branch.code, lab_today()), 1
    return Plan(
        visit=visit,
        patient=db.get_one(Patient, visit.patient_id),
        current=now,
        report_no=report_no,
        version=version,
        carried=carried,
        new=new,
        pending=pending,
        names=names,
        problems=[p for t in new for p in _unapproved(db, t)],
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


def preview_content(db: Session, principal: Principal, planned: Plan) -> dict[str, Any]:
    """What the report would print if this signatory released it now."""
    signatory = db.get_one(AppUser, principal.user_id)
    return snapshot(
        db, planned.visit, planned.tests, planned.pending, signatory, reported_at=utcnow()
    )


def preview(
    db: Session, store: FileStore, principal: Principal, visit_id: uuid.UUID, chosen: Options
) -> Rendered:
    """The report as it would be released now, marked as a preview on every page."""
    planned = plan(db, principal, visit_id)
    content = preview_content(db, principal, planned)
    known = {str(t.id) for t in planned.tests}
    chosen = Options(chosen.paper, chosen.reference, chosen.tests & known)
    return render_report(
        db,
        store,
        planned.visit.branch_id,
        view(content, chosen, preview=True),
        "digital",
        layout=published(db, planned.visit.branch_id, "report_a4"),
        paper=chosen.paper,
    )


QUEUE_LIMIT = 200


@dataclass(frozen=True)
class ToRelease:
    visit_id: uuid.UUID
    visit_no: str
    patient_name: str
    tests: int
    since: datetime


@dataclass(frozen=True)
class Released:
    report_id: uuid.UUID
    report_no: str
    version: int
    is_partial: bool
    visit_no: str
    patient_name: str
    released_at: datetime


def to_release(db: Session, principal: Principal) -> list[ToRelease]:
    """Visits with tests signed off where this signatory releases and not yet on a report,
    the longest waiting first."""
    branches = principal.branches_with("report.release")
    if not branches:
        return []
    since = func.min(Verification.verified_at)
    rows = db.execute(
        select(
            Visit.id, Visit.visit_no, Patient.full_name, func.count(OrderTest.id.distinct()), since
        )
        .join(OrderTest, OrderTest.visit_id == Visit.id)
        .join(Patient, Patient.id == Visit.patient_id)
        .join(Verification, Verification.order_test_id == OrderTest.id)
        .where(OrderTest.status == "verified", OrderTest.perform_branch_id.in_(branches))
        .group_by(Visit.id, Visit.visit_no, Patient.full_name)
        .order_by(since, Visit.visit_no)
        .limit(QUEUE_LIMIT)
    )
    return [ToRelease(*row) for row in rows]


def released(db: Session, principal: Principal) -> list[Released]:
    """Current reports of visits at this user's branches that nobody has handed over yet,
    the newest first."""
    branches = principal.branches_with("report.view")
    if not branches:
        return []
    handed = aliased(Report)
    delivered = (
        select(ReportDelivery.id)
        .join(handed, handed.id == ReportDelivery.report_id)
        .where(handed.report_no == Report.report_no)
        .exists()
    )
    rows = db.execute(
        select(
            Report.id,
            Report.report_no,
            Report.version,
            Report.is_partial,
            Visit.visit_no,
            Patient.full_name,
            Report.released_at,
        )
        .join(Visit, Visit.id == Report.visit_id)
        .join(Patient, Patient.id == Visit.patient_id)
        .where(Report.status == "released", Visit.branch_id.in_(branches), ~delivered)
        .order_by(Report.released_at.desc())
        .limit(QUEUE_LIMIT)
    )
    return [Released(*row) for row in rows]


def report_file(
    db: Session, store: FileStore, principal: Principal, report_id: uuid.UUID
) -> tuple[Report, bytes]:
    """A released version's stored PDF, for a user who may view the reports of the visit's
    branch or of a branch that performed one of its tests."""
    report = db.get(Report, report_id)
    if report is None:
        raise NotFoundError()
    visit = db.get_one(Visit, report.visit_id)
    branches = principal.branches_with("report.view")
    performed = db.scalar(
        select(ReportTest.order_test_id)
        .join(OrderTest, OrderTest.id == ReportTest.order_test_id)
        .where(ReportTest.report_id == report.id, OrderTest.perform_branch_id.in_(branches))
        .limit(1)
    )
    if visit.branch_id not in branches and performed is None:
        raise NotFoundError()
    _, data = read_file(db, store, report.file_id)
    return report, data
