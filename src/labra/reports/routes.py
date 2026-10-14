import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core.currency import load_format
from labra.core.db import get_session
from labra.core.errors import ValidationFailedError
from labra.core.lab_settings import get_value
from labra.core.registry import get_platform
from labra.reports import delivery, release, service, verify
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

DELIVERY_LABELS = {
    "counter": "At the counter",
    "home": "Home delivery",
    "email": "By email (recorded only; Labra doesn't send it)",
    "whatsapp": "By WhatsApp (recorded only; Labra doesn't send it)",
}

LOG_LABELS = {
    "digital": "PDF to send",
    "print": "PDF to print",
    "counter": "Handed over at the counter",
    "home": "Home delivery",
    "email": "Sent by email",
    "whatsapp": "Sent by WhatsApp",
}

DB = Annotated[Session, Depends(get_session)]
Releaser = Annotated[Principal, Depends(require("report.release"))]
Viewer = Annotated[Principal, Depends(require("report.view"))]
Deliverer = Annotated[Principal, Depends(require("report.deliver"))]


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
@page("reports/options", "reports/report.html")
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


def _version_page(
    request: Request,
    db: Session,
    principal: Principal,
    report_id: uuid.UUID,
    errors: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
) -> Response:
    s = delivery.screen(db, principal, report_id)
    return render(
        request,
        "reports/version.html",
        {
            "s": s,
            "papers": PAPERS,
            "modes": DELIVERY_LABELS,
            "actions": LOG_LABELS,
            "print_mode": get_value(db, "print.default_mode", s.visit.branch_id),
            "fmt": load_format(db, s.visit.branch_id),
            "me": str(principal.user_id),
            "form": form,
            "errors": errors or {},
        },
        status_code=422 if errors else 200,
    )


@router.get("/{report_id}", response_class=HTMLResponse)
@page("reports/delivery", "reports/version.html")
def version_screen(request: Request, db: DB, principal: Viewer, report_id: str) -> Response:
    return _version_page(request, db, principal, as_uuid(report_id))


@router.get("/{report_id}/pdf")
@page("reports/print-vs-digital", "reports/report.html")
def report_pdf(
    request: Request,
    db: DB,
    principal: Viewer,
    report_id: str,
    output: str = "digital",
    paper: str = "",
    reference: str = "",
    tests: Annotated[list[str] | None, Query()] = None,
    dues: str = "",
) -> Response:
    """A copy of a released version: the stored PDF when it is the full digital one, else
    made again from what was released. Logged."""
    report = as_uuid(report_id)
    store = get_platform().filestore
    try:
        found, data = delivery.make_copy(
            db,
            store,
            principal,
            report,
            output,
            dues == "yes",
            paper=paper,
            reference=reference,
            tests=[t for t in tests or [] if t],
        )
    except ValidationFailedError as exc:
        db.rollback()
        return _version_page(request, db, principal, report, exc.errors)
    db.commit()
    name = f"report-{found.report_no.replace('/', '-')}-v{found.version}"
    return pdf_inline(data, name if output == "digital" else f"{name}-print")


@router.post("/{report_id}/deliver")
@page("reports/delivery", "reports/version.html")
def deliver_report(
    request: Request,
    db: DB,
    principal: Deliverer,
    report_id: str,
    delivered_to: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "",
    staff_id: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    dues: Annotated[str, Form()] = "",
) -> Response:
    report = as_uuid(report_id)
    try:
        staff = uuid.UUID(staff_id)
    except ValueError:
        staff = None
    data = delivery.DeliveryInput(delivered_to, mode, staff, note)
    try:
        delivery.deliver(db, principal, report, data, dues == "yes")
    except ValidationFailedError as exc:
        db.rollback()
        form = {"delivered_to": delivered_to, "mode": mode, "staff_id": staff_id, "note": note}
        return _version_page(request, db, principal, report, exc.errors, form)
    db.commit()
    return RedirectResponse(f"/reports/{report}", status_code=303)


@public.get("/v/{token}", response_class=HTMLResponse)
@page("reports/releasing", "reports/check.html")
def check_page(request: Request, db: DB, token: str) -> Response:
    """The public check page a report's QR code opens; no sign-in."""
    found = verify.check(db, token)
    response = render(request, "reports/check.html", {"found": found})
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex, nofollow"
    return response
