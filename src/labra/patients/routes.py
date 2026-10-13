import uuid
from datetime import date
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core.db import get_session
from labra.core.errors import NotFoundError, ValidationFailedError
from labra.core.ids import lab_today
from labra.patients import service
from labra.patients.age import age_text
from labra.patients.models import REFERRER_KINDS
from labra.web.templating import page, render

router = APIRouter(prefix="/frontdesk")

DB = Annotated[Session, Depends(get_session)]

SEX_LABELS = {"M": "Male", "F": "Female", "O": "Other"}
KIND_LABELS = {
    "doctor": "Doctor",
    "clinic": "Clinic",
    "hospital": "Hospital",
    "corporate": "Company",
    "self": "Self",
}


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise NotFoundError() from None


def _whole(value: str) -> int | None:
    """An age part as typed: empty is None, anything else not a whole number is -1, which
    the form check reports as out of range."""
    value = value.strip()
    if not value:
        return None
    return int(value) if value.isdigit() else -1


def _day(value: str) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


# Patients


@router.get("/patients", response_class=HTMLResponse)
@page("frontdesk/find-patient", "frontdesk/patients.html")
def patients(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("patient.view"))],
    q: str = "",
    page: int = 1,
) -> Response:
    today = lab_today()
    found = service.find_patients(db, principal, q, page)
    return render(
        request,
        "frontdesk/patients.html",
        {
            "patients": found,
            "ages": {p.id: age_text(p.dob, today) for p in found.items},
            "q": q,
            "sexes": SEX_LABELS,
            "can_edit": principal.can("patient.edit"),
        },
    )


def _patient_form(
    request: Request,
    patient: object,
    errors: dict[str, str],
    hint: service.DuplicateHint | None = None,
    status: int = 200,
) -> Response:
    return render(
        request,
        "frontdesk/patient_form.html",
        {"patient": patient, "errors": errors, "hint": hint, "sexes": SEX_LABELS},
        status_code=status,
    )


@router.get("/patients/new", response_class=HTMLResponse)
@page("frontdesk/find-patient", "frontdesk/patient_form.html")
def patient_new(
    request: Request, principal: Annotated[Principal, Depends(require("patient.edit"))]
) -> Response:
    return _patient_form(request, None, {})


@router.get("/patients/{patient_id}", response_class=HTMLResponse)
@page("frontdesk/find-patient", "frontdesk/patient_form.html")
def patient_edit(
    request: Request,
    patient_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("patient.edit"))],
) -> Response:
    return _patient_form(request, service.get_patient(db, principal, _uuid(patient_id)), {})


@router.post("/patients")
def patient_save(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("patient.edit"))],
    title: Annotated[str, Form()] = "",
    full_name: Annotated[str, Form()] = "",
    sex: Annotated[str, Form()] = "",
    dob: Annotated[str, Form()] = "",
    age_years: Annotated[str, Form()] = "",
    age_months: Annotated[str, Form()] = "",
    age_days: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    alt_phone: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    address: Annotated[str, Form()] = "",
    city: Annotated[str, Form()] = "",
    pincode: Annotated[str, Form()] = "",
    confirm_new: Annotated[bool, Form()] = False,
    patient_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    data = service.PatientInput(
        full_name=full_name,
        sex=sex,
        dob=_day(dob),
        age_years=_whole(age_years),
        age_months=_whole(age_months),
        age_days=_whole(age_days),
        title=title,
        phone=phone,
        alt_phone=alt_phone,
        email=email,
        address=address,
        city=city,
        pincode=pincode,
    )
    try:
        if patient_id:
            patient = service.update_patient(db, principal, _uuid(patient_id), data, row_version)
        else:
            patient = service.register_patient(db, principal, data, confirm_new=confirm_new)
    except ValidationFailedError as exc:
        db.rollback()
        errors = dict(exc.errors)
        if dob and data.dob is None:
            errors["dob"] = "Enter the date of birth as a date."
        values = SimpleNamespace(**vars(data), dob_text=dob, id=patient_id, row_version=row_version)
        hint = exc.hint if isinstance(exc, service.PossibleDuplicateError) else None
        return _patient_form(request, values, errors, hint, status=422)
    db.commit()
    return RedirectResponse(f"/frontdesk/patients?q={patient.patient_no}", status_code=303)


# Referrers


@router.get("/referrers", response_class=HTMLResponse)
@page("frontdesk/referrers", "frontdesk/referrers.html")
def referrers(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("referrer.view"))],
    q: str = "",
    page: int = 1,
) -> Response:
    return render(
        request,
        "frontdesk/referrers.html",
        {
            "referrers": service.referrer_page(db, principal, page, q),
            "q": q,
            "kinds": KIND_LABELS,
            "can_edit": principal.can("referrer.edit"),
        },
    )


def _referrer_form(
    request: Request, referrer: object, errors: dict[str, str], status: int = 200
) -> Response:
    return render(
        request,
        "frontdesk/referrer_form.html",
        {
            "referrer": referrer,
            "errors": errors,
            "kinds": {k: KIND_LABELS[k] for k in REFERRER_KINDS},
        },
        status_code=status,
    )


@router.get("/referrers/new", response_class=HTMLResponse)
@page("frontdesk/referrers", "frontdesk/referrer_form.html")
def referrer_new(
    request: Request, principal: Annotated[Principal, Depends(require("referrer.edit"))]
) -> Response:
    return _referrer_form(request, None, {})


@router.get("/referrers/{referrer_id}", response_class=HTMLResponse)
@page("frontdesk/referrers", "frontdesk/referrer_form.html")
def referrer_edit(
    request: Request,
    referrer_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("referrer.edit"))],
) -> Response:
    return _referrer_form(request, service.get_referrer(db, principal, _uuid(referrer_id)), {})


@router.post("/referrers")
def referrer_save(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("referrer.edit"))],
    kind: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    qualification: Annotated[str, Form()] = "",
    council_reg_no: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    is_active: Annotated[bool, Form()] = False,
    referrer_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    data = service.ReferrerInput(
        kind, name, qualification, council_reg_no, phone, is_active or not referrer_id
    )
    try:
        if referrer_id:
            service.update_referrer(db, principal, _uuid(referrer_id), data, row_version)
        else:
            service.create_referrer(db, principal, data)
    except ValidationFailedError as exc:
        db.rollback()
        values = SimpleNamespace(**vars(data), id=referrer_id, row_version=row_version)
        return _referrer_form(request, values, exc.errors, status=422)
    db.commit()
    return RedirectResponse("/frontdesk/referrers", status_code=303)
