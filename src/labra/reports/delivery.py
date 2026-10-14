"""Copies of a released report and handing it over (design §7, M20, M21).

A copy is the stored PDF when it is the full digital one, else made again from the frozen
content on the letterhead the report was released with, so every copy matches the stored
one. Each copy and each hand-over is logged, with what was still due on the bill then; a
due warns and needs a tick, it never stops the copy.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.billing.models import Bill
from labra.core import audit
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.files import read_file
from labra.core.ids import utcnow
from labra.core.ports import FileStore
from labra.org.models import AppUser, UserBranchRole
from labra.patients.models import Patient
from labra.printing.models import LetterheadLayout
from labra.printing.service import render_report
from labra.reports.content import PAPERS, Options, stored_options, view
from labra.reports.models import (
    DELIVERY_MODES,
    PRINT_OUTPUTS,
    Report,
    ReportDelivery,
    ReportPrint,
    ReportTest,
)
from labra.reports.service import viewable
from labra.results.models import OrderTestEvent
from labra.visits.models import Visit

DUES = "Money is still due on the bill. Tick the box to go ahead anyway."
NOT_CURRENT = "A newer version of this report has been released. Hand over that one instead."
MAX_TO = 120
MAX_NOTE = 300


@dataclass(frozen=True)
class DeliveryInput:
    delivered_to: str
    mode: str
    staff_id: uuid.UUID | None
    note: str = ""


@dataclass(frozen=True)
class LogLine:
    """One copy made or one hand-over, for the report's log."""

    at: datetime
    version: int
    what: str
    by: str
    detail: str
    due: Decimal


@dataclass(frozen=True)
class Screen:
    report: Report
    visit: Visit
    patient: Patient
    current: Report
    tests: list[tuple[str, str]]
    stored: Options
    due: Decimal
    can_deliver: bool
    staff: list[AppUser]
    log: list[LogLine]


def due_on(db: Session, visit_id: uuid.UUID) -> Decimal:
    """What is still to be paid on the visit's bill; nothing without a bill."""
    due = db.scalar(select(Bill.due).where(Bill.visit_id == visit_id, Bill.status != "cancelled"))
    return due if due is not None else Decimal(0)


def staff(db: Session, branch_id: uuid.UUID) -> list[AppUser]:
    """Who may be named as handing a report over: active staff with a role at the branch,
    whether or not they sign in themselves."""
    return list(
        db.scalars(
            select(AppUser)
            .where(
                AppUser.is_active,
                AppUser.id.in_(
                    select(UserBranchRole.user_id).where(UserBranchRole.branch_id == branch_id)
                ),
            )
            .order_by(AppUser.full_name)
        )
    )


def _versions(db: Session, report: Report) -> dict[uuid.UUID, int]:
    return dict(
        db.execute(
            select(Report.id, Report.version).where(Report.report_no == report.report_no)
        ).all()
    )


def _log(db: Session, report: Report) -> list[LogLine]:
    """Every copy and hand-over of any version of the report's number, the newest first."""
    versions = _versions(db, report)
    deliveries = list(
        db.scalars(select(ReportDelivery).where(ReportDelivery.report_id.in_(versions)))
    )
    prints = list(db.scalars(select(ReportPrint).where(ReportPrint.report_id.in_(versions))))
    people = {d.staff_id or d.delivered_by for d in deliveries} | {p.printed_by for p in prints}
    names = dict(
        db.execute(select(AppUser.id, AppUser.full_name).where(AppUser.id.in_(people))).all()
    )
    lines = [
        LogLine(
            d.delivered_at,
            versions[d.report_id],
            d.mode,
            names.get(d.staff_id or d.delivered_by, ""),
            d.delivered_to,
            d.dues_at_delivery,
        )
        for d in deliveries
    ]
    lines += [
        LogLine(
            p.printed_at,
            versions[p.report_id],
            p.output,
            names.get(p.printed_by, ""),
            f"{len(p.order_test_ids)} tests" if p.order_test_ids else "",
            p.dues_at_print,
        )
        for p in prints
    ]
    return sorted(lines, key=lambda line: line.at, reverse=True)


