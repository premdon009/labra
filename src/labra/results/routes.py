import uuid
from dataclasses import replace
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core.currency import load_format
from labra.core.db import get_session
from labra.core.errors import NotFoundError, ValidationFailedError
from labra.core.ids import IST
from labra.results import entry, service, signoff, worklist
from labra.results.models import Result
from labra.web.forms import RowVersion, as_uuid, page_no
from labra.web.labels import CRITICAL_MODE_LABELS, SEX_LABELS, TEST_STATUS_LABELS
from labra.web.templating import page, render

router = APIRouter(prefix="/lab")

DB = Annotated[Session, Depends(get_session)]
Receiver = Annotated[Principal, Depends(require("sample.receive"))]
Enterer = Annotated[Principal, Depends(require("result.enter"))]
Verifier = Annotated[Principal, Depends(require("result.verify"))]
Router = Annotated[Principal, Depends(require("test.route"))]


# Receiving samples


def _receive_page(
    request: Request,
    db: Session,
    principal: Principal,
    sample_no: str = "",
    errors: dict[str, str] | None = None,
    done: str = "",
    status: int = 200,
) -> Response:
    return render(
        request,
        "lab/receive.html",
        {
            "sample_no": sample_no,
            "errors": errors or {},
            "done": service.lab_sample(db, principal, done) if done else None,
            "sexes": SEX_LABELS,
        },
        status_code=status,
    )


@router.get("/receive", response_class=HTMLResponse)
@page("lab/receiving-samples", "lab/receive.html")
def receive(request: Request, db: DB, principal: Receiver, done: str = "") -> Response:
    return _receive_page(request, db, principal, done=done)


@router.post("/receive")
def receive_save(
    request: Request, db: DB, principal: Receiver, sample_no: Annotated[str, Form()] = ""
) -> Response:
    try:
        sample = service.receive_sample(db, principal, sample_no)
    except ValidationFailedError as exc:
        db.rollback()
        return _receive_page(request, db, principal, sample_no, exc.errors, status=422)
    db.commit()
    return RedirectResponse(f"/lab/receive?done={sample.sample_no}", status_code=303)


# The worklist and the result grid


def _uuid_or_none(value: str) -> uuid.UUID | None:
    """A filter picked from a list; anything else is no filter."""
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@router.get("/worklist", response_class=HTMLResponse)
@page("lab/worklist", "lab/worklist.html")
def worklist_page(
    request: Request,
    db: DB,
    principal: Enterer,
    department: str = "",
    status: str = "",
    branch: str = "",
    page: Annotated[str, Query()] = "1",
) -> Response:
    in_view = worklist.branches_in_view(db, principal)
    done_at = _uuid_or_none(branch)
    if done_at not in in_view:
        done_at = principal.branch_id
    return render(
        request,
        "lab/worklist.html",
        {
            "items": worklist.work_page(
                db,
                principal,
                page_no(page),
                department_id=_uuid_or_none(department),
                status=status,
                branch_id=done_at,
            ),
            "departments": worklist.departments(db),
            "department": department,
            "status": status if status in worklist.STATUSES else "",
            "statuses": {code: TEST_STATUS_LABELS[code] for code in worklist.STATUSES},
            "branches": in_view,
            "branch": done_at,
            "sexes": SEX_LABELS,
        },
    )


def _visit_page(
    request: Request,
    db: Session,
    principal: Principal,
    visit_id: uuid.UUID,
    refused: tuple[uuid.UUID, ValidationFailedError] | None = None,
) -> Response:
    """The visit's grid. A step that was refused shows its reason under its test."""
    sheet = worklist.visit_sheet(db, principal, visit_id)
    if refused is not None:
        at, problem = refused
        sheet = replace(
            sheet,
            blocks=[
                replace(b, error=" ".join(problem.errors.values())) if b.order_test_id == at else b
                for b in sheet.blocks
            ],
        )
    return render(
        request,
        "lab/visit.html",
        {
            "sheet": sheet,
            "sexes": SEX_LABELS,
            "statuses": TEST_STATUS_LABELS,
            "modes": CRITICAL_MODE_LABELS,
            "fmt": load_format(db, principal.branch_id),
        },
        status_code=422 if refused else 200,
    )


@router.get("/visits/{visit_id}", response_class=HTMLResponse)
@page("lab/entering-results", "lab/visit.html")
def visit_grid(request: Request, db: DB, principal: Enterer, visit_id: str) -> Response:
    return _visit_page(request, db, principal, as_uuid(visit_id))


def _cell_rows(
    request: Request,
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    parameter_id: uuid.UUID,
    typed: str = "",
    refused: ValidationFailedError | None = None,
    not_logged: ValidationFailedError | None = None,
) -> Response:
    """The saved row, the calculated rows that follow from it and the test's footer, for
    the grid to swap in. A refused value comes back in its box with the reason beside it."""
    block = worklist.test_block(db, principal, worklist.load_sheet(db, order_test_id))
    row = next((r for r in block.rows if r.parameter.id == parameter_id), None)
    if row is not None and refused is not None:
        row = replace(
            row,
            value=typed,
            error=" ".join(refused.errors.values()),
            needs_confirm=isinstance(refused, entry.AbsurdValueError),
        )
    if row is not None and not_logged is not None:
        row = replace(row, inform_error=" ".join(not_logged.errors.values()))
    failed = refused or not_logged
    return render(
        request,
        "lab/_cell_rows.html",
        {
            "row": row,
            "calculated": [] if failed else [r for r in block.rows if r.calculated],
            "block": None if failed else block,
            "statuses": TEST_STATUS_LABELS,
            "modes": CRITICAL_MODE_LABELS,
        },
        status_code=422 if failed else 200,
    )


