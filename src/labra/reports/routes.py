from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core.db import get_session
from labra.core.registry import get_platform
from labra.reports import service
from labra.reports.content import PAPERS
from labra.web.documents import pdf_inline
from labra.web.forms import as_uuid
from labra.web.labels import TEST_STATUS_LABELS
from labra.web.templating import page, render

router = APIRouter(prefix="/reports")

DB = Annotated[Session, Depends(get_session)]
Releaser = Annotated[Principal, Depends(require("report.release"))]


@router.get("/visits/{visit_id}", response_class=HTMLResponse)
@page("reports/releasing", "reports/visit.html")
def visit_report(request: Request, db: DB, principal: Releaser, visit_id: str) -> Response:
    found = service.reportable(db, principal, as_uuid(visit_id))
    return render(
        request,
        "reports/visit.html",
        {
            "found": found,
            "papers": PAPERS,
            "chosen": service.options(db),
            "statuses": TEST_STATUS_LABELS,
        },
    )


@router.get("/visits/{visit_id}/preview")
@page("reports/releasing", "reports/report.html")
def visit_preview(
    db: DB,
    principal: Releaser,
    visit_id: str,
    paper: str = "",
    reference: str = "",
    tests: Annotated[list[str] | None, Query()] = None,
) -> Response:
    """The report as it would be released now, as a PDF marked "Preview"."""
    visit = as_uuid(visit_id)
    chosen = service.options(db, paper, reference, tests)
    rendered = service.preview(db, get_platform().filestore, principal, visit, chosen)
    return pdf_inline(rendered.pdf, "report-preview")
