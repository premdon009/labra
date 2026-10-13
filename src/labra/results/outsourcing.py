"""Tests an outside lab does: what is waiting to go, the sheet that travels with the samples,
marking a test sent, the result PDF that comes back, and each test's timeline.

The sheet for an outside lab carries the patient's name, age and sex. The phone and address
go on it only when that lab is set up to need them.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, exists, literal, or_, select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.catalog.models import Test
from labra.core import audit, outbox
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.files import read_file, save_file
from labra.core.ids import lab_today, utcnow
from labra.core.models import StoredFile
from labra.core.paging import Page, page_of
from labra.core.ports import FileStore
from labra.core.uploads import PDF, check_upload
from labra.extlabs.models import ExternalLab, ExternalLabRate
from labra.org.models import AppUser
from labra.org.service import stale
from labra.patients.age import age_text
from labra.patients.models import Patient
from labra.results.models import ExternalDocument, ExternalDocumentTest, OrderTestEvent
from labra.results.worklist import (
    EDITABLE,
    ROUTABLE,
    RouteChoice,
    can_route,
    choices_for,
    has_document,
)
from labra.visits.models import OrderTest, Sample, Visit

# A test goes out once its sample is in hand.
SENDABLE = ("collected", "in_lab")
MAX_ACCESSION = 40
COULD_GO_LIMIT = 25
TO_SEND_LIMIT = 100
_ACCESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ./_-]*")


def _scope(principal: Principal) -> ColumnElement[bool]:
    """The tests the user has a say in: those of the branches where they may route, and
    those done where they may route or enter results."""
    routes = principal.branches_with("test.route")
    enters = principal.branches_with("result.enter")
    if not routes and not enters:
        raise PermissionDeniedError()
    return or_(Visit.branch_id.in_(routes), OrderTest.perform_branch_id.in_(routes | enters))


# The timeline


@dataclass(frozen=True)
class Step:
    """One thing that happened to a test: what, when, who."""

    event: str
    at: datetime
    by: str
    note: str = ""


def timelines(db: Session, order_test_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Step]]:
    """Each test's steps in the order they happened, from the visit's registration on."""
    if not order_test_ids:
        return {}
    starts = db.execute(
        select(
            OrderTest.id,
            Visit.visited_at,
            Visit.created_by,
            Sample.collected_at,
            Sample.collected_by,
        )
        .join(Visit, Visit.id == OrderTest.visit_id)
        .outerjoin(Sample, Sample.id == OrderTest.sample_id)
        .where(OrderTest.id.in_(order_test_ids))
    ).all()
    events = db.scalars(
        select(OrderTestEvent)
        .where(OrderTestEvent.order_test_id.in_(order_test_ids))
        .order_by(OrderTestEvent.at, OrderTestEvent.id)
    ).all()
    people = {s.created_by for s in starts} | {s.collected_by for s in starts}
    people |= {e.by for e in events}
    names: dict[Any, str] = dict(
        db.execute(
            select(AppUser.id, AppUser.full_name).where(AppUser.id.in_(people - {None}))
        ).all()
    )
    found: dict[uuid.UUID, list[Step]] = {}
    for start in starts:
        steps = [Step("registered", start.visited_at, names.get(start.created_by, ""))]
        if start.collected_at is not None:
            steps.append(Step("collected", start.collected_at, names.get(start.collected_by, "")))
        found[start.id] = steps
    for event in events:
        found[event.order_test_id].append(
            Step(event.event, event.at, names.get(event.by, ""), event.note)
        )
    for steps in found.values():
        steps.sort(key=lambda step: step.at)
    return found


# The outsourcing screen


@dataclass(frozen=True)
class OutItem:
    """One test on the outsourcing screen. No phone, no address."""

    order_test_id: uuid.UUID
    visit_id: uuid.UUID
    visit_no: str
    sample_no: str
    patient_name: str
    age: str
    sex: str
    test_name: str
    status: str
    due_at: datetime
    overdue: bool
    row_version: int
    lab_id: uuid.UUID | None = None
    lab_name: str = ""
    accession_no: str = ""
    cost: Decimal | None = None
    can_route: bool = False
    can_open: bool = False
    choices: list[RouteChoice] = field(default_factory=list)
    timeline: list[Step] = field(default_factory=list)


@dataclass(frozen=True)
class Board:
    """The outsourcing screen: tests routed out and not yet sent, tests with an outside lab,
    and in-house tests an outside lab could do."""

    to_send: list[OutItem]
    sent: Page[OutItem]
    could_go: list[OutItem]
    more_could_go: bool
    # Labs with a test ready to go, for the link to each one's sheet.
    sheets: dict[uuid.UUID, str]


def _listed(principal: Principal) -> Select[*tuple[Any, ...]]:
    return (
        select(
            OrderTest,
            Visit,
            Sample.sample_no,
            Patient.full_name,
            Patient.dob,
            Patient.sex,
            Test.name,
            ExternalLab.name,
        )
        .join(Visit, Visit.id == OrderTest.visit_id)
        .join(Patient, Patient.id == Visit.patient_id)
        .join(Test, Test.id == OrderTest.test_id)
        .outerjoin(Sample, Sample.id == OrderTest.sample_id)
        .outerjoin(ExternalLab, ExternalLab.id == OrderTest.external_lab_id)
        .where(_scope(principal))
    )


def _items(
    db: Session, principal: Principal, rows: list[Any], with_choices: bool = False
) -> list[OutItem]:
    today, now = lab_today(), utcnow()
    steps = timelines(db, [row[0].id for row in rows])
    enters = principal.branches_with("result.enter")
    items = []
    for ordered, visit, sample_no, name, dob, sex, test_name, lab_name in rows:
        may_route = can_route(principal, ordered, visit)
        items.append(
            OutItem(
                order_test_id=ordered.id,
                visit_id=visit.id,
                visit_no=visit.visit_no,
                sample_no=sample_no or "",
                patient_name=name,
                age=age_text(dob, today),
                sex=sex,
                test_name=test_name,
                status=ordered.status,
                due_at=ordered.due_at,
                overdue=ordered.due_at < now,
                row_version=ordered.row_version,
                lab_id=ordered.external_lab_id,
                lab_name=lab_name or "",
                accession_no=ordered.external_accession_no,
                cost=ordered.external_cost if may_route else None,
                can_route=may_route,
                can_open=ordered.perform_branch_id in enters,
                choices=choices_for(db, principal, ordered, visit) if with_choices else [],
                timeline=steps.get(ordered.id, []),
            )
        )
    return items


def board(db: Session, principal: Principal, page: int = 1) -> Board:
    base = _listed(principal)
    to_send = db.execute(
        base.where(OrderTest.route == "external", OrderTest.status.in_(ROUTABLE))
        .order_by(ExternalLab.name, OrderTest.due_at, OrderTest.id)
        .limit(TO_SEND_LIMIT)
    ).all()
    sent = page_of(
        db,
        base.where(OrderTest.status == "sent_out").order_by(OrderTest.due_at, OrderTest.id),
        page,
    )
    could_go: list[Any] = []
    if principal.can("extlab.view"):
        now = utcnow()
        offered = exists().where(
            ExternalLabRate.test_id == OrderTest.test_id,
            ExternalLabRate.valid_from <= now,
            or_(ExternalLabRate.valid_to.is_(None), ExternalLabRate.valid_to > now),
            ExternalLabRate.external_lab_id.in_(
                select(ExternalLab.id).where(ExternalLab.is_active)
            ),
        )
        could_go = list(
            db.execute(
                base.where(OrderTest.route == "in_house", OrderTest.status.in_(ROUTABLE), offered)
                .order_by(OrderTest.due_at, OrderTest.id)
                .limit(COULD_GO_LIMIT + 1)
            ).all()
        )
    waiting = _items(db, principal, list(to_send))
    return Board(
        to_send=waiting,
        sent=Page(_items(db, principal, sent.items), sent.number, sent.size, sent.has_next),
        could_go=[
            item
            for item in _items(db, principal, could_go[:COULD_GO_LIMIT], with_choices=True)
            if item.choices
        ],
        more_could_go=len(could_go) > COULD_GO_LIMIT,
        sheets={
            item.lab_id: item.lab_name
            for item in waiting
            if item.lab_id is not None and item.status in SENDABLE
        },
    )


# The sheet that goes with the samples


@dataclass(frozen=True)
class SheetRow:
    sample_no: str
    container: str
    visit_no: str
    patient_name: str
    age: str
    sex: str
    test_name: str
    their_code: str
    phone: str
    address: str


@dataclass(frozen=True)
class SendSheet:
    lab_name: str
    share_phone: bool
    share_address: bool
    rows: list[SheetRow]


def send_sheet(db: Session, principal: Principal, lab_id: uuid.UUID) -> SendSheet:
    """The tests ready to go to one lab. The phone and the address are read only when the
    lab is set up to be given them."""
    scope = _scope(principal)
    lab = db.get(ExternalLab, lab_id)
    if lab is None:
        raise NotFoundError()
    rows = db.execute(
        select(
            Sample.sample_no,
            Sample.container,
            Visit.visit_no,
            Patient.full_name,
            Patient.dob,
            Patient.sex,
            Test.name,
            ExternalLabRate.their_test_code,
            Patient.phone if lab.share_phone else literal(""),
            Patient.address if lab.share_address else literal(""),
        )
        .select_from(OrderTest)
        .join(Visit, Visit.id == OrderTest.visit_id)
        .join(Patient, Patient.id == Visit.patient_id)
        .join(Test, Test.id == OrderTest.test_id)
        .outerjoin(Sample, Sample.id == OrderTest.sample_id)
        .outerjoin(
            ExternalLabRate,
            (ExternalLabRate.external_lab_id == lab.id)
            & (ExternalLabRate.test_id == OrderTest.test_id)
            & ExternalLabRate.valid_to.is_(None),
        )
        .where(scope, OrderTest.external_lab_id == lab.id, OrderTest.status.in_(SENDABLE))
        .order_by(Visit.visit_no, Test.name, OrderTest.id)
    ).all()
    today = lab_today()
    return SendSheet(
        lab_name=lab.name,
        share_phone=lab.share_phone,
        share_address=lab.share_address,
        rows=[
            SheetRow(
                sample_no=r[0] or "",
                container=r[1] or "",
                visit_no=r[2],
                patient_name=r[3],
                age=age_text(r[4], today),
                sex=r[5],
                test_name=r[6],
                their_code=r[7] or "",
                phone=r[8],
                address=r[9],
            )
            for r in rows
        ],
    )


# Sending


def _accession(raw: str) -> str:
    number = " ".join(raw.split())
    if len(number) > MAX_ACCESSION:
        raise ValidationFailedError({"accession_no": f"Use at most {MAX_ACCESSION} characters."})
    if number and not _ACCESSION.fullmatch(number):
        raise ValidationFailedError(
            {"accession_no": "Use letters, digits, spaces and . / - _ only."}
        )
    return number


def _routed_out(
    db: Session, principal: Principal, order_test_id: uuid.UUID, row_version: int
) -> tuple[OrderTest, Visit, ExternalLab]:
    ordered = db.scalar(select(OrderTest).where(OrderTest.id == order_test_id).with_for_update())
    if ordered is None:
        raise NotFoundError()
    visit = db.get_one(Visit, ordered.visit_id)
    if not can_route(principal, ordered, visit):
        raise PermissionDeniedError()
    if ordered.row_version != row_version:
        raise stale(db, ordered)
    if ordered.external_lab_id is None:
        raise ConflictError("This test isn't going to an outside lab. Reload the page.")
    return ordered, visit, db.get_one(ExternalLab, ordered.external_lab_id)


def mark_sent(
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    row_version: int,
    accession_no: str = "",
    now: datetime | None = None,
) -> OrderTest:
    """Record that a test's sample has left for its outside lab, with the lab's own number
    for it when that is known."""
    ordered, visit, lab = _routed_out(db, principal, order_test_id, row_version)
    if ordered.status == "ordered":
        raise ValidationFailedError(
            {"accession_no": "The sample isn't collected yet. Record the collection first."}
        )
    if ordered.status not in SENDABLE:
        raise ConflictError("This test was already sent, or has a result. Reload the page.")
    number = _accession(accession_no)
    at = now or utcnow()
    ordered.status = "sent_out"
    ordered.external_accession_no = number
    ordered.updated_by = principal.user_id
    db.flush()
    note = f"To {lab.name}" + (f", their number {number}" if number else "")
    db.add(
        OrderTestEvent(
            order_test_id=ordered.id, event="sent", at=at, by=principal.user_id, note=note
        )
    )
    cost = str(ordered.external_cost) if ordered.external_cost is not None else None
    audit.record(
        db,
        "test.send",
        "order_test",
        ordered.id,
        {
            "visit_id": str(visit.id),
            "external_lab_id": str(lab.id),
            "external_cost": cost,
            "accession_no": number,
        },
        user_id=principal.user_id,
        branch_id=visit.branch_id,
    )
    outbox.emit(
        db,
        "test.sent_out",
        {
            "schema_version": 1,
            "entity": "order_test",
            "entity_id": str(ordered.id),
            "visit_id": str(visit.id),
            "test_id": str(ordered.test_id),
            "branch_id": str(visit.branch_id),
            "perform_branch_id": str(ordered.perform_branch_id),
            "external_lab_id": str(lab.id),
            "external_cost": cost,
        },
    )
    return ordered


def set_accession(
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    row_version: int,
    accession_no: str,
) -> OrderTest:
    """Add or correct the outside lab's number for a test that is with it."""
    ordered, visit, lab = _routed_out(db, principal, order_test_id, row_version)
    if ordered.status != "sent_out":
        raise ConflictError("This test isn't with an outside lab now. Reload the page.")
    number = _accession(accession_no)
    if number == ordered.external_accession_no:
        return ordered
    before = ordered.external_accession_no
    ordered.external_accession_no = number
    ordered.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "test.accession",
        "order_test",
        ordered.id,
        {
            "visit_id": str(visit.id),
            "external_lab_id": str(lab.id),
            "from": before,
            "to": number,
        },
        user_id=principal.user_id,
        branch_id=visit.branch_id,
    )
    return ordered


