import uuid
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core.db import get_session
from labra.core.errors import ValidationFailedError
from labra.results import entry, service, worklist
from labra.web.forms import RowVersion, as_uuid, page_no
from labra.web.labels import SEX_LABELS, TEST_STATUS_LABELS
from labra.web.templating import page, render

router = APIRouter(prefix="/lab")

DB = Annotated[Session, Depends(get_session)]
Receiver = Annotated[Principal, Depends(require("sample.receive"))]
Enterer = Annotated[Principal, Depends(require("result.enter"))]


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


@router.get("/visits/{visit_id}", response_class=HTMLResponse)
@page("lab/entering-results", "lab/visit.html")
def visit_grid(request: Request, db: DB, principal: Enterer, visit_id: str) -> Response:
    return render(
        request,
        "lab/visit.html",
        {
            "sheet": worklist.visit_sheet(db, principal, as_uuid(visit_id)),
            "sexes": SEX_LABELS,
            "statuses": TEST_STATUS_LABELS,
        },
    )


def _cell_rows(
    request: Request,
    db: Session,
    principal: Principal,
    order_test_id: uuid.UUID,
    parameter_id: uuid.UUID,
    typed: str = "",
    refused: ValidationFailedError | None = None,
) -> Response:
    """The saved row, and the calculated rows that follow from it, for the grid to swap in.
    A refused value comes back in its box with the reason beside it."""
    sheet = worklist.load_sheet(db, order_test_id)
    can_type = sheet.ordered.status in entry.EDITABLE and principal.can(
        "result.enter", sheet.ordered.perform_branch_id
    )
    rows = worklist.rows(db, sheet, can_type)
    row = next((r for r in rows if r.parameter.id == parameter_id), None)
    if row is not None and refused is not None:
        row = replace(
            row,
            value=typed,
            error=" ".join(refused.errors.values()),
            needs_confirm=isinstance(refused, entry.AbsurdValueError),
        )
    return render(
        request,
        "lab/_cell_rows.html",
        {
            "row": row,
            "calculated": [] if refused else [r for r in rows if r.calculated],
        },
        status_code=422 if refused else 200,
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
