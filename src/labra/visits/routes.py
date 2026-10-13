import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.billing import service as billing
from labra.core.consent import current_notice
from labra.core.currency import load_format
from labra.core.db import get_session
from labra.core.errors import ValidationFailedError
from labra.core.ids import lab_today
from labra.patients import service as patients
from labra.patients.age import age_text
from labra.visits import service
from labra.visits.models import Sample
from labra.web.barcode import code128
from labra.web.forms import as_uuid, day, local_minute, whole
from labra.web.labels import (
    BILL_STATUS_LABELS,
    COLLECTION_LABELS,
    KIND_LABELS,
    MODE_LABELS,
    SAMPLE_STATUS_LABELS,
    SEX_LABELS,
)
from labra.web.templating import page, render

router = APIRouter(prefix="/frontdesk")

DB = Annotated[Session, Depends(get_session)]

_PAYMENT_KEYS = ("mode", "amount", "reference")
# How many digits of a phone number are worth looking up.
MIN_PHONE_DIGITS = 4


class VisitForm(BaseModel):
    """The visit screen as the browser sends it. The same form goes to the preview, which
    reprices the order, and to Save."""

    client_ref: str = ""
    patient_id: str = ""
    phone: str = ""
    title: str = ""
    full_name: str = ""
    sex: str = ""
    dob: str = ""
    age_years: str = ""
    age_months: str = ""
    age_days: str = ""
    confirm_new: bool = False
    consent: bool = False
    # The box a test code or name is typed into.
    q: str = ""
    item: list[str] = Field(default_factory=list)
    charge_desc: list[str] = Field(default_factory=list)
    charge_amount: list[str] = Field(default_factory=list)
    charge_reason: list[str] = Field(default_factory=list)
    new_charge_desc: str = ""
    new_charge_amount: str = ""
    new_charge_reason: str = ""
    discount_kind: str = "amount"
    discount_value: str = ""
    discount_reason: str = ""
    referrer_id: str = ""
    collection_mode: str = "walk_in"
    promised_at: str = ""
    footer_note: str = ""
    internal_note: str = ""
    pay_mode: str = "cash"
    pay_amount: str = ""
    pay_reference: str = ""
    # What a button on the order asked for: add the typed code, add a match, remove a line,
    # add the extra charge. Empty when only the figures need working out again.
    op: str = ""
    arg: str = ""

    def charges(self) -> list[service.ChargeInput]:
        return [
            service.ChargeInput(*row)
            for row in zip(self.charge_desc, self.charge_amount, self.charge_reason, strict=False)
        ]

    def new_charge(self) -> service.ChargeInput | None:
        row = (self.new_charge_desc, self.new_charge_amount, self.new_charge_reason)
        return service.ChargeInput(*row) if any(v.strip() for v in row) else None


def _items(raw: list[str]) -> list[tuple[str, uuid.UUID]]:
    items: list[tuple[str, uuid.UUID]] = []
    for value in raw:
        kind, _, item_id = value.partition(":")
        try:
            items.append((kind, uuid.UUID(item_id)))
        except ValueError:
            continue
    return items


def _input(
    form: VisitForm, items: list[str], charges: list[service.ChargeInput]
) -> service.VisitInput:
    patient = None
    if not form.patient_id:
        patient = patients.PatientInput(
            full_name=form.full_name,
            sex=form.sex,
            dob=day(form.dob),
            age_years=whole(form.age_years),
            age_months=whole(form.age_months),
            age_days=whole(form.age_days),
            title=form.title,
            phone=form.phone.strip(),
        )
    payment = None
    if form.pay_amount.strip():
        payment = billing.PaymentInput(
            form.pay_mode, billing.parse_amount(form.pay_amount), form.pay_reference
        )
    return service.VisitInput(
        client_ref=as_uuid(form.client_ref),
        patient_id=as_uuid(form.patient_id) if form.patient_id else None,
        patient=patient,
        confirm_new=form.confirm_new,
        consent=form.consent,
        items=_items(items),
        charges=charges,
        discount_kind=form.discount_kind,
        discount_value=form.discount_value,
        discount_reason=form.discount_reason,
        referrer_id=as_uuid(form.referrer_id) if form.referrer_id else None,
        collection_mode=form.collection_mode,
        promised_at=local_minute(form.promised_at),
        footer_note=form.footer_note,
        internal_note=form.internal_note,
        payment=payment,
    )


