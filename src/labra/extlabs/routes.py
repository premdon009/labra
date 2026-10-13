from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core.currency import load_format
from labra.core.db import get_session
from labra.core.errors import ValidationFailedError
from labra.extlabs import service
from labra.extlabs.models import ExternalLab
from labra.web.forms import RowVersion, as_uuid, day, page_no
from labra.web.templating import page, render

router = APIRouter(prefix="/admin/external-labs")

DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require("extlab.view"))]
Editor = Annotated[Principal, Depends(require("extlab.edit"))]


def _cost_unit(db: Session) -> str:
    symbol = load_format(db, None).symbol
    return f" ({symbol})" if symbol else ""


@router.get("", response_class=HTMLResponse)
@page("admin/external-labs", "extlabs/labs.html")
def labs(request: Request, db: DB, principal: Viewer, page: str = "1") -> Response:
    return render(
        request,
        "extlabs/labs.html",
        {
            "labs": service.lab_page(db, principal, page_no(page)),
            "can_edit": principal.can("extlab.edit"),
        },
    )


def _lab_form(
    request: Request,
    db: Session,
    principal: Principal,
    lab: ExternalLab | None,
    errors: dict[str, str],
    values: dict[str, object] | None = None,
    rate: dict[str, str] | None = None,
    status: int = 200,
) -> Response:
    saved = lab is not None
    return render(
        request,
        "extlabs/lab_form.html",
        {
            "lab": lab,
            "values": values if values is not None else lab,
            "errors": errors,
            "rate": rate or {},
            "rates": service.rates_of_lab(db, principal, lab.id) if saved else [],
            "ended": service.rates_of_lab(db, principal, lab.id, history=True) if saved else [],
            "unit": _cost_unit(db),
            "can_edit": principal.can("extlab.edit"),
        },
        status_code=status,
    )


@router.get("/new", response_class=HTMLResponse)
@page("admin/external-labs", "extlabs/lab_form.html")
def lab_new(request: Request, db: DB, principal: Editor) -> Response:
    return _lab_form(request, db, principal, None, {})


@router.get("/{lab_id}", response_class=HTMLResponse)
@page("admin/external-labs", "extlabs/lab_form.html")
def lab_edit(request: Request, lab_id: str, db: DB, principal: Viewer) -> Response:
    return _lab_form(request, db, principal, service.get_lab(db, principal, as_uuid(lab_id)), {})


@router.post("")
def lab_save(
    request: Request,
    db: DB,
    principal: Editor,
    name: Annotated[str, Form()] = "",
    nabl_cert_no: Annotated[str, Form()] = "",
    contact_name: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    results_email: Annotated[str, Form()] = "",
    portal_url: Annotated[str, Form()] = "",
    dpa_signed_on: Annotated[str, Form()] = "",
    share_phone: Annotated[bool, Form()] = False,
    share_address: Annotated[bool, Form()] = False,
    is_active: Annotated[bool, Form()] = False,
    lab_id: Annotated[str, Form()] = "",
    row_version: RowVersion = 0,
) -> Response:
    data = service.LabInput(
        name,
        nabl_cert_no,
        contact_name,
        phone,
        email,
        results_email,
        portal_url,
        day(dpa_signed_on),
        share_phone,
        share_address,
        is_active or not lab_id,
    )
    lab = service.get_lab(db, principal, as_uuid(lab_id)) if lab_id else None
    try:
        if dpa_signed_on.strip() and data.dpa_signed_on is None:
            raise ValidationFailedError({"dpa_signed_on": "Enter a date."})
        if lab is not None:
            service.update_lab(db, principal, lab.id, data, row_version)
        else:
            lab = service.create_lab(db, principal, data)
    except ValidationFailedError as exc:
        db.rollback()
        typed = {**data.columns(), "dpa_signed_on": dpa_signed_on}
        return _lab_form(request, db, principal, lab, exc.errors, typed, status=422)
    db.commit()
    return RedirectResponse(f"/admin/external-labs/{lab.id}", status_code=303)


@router.post("/{lab_id}/rates")
def rate_save(
    request: Request,
    lab_id: str,
    db: DB,
    principal: Editor,
    test_code: Annotated[str, Form()] = "",
    cost: Annotated[str, Form()] = "",
    tat_hours: Annotated[str, Form()] = "",
    their_test_code: Annotated[str, Form()] = "",
) -> Response:
    lab = service.get_lab(db, principal, as_uuid(lab_id))
    try:
        service.set_rate(db, principal, lab.id, test_code, cost, tat_hours, their_test_code)
    except ValidationFailedError as exc:
        db.rollback()
        typed = {
            "test_code": test_code,
            "cost": cost,
            "tat_hours": tat_hours,
            "their_test_code": their_test_code,
        }
        return _lab_form(request, db, principal, lab, exc.errors, rate=typed, status=422)
    db.commit()
    return RedirectResponse(f"/admin/external-labs/{lab.id}", status_code=303)


@router.post("/{lab_id}/rates/{rate_id}/end")
def rate_end(lab_id: str, rate_id: str, db: DB, principal: Editor) -> Response:
    lab = service.get_lab(db, principal, as_uuid(lab_id))
    service.end_rate(db, principal, lab.id, as_uuid(rate_id))
    db.commit()
    return RedirectResponse(f"/admin/external-labs/{lab.id}", status_code=303)
