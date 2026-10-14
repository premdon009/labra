import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.billing import service as billing
from labra.core.currency import load_format
from labra.core.db import get_session
from labra.core.ids import lab_today
from labra.org.models import Branch
from labra.owner import service
from labra.web.forms import as_uuid, day, page_no
from labra.web.labels import MODE_LABELS, TEST_STATUS_LABELS
from labra.web.templating import page, render

router = APIRouter(prefix="/owner")

DB = Annotated[Session, Depends(get_session)]
Owner = Annotated[Principal, Depends(require(service.PERMISSION))]


def _branch(raw: str) -> uuid.UUID | None:
    return as_uuid(raw) if raw else None


def _common(db: Session, principal: Principal, branch_id: uuid.UUID | None) -> dict[str, object]:
    return {
        "branches": service.branch_choices(db, principal),
        "branch": str(branch_id) if branch_id else "",
        "fmt": load_format(db, branch_id),
    }


@router.get("/daily", response_class=HTMLResponse)
@page("owner/daily-collection", "owner/daily.html")
def daily(request: Request, db: DB, principal: Owner, date: str = "", branch: str = "") -> Response:
    branch_id = _branch(branch)
    chosen = day(date) or lab_today()
    figures = service.daily(db, principal, chosen, branch_id)
    return render(
        request,
        "owner/daily.html",
        {
            **_common(db, principal, branch_id),
            "d": figures,
            "day": chosen.isoformat(),
            "modes": MODE_LABELS,
        },
    )


@router.get("/dues", response_class=HTMLResponse)
@page("owner/dues-pending-outsourcing", "owner/dues.html")
def dues(request: Request, db: DB, principal: Owner, page: str = "1") -> Response:
    bills = billing.dues_page(db, principal, page_no(page), permission=service.PERMISSION)
    names = dict(
        db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_({b.branch_id for b in bills.items}))
        ).all()
    )
    return render(
        request,
        "owner/dues.html",
        {**_common(db, principal, None), "bills": bills, "names": names},
    )


@router.get("/pending", response_class=HTMLResponse)
@page("owner/dues-pending-outsourcing", "owner/pending.html")
def pending(
    request: Request, db: DB, principal: Owner, branch: str = "", page: str = "1"
) -> Response:
    branch_id = _branch(branch)
    return render(
        request,
        "owner/pending.html",
        {
            **_common(db, principal, branch_id),
            "tests": service.pending(db, principal, page_no(page), branch_id),
            "statuses": TEST_STATUS_LABELS,
        },
    )


@router.get("/outsourcing", response_class=HTMLResponse)
@page("owner/dues-pending-outsourcing", "owner/outsourcing.html")
def outsourcing(
    request: Request,
    db: DB,
    principal: Owner,
    start: Annotated[str, Query(alias="from")] = "",
    end: Annotated[str, Query(alias="to")] = "",
    branch: str = "",
) -> Response:
    branch_id = _branch(branch)
    today = lab_today()
    first = day(start) or today.replace(day=1)
    last = day(end) or today
    if first > last:
        first, last = last, first
    lines, total = service.outsourcing(db, principal, first, last, branch_id)
    return render(
        request,
        "owner/outsourcing.html",
        {
            **_common(db, principal, branch_id),
            "lines": lines,
            "total": total,
            "start": first.isoformat(),
            "end": last.isoformat(),
        },
    )