def _visit_page(
    request: Request,
    db: Session,
    principal: Principal,
    form: VisitForm,
    problems: dict[str, str] | None = None,
    hint: patients.DuplicateHint | None = None,
    status: int = 200,
) -> Response:
    data = _input(form, form.item, form.charges())
    patient = patients.get_patient(db, principal, data.patient_id) if data.patient_id else None
    notice = current_notice(db)
    referrer = patients.get_referrer(db, principal, data.referrer_id) if data.referrer_id else None
    return render(
        request,
        "frontdesk/visit_form.html",
        {
            "form": form,
            "draft": service.price_order(db, principal, data),
            "problems": problems or {},
            "hint": hint,
            "patient": patient,
            "age": age_text(patient.dob, lab_today()) if patient else "",
            "consent": service.consent_on_file(db, patient.id, notice) if patient else None,
            "notice": notice,
            "referrer": referrer,
            "referrers": patients.pick_referrers(db, principal, ""),
            "can_add_referrer": principal.can("referrer.edit"),
            "can_take_payment": principal.can("payment.take", principal.branch_id),
            "fmt": load_format(db, principal.branch_id),
            "sexes": SEX_LABELS,
            "modes": MODE_LABELS,
            "collection_modes": COLLECTION_LABELS,
            "kinds": KIND_LABELS,
            "errors": {},
            "added": None,
            "q": "",
        },
        status_code=status,
    )


@router.get("/visits/new", response_class=HTMLResponse)
@page("frontdesk/new-visit", "frontdesk/visit_form.html")
def visit_new(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("visit.create"))],
    patient_id: str = "",
) -> Response:
    form = VisitForm(client_ref=str(uuid.uuid4()), patient_id=patient_id)
    return _visit_page(request, db, principal, form)


@router.get("/visits/new/patient", response_class=HTMLResponse)
@page("frontdesk/new-visit", "frontdesk/_patient_match.html")
def visit_patient_match(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("visit.create"))],
    phone: str = "",
) -> Response:
    """People already registered with the phone number being typed."""
    digits = phone.strip()
    looked = digits.isdigit() and len(digits) >= MIN_PHONE_DIGITS
    found = patients.find_patients(db, principal, digits, 1).items[:5] if looked else []
    today = lab_today()
    return render(
        request,
        "frontdesk/_patient_match.html",
        {
            "matches": found,
            "looked": looked,
            "ages": {p.id: age_text(p.dob, today) for p in found},
            "sexes": SEX_LABELS,
        },
    )


@router.get("/visits/new/tests", response_class=HTMLResponse)
@page("frontdesk/new-visit", "frontdesk/_test_hits.html")
def visit_test_hits(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("visit.create"))],
    q: str = "",
) -> Response:
    return render(
        request,
        "frontdesk/_test_hits.html",
        {
            "hits": service.find_items(db, principal, q),
            "q": q.strip(),
            "fmt": load_format(db, principal.branch_id),
        },
    )


@router.post("/visits/new/preview")
def visit_preview(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("visit.create"))],
    form: Annotated[VisitForm, Form()],
) -> Response:
    """Change the order as a button asked, then show its lines and totals again."""
    items = list(form.item)
    charges = form.charges()
    problems: dict[str, str] = {}
    done = ""
    typed = form.q.strip()
    if form.op == "code" and typed:
        hits = service.find_items(db, principal, typed, 1)
        if hits:
            items.append(f"{hits[0].item_type}:{hits[0].item_id}")
            done = "code"
        else:
            problems["items"] = f"No test or package matches “{typed}”."
    elif form.op == "add":
        items.append(form.arg)
        done = "code"
    elif form.op == "remove" and form.arg.isdigit():
        index = int(form.arg)
        if index < len(items):
            del items[index]
        elif index - len(items) < len(charges):
            del charges[index - len(items)]
    elif form.op == "charge":
        charge = form.new_charge()
        if charge is not None:
            charges.append(charge)
            done = "charge"
    draft = service.price_order(db, principal, _input(form, items, charges))
    if {"code": "items", "charge": "charge"}.get(done) in draft.problems:
        # The line was not added, so what was typed stays for the user to correct.
        done = ""
    return render(
        request,
        "frontdesk/_visit_order.html",
        {
            "draft": draft,
            "problems": draft.problems | problems,
            "done": done,
            "fmt": load_format(db, principal.branch_id),
        },
    )


@router.post("/visits")
def visit_save(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("visit.create"))],
    form: Annotated[VisitForm, Form()],
) -> Response:
    charges = form.charges()
    pending = form.new_charge()
    if pending is not None:
        charges.append(pending)
    data = _input(form, form.item, charges)
    problems: dict[str, str] = {}
    if form.q.strip():
        problems["items"] = (
            f"“{form.q.strip()}” is still in the test box. Press Enter to add it, or clear it."
        )
    if form.promised_at and data.promised_at is None:
        problems["promised_at"] = "Enter the promised time as a date and a time."
    if form.dob and data.patient is not None and data.patient.dob is None:
        problems["dob"] = "Enter the date of birth as a date."
    hint = None
    try:
        if problems:
            raise ValidationFailedError(problems)
        visit = service.save_visit(db, principal, data)
    except ValidationFailedError as exc:
        db.rollback()
        problems = {
            (f"pay_{key}" if key in _PAYMENT_KEYS else key): text
            for key, text in exc.errors.items()
        } | problems
        if isinstance(exc, patients.PossibleDuplicateError):
            hint = exc.hint
        return _visit_page(request, db, principal, form, problems, hint, status=422)
    db.commit()
    return RedirectResponse(f"/frontdesk/visits/{visit.id}?print=1", status_code=303)