# The result that comes back


@dataclass(frozen=True)
class DocView:
    id: uuid.UUID
    received_at: datetime
    received_by: str
    size: int
    tests: list[str]


@dataclass(frozen=True)
class LabGroup:
    """One outside lab's part in a visit: the tests a result PDF can be attached to, and
    the PDFs already here."""

    lab_id: uuid.UUID
    lab_name: str
    tests: list[tuple[uuid.UUID, str]]
    documents: list[DocView]
    error: str = ""


def _takes_document(db: Session, ordered: OrderTest) -> bool:
    """A test with its outside lab takes its result; one that already has a PDF and isn't
    verified yet can take a corrected one."""
    if ordered.status == "sent_out":
        return True
    return ordered.status in EDITABLE and has_document(db, ordered.id)


def outside_results(db: Session, principal: Principal, visit_id: uuid.UUID) -> list[LabGroup]:
    enters = principal.branches_with("result.enter")
    tests = db.execute(
        select(OrderTest, Test.name, ExternalLab.id, ExternalLab.name)
        .join(Test, Test.id == OrderTest.test_id)
        .join(ExternalLab, ExternalLab.id == OrderTest.external_lab_id)
        .where(
            OrderTest.visit_id == visit_id,
            OrderTest.status != "cancelled",
            OrderTest.perform_branch_id.in_(enters),
        )
        .order_by(ExternalLab.name, Test.name, OrderTest.id)
    ).all()
    names: dict[uuid.UUID, str] = {}
    open_tests: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {}
    for ordered, test_name, lab_id, lab_name in tests:
        names[lab_id] = lab_name
        if _takes_document(db, ordered):
            open_tests.setdefault(lab_id, []).append((ordered.id, test_name))
    mine = {ordered.id for ordered, _, _, _ in tests}
    documents: dict[uuid.UUID, list[DocView]] = {}
    found = db.execute(
        select(ExternalDocument, StoredFile.size, AppUser.full_name)
        .join(StoredFile, StoredFile.id == ExternalDocument.file_id)
        .join(AppUser, AppUser.id == ExternalDocument.received_by)
        .where(ExternalDocument.visit_id == visit_id)
        .order_by(ExternalDocument.received_at, ExternalDocument.id)
    ).all()
    for document, size, by in found:
        linked = db.execute(
            select(ExternalDocumentTest.order_test_id, Test.name)
            .join(OrderTest, OrderTest.id == ExternalDocumentTest.order_test_id)
            .join(Test, Test.id == OrderTest.test_id)
            .where(ExternalDocumentTest.external_document_id == document.id)
            .order_by(Test.name)
        ).all()
        if not any(order_test_id in mine for order_test_id, _ in linked):
            continue
        documents.setdefault(document.external_lab_id, []).append(
            DocView(document.id, document.received_at, by, size, [name for _, name in linked])
        )
    return [
        LabGroup(lab_id, names[lab_id], open_tests.get(lab_id, []), documents.get(lab_id, []))
        for lab_id in names
        if open_tests.get(lab_id) or documents.get(lab_id)
    ]


