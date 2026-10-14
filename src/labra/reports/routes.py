import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core.db import get_session
from labra.core.errors import ValidationFailedError
from labra.core.registry import get_platform
from labra.reports import release, service, verify
from labra.reports.content import PAPERS
from labra.web.documents import pdf_inline
from labra.web.forms import as_uuid
from labra.web.labels import TEST_STATUS_LABELS
from labra.web.templating import page, render

router = APIRouter(prefix="/reports")
public = APIRouter()

MODE_LABELS = {
    "combined": "One report with every test; an outside lab's PDF follows it when no values"
    " were typed from it",
    "separate": "This lab's own report, plus each outside lab's PDF as a report of its own",
}

KIND_LABELS = {
    "combined": "Every test",
    "in_house": "This lab's tests",
    "external_forward": "An outside lab's PDF",
}

DB = Annotated[Session, Depends(get_session)]
Releaser = Annotated[Principal, Depends(require("report.release"))]
Viewer = Annotated[Principal, Depends(require("report.view"))]


@router.get("", response_class=HTMLResponse)
@page("reports/releasing", "reports/queue.html")
def queue(request: Request, db: DB, principal: Viewer) -> Response:
    return render(
        request,
        "reports/queue.html",
        {
            "releasing": bool(principal.branches_with("report.release")),
            "to_release": service.to_release(db, principal),
            "released": service.released(db, principal),
        },
    )


def _visit_page(
    request: Request,
    db: Session,
    principal: Principal,
    visit_id: uuid.UUID,
    errors: dict[str, str] | None = None,
) -> Response:
    return render(
        request,
        "reports/visit.html",
        {
            "planned": service.plan(db, principal, visit_id),
            "modes": MODE_LABELS,
            "kinds": KIND_LABELS,
            "versions": service.versions(db, visit_id),
            "papers": PAPERS,
            "chosen": service.options(db),
            "statuses": TEST_STATUS_LABELS,
            "errors": errors or {},
        },
        status_code=422 if errors else 200,
    )


@router.get("/visits/{visit_id}", response_class=HTMLResponse)
@page("reports/releasing", "reports/visit.html")
def visit_report(request: Request, db: DB, principal: Releaser, visit_id: str) -> Response:
    return _visit_page(request, db, principal, as_uuid(visit_id))


@router.post("/visits/{visit_id}/release")
@page("reports/releasing", "reports/visit.html")
def release_report(
    request: Request,
    db: DB,
    principal: Releaser,
    visit_id: str,
    tests: Annotated[list[str] | None, Form()] = None,
    confirm: Annotated[str, Form()] = "",
) -> Response:
    visit = as_uuid(visit_id)
    expected = {as_uuid(t) for t in tests or []}
    store = get_platform().filestore
    try:
        release.release(db, store, principal, visit, expected, confirm == "yes")
    except ValidationFailedError as exc:
        db.rollback()
        return _visit_page(request, db, principal, visit, exc.errors)
    db.commit()
    return RedirectResponse(f"/reports/visits/{visit}", status_code=303)


@router.post("/visits/{visit_id}/forward/{document_id}")
@page("reports/releasing", "reports/visit.html")
def forward_report(
    request: Request,
    db: DB,
    principal: Releaser,
    visit_id: str,
    document_id: str,
    confirm: Annotated[str, Form()] = "",
) -> Response:
    """Release an outside lab's PDF as a report of its own (separate mode)."""
    visit = as_uuid(visit_id)
    store = get_platform().filestore
    try:
        release.forward(db, store, principal, visit, as_uuid(document_id), confirm == "yes")
    except ValidationFailedError as exc:
        db.rollback()
        return _visit_page(request, db, principal, visit, exc.errors)
    db.commit()
    return RedirectResponse(f"/reports/visits/{visit}", status_code=303)


@router.post("/visits/{visit_id}/mode")
@page("reports/releasing", "reports/visit.html")
def report_mode(
    db: DB, principal: Releaser, visit_id: str, mode: Annotated[str, Form()] = ""
) -> Response:
    """One report with every test, or the outside labs' PDFs as reports of their own."""
    visit = as_uuid(visit_id)
    service.set_mode(db, principal, visit, mode)
    db.commit()
    return RedirectResponse(f"/reports/visits/{visit}", status_code=303)


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


@router.get("/{report_id}/pdf")
@page("reports/releasing", "reports/report.html")
def report_pdf(db: DB, principal: Viewer, report_id: str) -> Response:
    """The stored copy of a released version, exactly as released."""
    store = get_platform().filestore
    report, data = service.report_file(db, store, principal, as_uuid(report_id))
    return pdf_inline(data, f"report-{report.report_no.replace('/', '-')}-v{report.version}")


@public.get("/v/{token}", response_class=HTMLResponse)
@page("reports/releasing", "reports/check.html")
def check_page(request: Request, db: DB, token: str) -> Response:
    """The public check page a report's QR code opens; no sign-in."""
    found = verify.check(db, token)
    response = render(request, "reports/check.html", {"found": found})
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex, nofollow"
    return response