def screen(db: Session, principal: Principal, report_id: uuid.UUID) -> Screen:
    """What the report's own screen shows: the version, its tests, the due, the log."""
    report, visit = viewable(db, principal, report_id)
    current = db.scalar(
        select(Report).where(Report.report_no == report.report_no, Report.status == "released")
    )
    return Screen(
        report=report,
        visit=visit,
        patient=db.get_one(Patient, visit.patient_id),
        current=current or report,
        tests=[(p["order_test_id"], p["name"]) for p in report.content["panels"]],
        stored=stored_options(report.content),
        due=due_on(db, visit.id),
        can_deliver=principal.can("report.deliver", visit.branch_id),
        staff=staff(db, visit.branch_id),
        log=_log(db, report),
    )


def make_copy(
    db: Session,
    store: FileStore,
    principal: Principal,
    report_id: uuid.UUID,
    output: str,
    dues_ok: bool,
    *,
    paper: str = "",
    reference: str = "",
    tests: Sequence[str] = (),
) -> tuple[Report, bytes]:
    """A copy of a released version to download or print, logged. What isn't chosen is as
    on the stored copy; no test chosen, or every test, means the whole report."""
    report, visit = viewable(db, principal, report_id)
    if output not in PRINT_OUTPUTS:
        raise NotFoundError()
    stored = stored_options(report.content)
    known = {p["order_test_id"] for p in report.content["panels"]}
    picked = frozenset(tests) & known
    chosen = Options(
        paper if paper in PAPERS else stored.paper,
        reference == "1" if reference in ("0", "1") else stored.reference,
        frozenset() if picked == known else picked,
    )
    due = due_on(db, visit.id)
    if due > 0 and not dues_ok:
        raise ValidationFailedError({"dues": DUES})
    if output == "digital" and chosen == stored:
        _, data = read_file(db, store, report.file_id)
    else:
        layout = (
            db.get(LetterheadLayout, report.letterhead_layout_id)
            if report.letterhead_layout_id is not None
            else None
        )
        data = render_report(
            db,
            store,
            visit.branch_id,
            view(report.content, chosen),
            output,
            layout=layout,
            paper=chosen.paper,
        ).pdf
    db.add(
        ReportPrint(
            report_id=report.id,
            output=output,
            order_test_ids=sorted(chosen.tests),
            options={"paper": chosen.paper, "reference": chosen.reference},
            dues_at_print=due,
            printed_by=principal.user_id,
        )
    )
    db.flush()
    return report, data


def deliver(
    db: Session,
    principal: Principal,
    report_id: uuid.UUID,
    data: DeliveryInput,
    dues_ok: bool,
    at: datetime | None = None,
) -> ReportDelivery:
    """Record the report as handed over or sent. Only the version in force is handed over."""
    report, visit = viewable(db, principal, report_id)
    if not principal.can("report.deliver", visit.branch_id):
        raise PermissionDeniedError()
    if report.status != "released":
        raise ConflictError(NOT_CURRENT)
    errors: dict[str, str] = {}
    delivered_to = " ".join(data.delivered_to.split())
    note = data.note.strip()
    if not delivered_to:
        errors["delivered_to"] = "Say who received the report."
    elif len(delivered_to) > MAX_TO:
        errors["delivered_to"] = f"Use at most {MAX_TO} characters."
    if data.mode not in DELIVERY_MODES:
        errors["mode"] = "Choose how the report was handed over."
    if data.staff_id not in {user.id for user in staff(db, visit.branch_id)}:
        errors["staff_id"] = "Choose who handed it over."
    if len(note) > MAX_NOTE:
        errors["note"] = f"Use at most {MAX_NOTE} characters."
    due = due_on(db, visit.id)
    if due > 0 and not dues_ok:
        errors["dues"] = DUES
    if errors:
        raise ValidationFailedError(errors)
    when = at or utcnow()
    delivery = ReportDelivery(
        report_id=report.id,
        delivered_to=delivered_to,
        mode=data.mode,
        staff_id=data.staff_id,
        delivered_by=principal.user_id,
        delivered_at=when,
        note=note,
        dues_at_delivery=due,
    )
    db.add(delivery)
    for order_test_id in db.scalars(
        select(ReportTest.order_test_id).where(ReportTest.report_id == report.id)
    ):
        db.add(
            OrderTestEvent(
                order_test_id=order_test_id,
                event="delivered",
                at=when,
                by=principal.user_id,
                note=f"Report {report.report_no} v{report.version}",
            )
        )
    db.flush()
    # No names: who received it is on the delivery row only.
    audit.record(
        db,
        "report.deliver",
        "report",
        report.id,
        {"visit_id": str(visit.id), "version": report.version, "mode": data.mode, "due": str(due)},
        user_id=principal.user_id,
        branch_id=visit.branch_id,
    )
    return delivery