def attach_result(
    db: Session,
    store: FileStore,
    principal: Principal,
    visit_id: uuid.UUID,
    external_lab_id: uuid.UUID,
    data: bytes,
    order_test_ids: list[uuid.UUID],
    now: datetime | None = None,
) -> ExternalDocument:
    """Attach the PDF an outside lab sent to the tests it is the result of. A test that was
    with the lab is back in the lab from here: its value can be typed, and it can go for
    verification."""
    visit = db.get(Visit, visit_id)
    lab = db.get(ExternalLab, external_lab_id)
    if visit is None or lab is None:
        raise NotFoundError()
    if not order_test_ids:
        raise ValidationFailedError({"tests": "Tick the tests this PDF is the result of."})
    tests = db.scalars(
        select(OrderTest)
        .where(OrderTest.id.in_(order_test_ids), OrderTest.visit_id == visit.id)
        .order_by(OrderTest.id)
        .with_for_update()
    ).all()
    if len(tests) != len(set(order_test_ids)):
        raise NotFoundError()
    for ordered in tests:
        if not principal.can("result.enter", ordered.perform_branch_id):
            raise PermissionDeniedError()
    if any(t.external_lab_id != lab.id or not _takes_document(db, t) for t in tests):
        raise ConflictError(
            "One of these tests isn't with this lab any more, or is already verified."
            " Reload the page."
        )
    mime = check_upload(data, allowed=[PDF])
    digest = hashlib.sha256(data).hexdigest()
    already = db.scalar(
        select(
            exists().where(ExternalDocument.visit_id == visit.id, ExternalDocument.sha256 == digest)
        )
    )
    if already:
        raise ValidationFailedError({"file": "This file is already attached to the visit."})
    at = now or utcnow()
    name = f"external-result-{visit.visit_no}.pdf"
    stored = save_file(db, store, data, name, mime, principal.user_id)
    document = ExternalDocument(
        visit_id=visit.id,
        external_lab_id=lab.id,
        file_id=stored.id,
        sha256=stored.sha256,
        received_at=at,
        received_by=principal.user_id,
    )
    db.add(document)
    db.flush()
    for ordered in tests:
        db.add(ExternalDocumentTest(external_document_id=document.id, order_test_id=ordered.id))
        if ordered.status == "sent_out":
            ordered.status = "in_lab"
            ordered.updated_by = principal.user_id
            db.add(
                OrderTestEvent(
                    order_test_id=ordered.id,
                    event="received_back",
                    at=at,
                    by=principal.user_id,
                    note=f"Result PDF from {lab.name}",
                )
            )
    db.flush()
    audit.record(
        db,
        "result.document",
        "external_document",
        document.id,
        {
            "visit_id": str(visit.id),
            "external_lab_id": str(lab.id),
            "sha256": stored.sha256,
            "tests": [str(t.id) for t in tests],
        },
        user_id=principal.user_id,
        branch_id=visit.branch_id,
    )
    return document


def read_document(
    db: Session, store: FileStore, principal: Principal, document_id: uuid.UUID
) -> tuple[str, bytes]:
    """A result PDF as a download: a name Labra makes up, and the stored bytes."""
    document = db.get(ExternalDocument, document_id)
    if document is None:
        raise NotFoundError()
    visit = db.get_one(Visit, document.visit_id)
    routes = principal.branches_with("test.route")
    allowed = routes | principal.branches_with("result.enter")
    done_at = db.scalars(
        select(OrderTest.perform_branch_id)
        .join(ExternalDocumentTest, ExternalDocumentTest.order_test_id == OrderTest.id)
        .where(ExternalDocumentTest.external_document_id == document.id)
    ).all()
    if visit.branch_id not in routes and not any(branch in allowed for branch in done_at):
        raise PermissionDeniedError()
    _, data = read_file(db, store, document.file_id)
    return f"external-result-{visit.visit_no}-{document.sha256[:8]}.pdf", data