@router.post("/tests/{order_test_id}/cells/{parameter_id}")
def cell_save(
    request: Request,
    db: DB,
    principal: Enterer,
    order_test_id: str,
    parameter_id: str,
    row_version: RowVersion = 0,
    value: Annotated[str, Form()] = "",
    confirm: Annotated[str, Form()] = "",
) -> Response:
    ordered, parameter = as_uuid(order_test_id), as_uuid(parameter_id)
    try:
        entry.save_value(
            db, principal, ordered, parameter, value, row_version, confirm_absurd=confirm == "1"
        )
    except ValidationFailedError as exc:
        db.rollback()
        return _cell_rows(request, db, principal, ordered, parameter, value.strip(), exc)
    db.commit()
    return _cell_rows(request, db, principal, ordered, parameter)


# Critical values


def _local_time(raw: str) -> datetime | None:
    """The time typed in the browser's date-and-time box, which is India time."""
    try:
        return datetime.fromisoformat(raw.strip()).replace(tzinfo=IST) if raw.strip() else None
    except ValueError:
        raise ValidationFailedError({"informed_at": "Enter the date and time."}) from None


@router.post("/results/{result_id}/critical")
def critical_save(
    request: Request,
    db: DB,
    principal: Enterer,
    result_id: str,
    informed_to: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    informed_at: Annotated[str, Form()] = "",
) -> Response:
    result = db.get(Result, as_uuid(result_id))
    if result is None:
        raise NotFoundError()
    ordered, parameter = result.order_test_id, result.parameter_id
    try:
        signoff.log_critical(
            db,
            principal,
            result.id,
            informed_to=informed_to,
            mode=mode,
            phone=phone,
            informed_at=_local_time(informed_at),
        )
    except ValidationFailedError as exc:
        db.rollback()
        return _cell_rows(request, db, principal, ordered, parameter, not_logged=exc)
    db.commit()
    return _cell_rows(request, db, principal, ordered, parameter)


@router.get("/critical", response_class=HTMLResponse)
@page("lab/critical-values", "lab/critical.html")
def critical_page(
    request: Request, db: DB, principal: Enterer, page: Annotated[str, Query()] = "1"
) -> Response:
    return render(
        request,
        "lab/critical.html",
        {
            "waiting": worklist.critical_waiting(db, principal),
            "log": worklist.critical_log(db, principal, page_no(page)),
            "sexes": SEX_LABELS,
            "modes": CRITICAL_MODE_LABELS,
        },
    )


# Submit, verify, reopen, and where a test is done


def _back(db: Session, order_test_id: uuid.UUID) -> Response:
    visit_id = worklist.load_sheet(db, order_test_id).ordered.visit_id
    return RedirectResponse(f"/lab/visits/{visit_id}#t-{order_test_id}", status_code=303)


def _refused(
    request: Request,
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    problem: ValidationFailedError,
) -> Response:
    db.rollback()
    visit_id = worklist.load_sheet(db, order_test_id).ordered.visit_id
    return _visit_page(request, db, principal, visit_id, (order_test_id, problem))


@router.post("/tests/{order_test_id}/submit")
def submit(
    request: Request, db: DB, principal: Enterer, order_test_id: str, row_version: RowVersion = 0
) -> Response:
    ordered = as_uuid(order_test_id)
    try:
        signoff.submit(db, principal, ordered, row_version)
    except ValidationFailedError as exc:
        return _refused(request, db, principal, ordered, exc)
    db.commit()
    return _back(db, ordered)


@router.post("/tests/{order_test_id}/verify")
def verify(
    request: Request, db: DB, principal: Verifier, order_test_id: str, row_version: RowVersion = 0
) -> Response:
    ordered = as_uuid(order_test_id)
    try:
        signoff.verify(db, principal, ordered, row_version)
    except ValidationFailedError as exc:
        return _refused(request, db, principal, ordered, exc)
    db.commit()
    return _back(db, ordered)


@router.post("/tests/{order_test_id}/reopen")
def reopen(
    request: Request,
    db: DB,
    principal: Verifier,
    order_test_id: str,
    row_version: RowVersion = 0,
    reason: Annotated[str, Form()] = "",
) -> Response:
    ordered = as_uuid(order_test_id)
    try:
        signoff.reopen(db, principal, ordered, row_version, reason)
    except ValidationFailedError as exc:
        return _refused(request, db, principal, ordered, exc)
    db.commit()
    return _back(db, ordered)


@router.post("/tests/{order_test_id}/route")
def route(
    request: Request,
    db: DB,
    principal: Router,
    order_test_id: str,
    row_version: RowVersion = 0,
    to: Annotated[str, Form()] = "",
    reason: Annotated[str, Form()] = "",
) -> Response:
    """`to` is `branch:<id>` for in-house or `lab:<id>` for an outside lab."""
    ordered = as_uuid(order_test_id)
    kind, _, target = to.partition(":")
    try:
        if kind not in ("branch", "lab") or _uuid_or_none(target) is None:
            raise ValidationFailedError({"to": "Pick where the test is done."})
        service.route_test(
            db,
            principal,
            ordered,
            row_version,
            branch_id=_uuid_or_none(target) if kind == "branch" else None,
            external_lab_id=_uuid_or_none(target) if kind == "lab" else None,
            reason=reason,
        )
    except ValidationFailedError as exc:
        return _refused(request, db, principal, ordered, exc)
    db.commit()
    return _back(db, ordered)


@router.post("/visits/{visit_id}/sharing-consent")
def sharing_consent(db: DB, principal: Router, visit_id: str) -> Response:
    visit = as_uuid(visit_id)
    service.record_sharing_consent(db, principal, visit)
    db.commit()
    return RedirectResponse(f"/lab/visits/{visit}", status_code=303)
