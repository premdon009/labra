import uuid
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.billing import service
from labra.billing.models import Bill
from labra.core.currency import format_from_snapshot, load_format
from labra.core.db import get_session
from labra.core.errors import ValidationFailedError
from labra.web.forms import RowVersion, as_uuid, day, page_no
from labra.web.labels import BILL_STATUS_LABELS, MODE_LABELS
from labra.web.templating import page, render

router = APIRouter(prefix="/frontdesk")

DB = Annotated[Session, Depends(get_session)]


@router.get("/bills", response_class=HTMLResponse)
@page("frontdesk/bills-and-receipts", "frontdesk/bills.html")
def bills(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("bill.view"))],
    day_from: Annotated[str, Query(alias="from")] = "",
    day_to: Annotated[str, Query(alias="to")] = "",
    status: str = "",
    page: str = "1",
) -> Response:
    return render(
        request,
        "frontdesk/bills.html",
        {
            "bills": service.bill_page(
                db, principal, page_no(page), day(day_from), day(day_to), status
            ),
            "day_from": day_from,
            "day_to": day_to,
            "status": status,
            "statuses": BILL_STATUS_LABELS,
            "fmt": load_format(db, principal.branch_id),
        },
    )


@router.get("/dues", response_class=HTMLResponse)
@page("frontdesk/dues-and-payments", "frontdesk/dues.html")
def dues(
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require("bill.view"))],
    page: str = "1",
) -> Response:
    return render(
        request,
        "frontdesk/dues.html",
        {
            "bills": service.dues_page(db, principal, page_no(page)),
            "fmt": load_format(db, principal.branch_id),
            "can_pay": principal.can("payment.take", principal.branch_id),
        },
    )


# Printing


def _printed(db: Session, bill: Bill) -> dict[str, object]:
    """What a bill prints from: its frozen snapshot, never today's settings."""
    return {
        "bill": bill,
        "snap": bill.print_snapshot,
        "fmt": format_from_snapshot(bill.print_snapshot["currency"]),
        "modes": MODE_LABELS,
        "back": f"/frontdesk/visits/{bill.visit_id}",
    }


@router.get("/bills/{bill_id}/print", response_class=HTMLResponse)
@page("frontdesk/bills-and-receipts", "frontdesk/bill_print.html")
def bill_print(
    request: Request,
    bill_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("bill.view"))],
    auto: bool = False,
    then: str = "",
) -> Response:
    bill = service.get_bill(db, principal, as_uuid(bill_id))
    context = _printed(db, bill) | {
        "lines": service.bill_lines(db, bill.id),
        "payments": service.bill_payments(db, bill.id),
        "refund": service.bill_refund(db, bill.id),
        "auto": auto,
    }
    # After a new visit's bill, the sample labels print next.
    after = f"{context['back']}/labels?print=1" if then == "labels" else context["back"]
    return render(request, "frontdesk/bill_print.html", context | {"after": after})


@router.get("/payments/{payment_id}/print", response_class=HTMLResponse)
@page("frontdesk/bills-and-receipts", "frontdesk/receipt_print.html")
def receipt_print(
    request: Request,
    payment_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("bill.view"))],
    auto: bool = False,
    then: str = "",
) -> Response:
    payment, bill = service.get_payment(db, principal, as_uuid(payment_id))
    context = _printed(db, bill) | {"payment": payment, "auto": auto}
    after = "/frontdesk/dues" if then == "dues" else context["back"]
    return render(request, "frontdesk/receipt_print.html", context | {"after": after})


# Taking a payment


def _pay_form(
    request: Request,
    db: Session,
    bill: Bill,
    values: object,
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    return render(
        request,
        "frontdesk/pay.html",
        {
            "bill": bill,
            "values": values,
            "errors": errors,
            "modes": MODE_LABELS,
            "fmt": load_format(db, bill.branch_id),
        },
        status_code=status,
    )


@router.get("/bills/{bill_id}/pay", response_class=HTMLResponse)
@page("frontdesk/dues-and-payments", "frontdesk/pay.html")
def pay(
    request: Request,
    bill_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("payment.take"))],
) -> Response:
    bill = service.get_bill(db, principal, as_uuid(bill_id))
    values = SimpleNamespace(
        client_ref=uuid.uuid4(),
        mode="cash",
        amount=f"{bill.net - bill.paid:.2f}",
        reference="",
        same_payment=False,
    )
    return _pay_form(request, db, bill, values, {})


@router.post("/bills/{bill_id}/pay")
def pay_save(
    request: Request,
    bill_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("payment.take"))],
    client_ref: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
    reference: Annotated[str, Form()] = "",
    same_payment: Annotated[bool, Form()] = False,
) -> Response:
    data = service.PaymentInput(mode, service.parse_amount(amount), reference, same_payment)
    try:
        payment = service.take_payment(db, principal, as_uuid(bill_id), data, as_uuid(client_ref))
    except ValidationFailedError as exc:
        db.rollback()
        bill = service.get_bill(db, principal, as_uuid(bill_id))
        values = SimpleNamespace(
            client_ref=client_ref,
            mode=mode,
            amount=amount,
            reference=reference,
            same_payment=same_payment,
        )
        return _pay_form(request, db, bill, values, exc.errors, status=422)
    db.commit()
    return RedirectResponse(
        f"/frontdesk/payments/{payment.id}/print?auto=1&then=dues", status_code=303
    )


# Cancelling


def _cancel_form(
    request: Request,
    db: Session,
    bill: Bill,
    values: object,
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    return render(
        request,
        "frontdesk/bill_cancel.html",
        {
            "bill": bill,
            "values": values,
            "errors": errors,
            "modes": MODE_LABELS,
            "fmt": load_format(db, bill.branch_id),
        },
        status_code=status,
    )


@router.get("/bills/{bill_id}/cancel", response_class=HTMLResponse)
@page("frontdesk/bills-and-receipts", "frontdesk/bill_cancel.html")
def cancel(
    request: Request,
    bill_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("bill.cancel"))],
) -> Response:
    bill = service.get_bill(db, principal, as_uuid(bill_id))
    values = SimpleNamespace(reason="", refund_mode="cash", refund_reference="")
    return _cancel_form(request, db, bill, values, {})


@router.post("/bills/{bill_id}/cancel")
def cancel_save(
    request: Request,
    bill_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("bill.cancel"))],
    reason: Annotated[str, Form()] = "",
    confirm: Annotated[str, Form()] = "",
    row_version: RowVersion = 0,
    refund_mode: Annotated[str, Form()] = "cash",
    refund_reference: Annotated[str, Form()] = "",
) -> Response:
    try:
        bill = service.cancel_bill(
            db,
            principal,
            as_uuid(bill_id),
            reason,
            confirm == "yes",
            row_version,
            refund_mode,
            refund_reference,
        )
    except ValidationFailedError as exc:
        db.rollback()
        bill = service.get_bill(db, principal, as_uuid(bill_id))
        values = SimpleNamespace(
            reason=reason, refund_mode=refund_mode, refund_reference=refund_reference
        )
        return _cancel_form(request, db, bill, values, exc.errors, status=422)
    db.commit()
    return RedirectResponse(f"/frontdesk/visits/{bill.visit_id}", status_code=303)
