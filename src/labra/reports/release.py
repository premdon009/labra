"""Releasing a report (design §7): the signatory's confirmation, then in one transaction the
number, the PDF, the stored copy, the report rows, the tests marked released, their events,
the audit row and the `report.released` event.

A visit has one report number. Each release is a new version of it carrying every test the
last version carried and the tests signed off since; the last version is then superseded.
A version that carries a corrected result is marked amended, with the reason. In separate
mode each outside lab's PDF is released on its own (`forward`) in the same way.
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.catalog.models import Test
from labra.core import audit, outbox
from labra.core.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from labra.core.files import save_file
from labra.core.ids import lab_today, utcnow
from labra.core.lab_settings import get_value
from labra.core.numbering import next_number
from labra.core.ports import FileStore
from labra.org.models import AppUser, Branch
from labra.printing.service import published, render_report
from labra.reports.content import snapshot, view
from labra.reports.models import Report, ReportTest
from labra.reports.service import Plan, amendment, options, plan
from labra.results.models import ExternalDocument, OrderTestEvent
from labra.visits.models import OrderTest, Visit

NOTHING_NEW = "No signed-off test is waiting to be reported. Reload the page."
CONFIRM = "Tick the box to confirm the release."
CHANGED = "The tests waiting to be reported have changed. Check the list again."
MAX_AMENDMENT = 300


def _qr_text(db: Session, report_no: str, version: int, token: str, content: dict) -> str:
    """A link to the public check page; without a web address for it, the report's number
    and a fingerprint of what it prints."""
    base = get_value(db, "report.verify_base_url")
    if base:
        return f"{base}/v/{token}"
    digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    return f"Report {report_no} v{version} {digest[:16]}"


def _planned(db: Session, principal: Principal, visit_id: uuid.UUID) -> Plan:
    if not principal.branches_with("report.release"):
        raise PermissionDeniedError()
    # One release of a visit at a time: the second waits here, then sees the first's version.
    db.scalar(select(Visit).where(Visit.id == visit_id).with_for_update())
    return plan(db, principal, visit_id)


def release(
    db: Session,
    store: FileStore,
    principal: Principal,
    visit_id: uuid.UUID,
    expected: set[uuid.UUID],
    confirm: bool,
    at: datetime | None = None,
) -> Report:
    """Release the visit's newly signed-off tests as the next version of its report.
    `expected` is the set of new tests the signatory confirmed; a change refuses."""
    planned = _planned(db, principal, visit_id)
    if not planned.new:
        raise ConflictError(NOTHING_NEW)
    if {t.id for t in planned.new} != expected:
        raise ConflictError(CHANGED)
    if planned.problems:
        raise ValidationFailedError({"release": " ".join(planned.problems)})
    if not confirm:
        raise ValidationFailedError({"confirm": CONFIRM})
    return _issue(
        db,
        store,
        principal,
        planned,
        kind=planned.kind,
        document=None,
        previous=planned.current,
        tests=planned.tests,
        new=planned.new,
        pending=planned.pending,
        amended=planned.amended,
        at=at or utcnow(),
    )


def forward(
    db: Session,
    store: FileStore,
    principal: Principal,
    visit_id: uuid.UUID,
    document_id: uuid.UUID,
    confirm: bool,
    at: datetime | None = None,
) -> Report:
    """Release an outside lab's PDF as a report of its own, behind a cover page (separate
    mode), once every test on it is signed off."""
    planned = _planned(db, principal, visit_id)
    chosen = next((f for f in planned.forwards if f.document.id == document_id), None)
    if chosen is None or not chosen.ready:
        raise ConflictError(NOTHING_NEW)
    if not confirm:
        raise ValidationFailedError({f"forward:{document_id}": CONFIRM})
    return _issue(
        db,
        store,
        principal,
        planned,
        kind="external_forward",
        document=chosen.document,
        previous=chosen.current,
        tests=chosen.tests,
        new=chosen.new,
        pending=[],
        amended=chosen.amended,
        at=at or utcnow(),
    )


def _issue(
    db: Session,
    store: FileStore,
    principal: Principal,
    planned: Plan,
    *,
    kind: str,
    document: ExternalDocument | None,
    previous: Report | None,
    tests: list[OrderTest],
    new: list[OrderTest],
    pending: list[OrderTest],
    amended: list[OrderTest],
    at: datetime,
) -> Report:
    """Number, render, store and record one report version, and mark its new tests
    released."""
    visit = planned.visit
    branch = db.get_one(Branch, visit.branch_id)
    if previous is None:
        report_no = next_number(db, "report", branch.id, branch.code, lab_today())
        version = 1
    else:
        report_no, version = previous.report_no, previous.version + 1
    # The mode in force when the first report went out stays, whatever the setting says later.
    if visit.report_mode is None:
        visit.report_mode = planned.mode
        visit.updated_by = principal.user_id
    signatory = db.get_one(AppUser, principal.user_id)
    corrected = amendment(previous, amended, planned.names, planned.reasons)
    if document is not None and corrected is not None:
        corrected["lines"] = [planned.names[t.id] for t in amended]
    content: dict[str, Any] = snapshot(
        db,
        visit,
        tests,
        pending,
        signatory,
        reported_at=at,
        report_no=report_no,
        version=version,
        forward=document,
        separately=planned.separately if document is None else (),
        amended=corrected,
    )
    # The stored copy follows the lab's settings, recorded so a copy made later matches it.
    chosen = options(db)
    content["stored"] = {"paper": chosen.paper, "reference": chosen.reference}
    token = secrets.token_urlsafe(16)
    content["qr"] = _qr_text(db, report_no, version, token, content)
    layout = published(db, branch.id, "report_a4")
    rendered = render_report(db, store, branch.id, view(content, chosen), "digital", layout=layout)
    stored = save_file(
        db,
        store,
        rendered.pdf,
        f"report-{report_no.replace('/', '-')}-v{version}.pdf",
        "application/pdf",
        principal.user_id,
    )
    if previous is not None:
        previous.status = "superseded"
        db.flush()
    reason = "; ".join(corrected["lines"]) if corrected is not None else ""
    if len(reason) > MAX_AMENDMENT:
        reason = reason[: MAX_AMENDMENT - 1] + "…"
    report = Report(
        report_no=report_no,
        version=version,
        visit_id=visit.id,
        kind=kind,
        external_document_id=document.id if document is not None else None,
        is_partial=bool(pending),
        amendment_reason=reason,
        supersedes_report_id=previous.id if previous is not None else None,
        released_by=principal.user_id,
        released_at=at,
        file_id=stored.id,
        sha256=hashlib.sha256(rendered.pdf).hexdigest(),
        content=content,
        letterhead_layout_id=layout.id if layout is not None else None,
        verify_token=token,
    )
    db.add(report)
    db.flush()
    db.add_all(ReportTest(report_id=report.id, order_test_id=t.id) for t in tests)
    codes = dict(
        db.execute(select(Test.id, Test.code).where(Test.id.in_([t.test_id for t in new]))).all()
    )
    for ordered in new:
        ordered.status = "released"
        ordered.updated_by = principal.user_id
        db.add(
            OrderTestEvent(
                order_test_id=ordered.id,
                event="released",
                at=at,
                by=principal.user_id,
                note=f"Report {report_no} v{version}",
            )
        )
    db.flush()
    # Test codes and counts only: the reopening reasons are in each test's own audit row.
    audit.record(
        db,
        "report.release",
        "report",
        report.id,
        {
            "visit_id": str(visit.id),
            "kind": kind,
            "version": version,
            "tests": sorted(codes[t.test_id] for t in new),
            "amended": sorted(codes[t.test_id] for t in amended),
            "carried": len(tests) - len(new),
            "partial": report.is_partial,
        },
        user_id=principal.user_id,
        branch_id=visit.branch_id,
    )
    # IDs only: no name, no value, no reason, no check-page token.
    outbox.emit(
        db,
        "report.released",
        {
            "schema_version": 1,
            "entity": "report",
            "entity_id": str(report.id),
            "visit_id": str(visit.id),
            "branch_id": str(visit.branch_id),
            "kind": kind,
            "version": version,
            "supersedes_report_id": str(previous.id) if previous is not None else None,
            "order_test_ids": sorted(str(t.id) for t in tests),
            "is_partial": report.is_partial,
            "is_amended": corrected is not None,
        },
    )
    return report