def _live(samples: list[Sample]) -> list[Sample]:
    """The samples that still need a label: all but the cancelled ones."""
    return [sample for sample in samples if sample.status != "cancelled"]


@router.get("/visits/{visit_id}", response_class=HTMLResponse)
@page("frontdesk/bills-and-receipts", "frontdesk/visit_summary.html")
def visit_summary(
    request: Request,
    visit_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("visit.view"))],
    auto_print: Annotated[bool, Query(alias="print")] = False,
) -> Response:
    summary = service.visit_summary(db, principal, as_uuid(visit_id))
    bill = summary.bill
    if auto_print and bill is not None:
        # The bill goes to the A4 printer first, then the labels to the label printer.
        then = "&then=labels" if _live(summary.samples) else ""
        return RedirectResponse(f"/frontdesk/bills/{bill.id}/print?auto=1{then}", status_code=303)
    return render(
        request,
        "frontdesk/visit_summary.html",
        {
            "s": summary,
            "has_labels": bool(_live(summary.samples)),
            "age": age_text(summary.patient.dob, lab_today()),
            "fmt": load_format(db, summary.visit.branch_id),
            "sexes": SEX_LABELS,
            "modes": MODE_LABELS,
            "collection_modes": COLLECTION_LABELS,
            "bill_statuses": BILL_STATUS_LABELS,
            "sample_statuses": SAMPLE_STATUS_LABELS,
            "can_pay": principal.can("payment.take", summary.visit.branch_id),
            "can_cancel": principal.can("bill.cancel", summary.visit.branch_id),
        },
    )


# Sample labels and collection


@router.get("/visits/{visit_id}/labels", response_class=HTMLResponse)
@page("frontdesk/labels", "frontdesk/labels.html")
def visit_labels(
    request: Request,
    visit_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("visit.view"))],
    auto_print: Annotated[bool, Query(alias="print")] = False,
) -> Response:
    summary = service.visit_summary(db, principal, as_uuid(visit_id))
    back = f"/frontdesk/visits/{summary.visit.id}"
    labels = [
        {
            "sample": sample,
            "bars": code128(sample.sample_no),
            "tests": [
                test.short_name or test.code
                for ordered, test in summary.tests
                if ordered.sample_id == sample.id
            ],
        }
        for sample in _live(summary.samples)
    ]
    return render(
        request,
        "frontdesk/labels.html",
        {
            "s": summary,
            "labels": labels,
            "age": age_text(summary.patient.dob, lab_today()),
            "auto": auto_print and bool(labels),
            "after": back,
            "back": back,
        },
    )


def _collect_page(
    request: Request,
    db: Session,
    principal: Principal,
    chosen: str,
    sample_no: str = "",
    errors: dict[str, str] | None = None,
    done: str = "",
    status: int = 200,
) -> Response:
    staff = service.collectors(db, principal)
    if chosen not in {str(user.id) for user in staff}:
        chosen = str(principal.user_id)
    return render(
        request,
        "frontdesk/collect.html",
        {
            "staff": staff,
            "chosen": chosen,
            "sample_no": sample_no,
            "errors": errors or {},
            "done": service.find_sample(db, principal, done) if done else None,
        },
        status_code=status,
    )


@router.get("/collect", response_class=HTMLResponse)
@page("frontdesk/labels", "frontdesk/collect.html")
def collect(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("sample.collect"))],
    by: str = "",
    done: str = "",
) -> Response:
    return _collect_page(request, db, principal, by, done=done)


@router.post("/collect")
def collect_save(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("sample.collect"))],
    sample_no: Annotated[str, Form()] = "",
    collected_by: Annotated[str, Form()] = "",
) -> Response:
    try:
        who = uuid.UUID(collected_by)
    except ValueError:
        who = None
    try:
        sample = service.collect_sample(db, principal, sample_no, who)
    except ValidationFailedError as exc:
        db.rollback()
        return _collect_page(
            request, db, principal, collected_by, sample_no, exc.errors, status=422
        )
    db.commit()
    return RedirectResponse(
        f"/frontdesk/collect?by={collected_by}&done={sample.sample_no}", status_code=303
    )
