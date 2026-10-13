"""External labs and what each charges per test.

A rate is never edited: a change closes the open row and starts a new one, so the cost of a
test that was sent out last month can still be traced.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.catalog.models import Test
from labra.core import audit
from labra.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from labra.core.ids import lab_today, utcnow
from labra.core.paging import Page, page_of
from labra.extlabs.models import ExternalLab, ExternalLabRate
from labra.org.service import stale

# A lab's desk line may be a landline with an STD code, so this is looser than a mobile.
_PHONE_RE = re.compile(r"^\+?\d[\d -]{5,13}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_TAT_HOURS = 24 * 60


def _check(principal: Principal, permission: str) -> None:
    if not principal.can(permission):
        raise PermissionDeniedError()


@dataclass
class LabInput:
    name: str
    nabl_cert_no: str = ""
    contact_name: str = ""
    phone: str = ""
    email: str = ""
    results_email: str = ""
    portal_url: str = ""
    dpa_signed_on: date | None = None
    share_phone: bool = False
    share_address: bool = False
    is_active: bool = True

    def problems(self, today: date) -> dict[str, str]:
        p: dict[str, str] = {}
        if not self.name.strip():
            p["name"] = "Enter the lab's name."
        if self.phone.strip() and not _PHONE_RE.match(self.phone.strip()):
            p["phone"] = "Digits only, with the STD code for a landline."
        for key in ("email", "results_email"):
            value = getattr(self, key).strip()
            if value and not _EMAIL_RE.match(value):
                p[key] = "Enter an email address, for example reports@example.org."
        url = self.portal_url.strip()
        if url and not url.startswith(("https://", "http://")):
            p["portal_url"] = "Start the address with https://."
        if self.dpa_signed_on is not None and self.dpa_signed_on > today:
            p["dpa_signed_on"] = "This date is in the future."
        return p

    def columns(self) -> dict[str, object]:
        return {
            "name": " ".join(self.name.split()),
            "nabl_cert_no": self.nabl_cert_no.strip(),
            "contact_name": " ".join(self.contact_name.split()),
            "phone": self.phone.strip(),
            "email": self.email.strip(),
            "results_email": self.results_email.strip(),
            "portal_url": self.portal_url.strip(),
            "dpa_signed_on": self.dpa_signed_on,
            "share_phone": self.share_phone,
            "share_address": self.share_address,
            "is_active": self.is_active,
        }


def _name_taken(db: Session, name: str, except_id: uuid.UUID | None) -> bool:
    stmt = select(ExternalLab.id).where(func.lower(ExternalLab.name) == name.lower())
    if except_id is not None:
        stmt = stmt.where(ExternalLab.id != except_id)
    return db.scalar(stmt) is not None


def _problems(
    db: Session, data: LabInput, today: date | None, except_id: uuid.UUID | None = None
) -> dict[str, str]:
    problems = data.problems(today or lab_today())
    if "name" not in problems and _name_taken(db, " ".join(data.name.split()), except_id):
        problems["name"] = "Another lab already has this name."
    return problems


def lab_page(db: Session, principal: Principal, page: int) -> Page[ExternalLab]:
    _check(principal, "extlab.view")
    stmt = select(ExternalLab).order_by(
        ExternalLab.is_active.desc(), ExternalLab.name, ExternalLab.id
    )
    return page_of(db, stmt, page)


def get_lab(db: Session, principal: Principal, lab_id: uuid.UUID) -> ExternalLab:
    _check(principal, "extlab.view")
    lab = db.get(ExternalLab, lab_id)
    if lab is None:
        raise NotFoundError()
    return lab


def create_lab(
    db: Session, principal: Principal, data: LabInput, today: date | None = None
) -> ExternalLab:
    _check(principal, "extlab.edit")
    problems = _problems(db, data, today)
    if problems:
        raise ValidationFailedError(problems)
    lab = ExternalLab(**data.columns(), created_by=principal.user_id)
    db.add(lab)
    db.flush()
    audit.record(db, "extlab.create", "external_lab", lab.id, user_id=principal.user_id)
    return lab


def update_lab(
    db: Session,
    principal: Principal,
    lab_id: uuid.UUID,
    data: LabInput,
    row_version: int,
    today: date | None = None,
) -> ExternalLab:
    _check(principal, "extlab.edit")
    lab = get_lab(db, principal, lab_id)
    if lab.row_version != row_version:
        raise stale(db, lab)
    problems = _problems(db, data, today, lab.id)
    if problems:
        raise ValidationFailedError(problems)
    values = data.columns()
    changed = [k for k, v in values.items() if getattr(lab, k) != v]
    for k in changed:
        setattr(lab, k, values[k])
    if changed:
        lab.updated_by = principal.user_id
        db.flush()
        audit.record(
            db,
            "extlab.update",
            "external_lab",
            lab.id,
            {"fields": changed},
            user_id=principal.user_id,
        )
    return lab


# Rates


@dataclass
class RateRow:
    rate: ExternalLabRate
    test: Test


@dataclass
class LabQuote:
    """What one lab charges for a test now, for the person choosing where to send it."""

    lab: ExternalLab
    rate: ExternalLabRate


def _money(raw: str | Decimal, problems: dict[str, str]) -> Decimal | None:
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        value = Decimal("NaN")
    if not value.is_finite() or value < 0 or value != value.quantize(Decimal("0.01")):
        problems["cost"] = "A cost of zero or more, with at most two decimals."
        return None
    return value.quantize(Decimal("0.01"))


def _hours(raw: str | int, problems: dict[str, str]) -> int | None:
    text = str(raw).strip()
    if not (text.isascii() and text.isdigit()) or not 0 < int(text[:9]) <= MAX_TAT_HOURS:
        problems["tat_hours"] = f"Whole hours, from 1 to {MAX_TAT_HOURS}."
        return None
    return int(text)


def set_rate(
    db: Session,
    principal: Principal,
    lab_id: uuid.UUID,
    test_code: str,
    cost: str | Decimal,
    tat_hours: str | int,
    their_test_code: str = "",
) -> ExternalLabRate:
    """What the lab charges for a test from now on. The rate in force until now is closed,
    not changed."""
    _check(principal, "extlab.edit")
    lab = get_lab(db, principal, lab_id)
    problems: dict[str, str] = {}
    code = test_code.strip().lower()
    test = db.scalar(select(Test).where(Test.code == code)) if code else None
    if test is None:
        problems["test_code"] = "No test has this code." if code else "Enter the test's code."
    value = _money(cost, problems)
    hours = _hours(tat_hours, problems)
    if problems or test is None or value is None or hours is None:
        raise ValidationFailedError(problems)
    now = utcnow()
    open_row = db.scalar(
        select(ExternalLabRate)
        .where(
            ExternalLabRate.external_lab_id == lab.id,
            ExternalLabRate.test_id == test.id,
            ExternalLabRate.valid_to.is_(None),
        )
        .with_for_update()
    )
    before = None
    if open_row is not None:
        before = {"cost": open_row.cost, "tat_hours": open_row.tat_hours}
        open_row.valid_to = now
        open_row.updated_by = principal.user_id
        db.flush()
    row = ExternalLabRate(
        external_lab_id=lab.id,
        test_id=test.id,
        their_test_code=their_test_code.strip(),
        cost=value,
        tat_hours=hours,
        valid_from=now,
        created_by=principal.user_id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        "extlab.rate_set",
        "external_lab_rate",
        row.id,
        {
            "external_lab_id": str(lab.id),
            "test_id": str(test.id),
            "before": before,
            "after": {"cost": value, "tat_hours": hours},
        },
        user_id=principal.user_id,
    )
    return row


def end_rate(db: Session, principal: Principal, lab_id: uuid.UUID, rate_id: uuid.UUID) -> None:
    """The lab no longer does this test for us."""
    _check(principal, "extlab.edit")
    row = db.get(ExternalLabRate, rate_id)
    if row is None or row.external_lab_id != lab_id or row.valid_to is not None:
        raise NotFoundError()
    row.valid_to = utcnow()
    row.updated_by = principal.user_id
    db.flush()
    audit.record(
        db,
        "extlab.rate_end",
        "external_lab_rate",
        row.id,
        {"external_lab_id": str(lab_id), "test_id": str(row.test_id)},
        user_id=principal.user_id,
    )


def rates_of_lab(
    db: Session, principal: Principal, lab_id: uuid.UUID, history: bool = False
) -> list[RateRow]:
    """The lab's rates in force by test code, or with `history` the ones that ended, newest
    first."""
    _check(principal, "extlab.view")
    stmt = (
        select(ExternalLabRate, Test)
        .join(Test, Test.id == ExternalLabRate.test_id)
        .where(ExternalLabRate.external_lab_id == lab_id)
    )
    if history:
        stmt = stmt.where(ExternalLabRate.valid_to.is_not(None)).order_by(
            ExternalLabRate.valid_to.desc(), Test.code
        )
    else:
        stmt = stmt.where(ExternalLabRate.valid_to.is_(None)).order_by(Test.code)
    return [RateRow(rate, test) for rate, test in db.execute(stmt)]


def quotes_for(
    db: Session, principal: Principal, test_id: uuid.UUID, at: datetime | None = None
) -> list[LabQuote]:
    """The active labs that do a test and what each charged at `at` (now, if not given),
    cheapest first."""
    _check(principal, "extlab.view")
    at = at or utcnow()
    stmt = (
        select(ExternalLab, ExternalLabRate)
        .join(ExternalLabRate, ExternalLabRate.external_lab_id == ExternalLab.id)
        .where(
            ExternalLab.is_active,
            ExternalLabRate.test_id == test_id,
            ExternalLabRate.valid_from <= at,
            or_(ExternalLabRate.valid_to.is_(None), ExternalLabRate.valid_to > at),
        )
        .order_by(ExternalLabRate.cost, ExternalLabRate.tat_hours, ExternalLab.name)
    )
    return [LabQuote(lab, rate) for lab, rate in db.execute(stmt)]
