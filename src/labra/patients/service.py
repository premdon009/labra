"""Patients and referrers: find, register, change.

A patient belongs to the branches where they registered or visited; elsewhere they are
not found. The duplicate check looks across the whole lab but never shows another
branch's patient.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.core import audit
from labra.core.dialect import similar, similarity
from labra.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from labra.core.ids import lab_today
from labra.core.numbering import next_number
from labra.core.paging import Page, page_of
from labra.org.models import Branch
from labra.org.service import stale
from labra.patients.age import MAX_AGE_YEARS, age_ymd, estimated_dob
from labra.patients.models import REFERRER_KINDS, SEXES, Patient, Referrer
from labra.visits.models import Visit

_PHONE_RE = re.compile(r"^[6-9]\d{9}$")
_PINCODE_RE = re.compile(r"^[1-9]\d{5}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# How alike two names must be (trigram similarity) to count as the same person.
SAME_NAME = 0.45


def _check(principal: Principal, permission: str, branch_id: uuid.UUID | None = None) -> None:
    if not principal.can(permission, branch_id):
        raise PermissionDeniedError()


# Patients


@dataclass
class PatientInput:
    """The registration form. Either `dob`, or an age in years, months and days."""

    full_name: str
    sex: str
    dob: date | None = None
    age_years: int | None = None
    age_months: int | None = None
    age_days: int | None = None
    title: str = ""
    phone: str = ""
    alt_phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    pincode: str = ""

    def birth(self, today: date) -> tuple[date | None, bool, dict[str, str]]:
        """The date of birth to store, whether it is estimated, and any problems."""
        if self.dob is not None:
            if self.dob > today:
                return None, False, {"dob": "The date of birth can't be after today."}
            if age_ymd(self.dob, today)[0] > MAX_AGE_YEARS:
                return None, False, {"dob": f"Enter a date of birth within {MAX_AGE_YEARS} years."}
            return self.dob, False, {}
        parts = (self.age_years or 0, self.age_months or 0, self.age_days or 0)
        if not any(parts):
            return None, False, {"dob": "Enter the date of birth or the age."}
        if min(parts) < 0 or parts[0] > MAX_AGE_YEARS or parts[1] > 11 or parts[2] > 30:
            return None, False, {"dob": "Enter years up to 150, months up to 11, days up to 30."}
        return estimated_dob(*parts, today), True, {}

    def problems(self) -> dict[str, str]:
        p: dict[str, str] = {}
        if not self.full_name.strip():
            p["full_name"] = "Enter the patient's name."
        if self.sex not in SEXES:
            p["sex"] = "Choose male, female or other."
        for name in ("phone", "alt_phone"):
            if getattr(self, name) and not _PHONE_RE.match(getattr(self, name)):
                p[name] = "Ten digits, starting with 6 to 9."
        if self.email and not _EMAIL_RE.match(self.email):
            p["email"] = "Enter an email address like name@example.com."
        if self.pincode and not _PINCODE_RE.match(self.pincode):
            p["pincode"] = "Six digits, for example 560001."
        return p

    def columns(self) -> dict[str, str]:
        return {
            "title": self.title.strip(),
            "full_name": " ".join(self.full_name.split()),
            "sex": self.sex,
            "phone": self.phone.strip(),
            "alt_phone": self.alt_phone.strip(),
            "email": self.email.strip(),
            "address": self.address.strip(),
            "city": self.city.strip(),
            "pincode": self.pincode.strip(),
        }


@dataclass
class DuplicateHint:
    """Patients like the one being registered: those the user may see, and whether there
    are others at branches they can't see."""

    matches: list[Patient] = field(default_factory=list)
    elsewhere: bool = False

    def __bool__(self) -> bool:
        return bool(self.matches) or self.elsewhere


class PossibleDuplicateError(ValidationFailedError):
    def __init__(self, hint: DuplicateHint) -> None:
        if hint.matches:
            message = "A patient with this phone number and a similar name is already registered."
        else:
            message = (
                "A patient with this phone number and a similar name may be registered at "
                "another branch."
            )
        super().__init__({"duplicate": message})
        self.hint = hint


def _visible(principal: Principal) -> ColumnElement[bool]:
    branches = principal.branches_with("patient.view")
    return or_(
        Patient.registered_branch_id.in_(branches),
        exists().where(Visit.patient_id == Patient.id, Visit.branch_id.in_(branches)),
    )


def find_patients(db: Session, principal: Principal, q: str, page: int) -> Page[Patient]:
    """By phone (or its first digits), patient number, or name, spelling variants included.
    With nothing typed, the newest registrations come first."""
    q = " ".join(q.split())
    stmt = select(Patient).where(_visible(principal))
    if not q:
        stmt = stmt.order_by(Patient.created_at.desc(), Patient.id)
    elif q.isdigit():
        stmt = stmt.where(
            or_(
                Patient.phone.startswith(q, autoescape=True),
                Patient.alt_phone.startswith(q, autoescape=True),
            )
        ).order_by(Patient.full_name, Patient.id)
    elif "/" in q:
        stmt = stmt.where(
            func.upper(Patient.patient_no).endswith(q.upper(), autoescape=True)
        ).order_by(Patient.patient_no)
    else:
        stmt = stmt.where(
            or_(Patient.full_name.icontains(q, autoescape=True), similar(Patient.full_name, q))
        ).order_by(similarity(Patient.full_name, q).desc(), Patient.full_name, Patient.id)
    return page_of(db, stmt, page)


def get_patient(db: Session, principal: Principal, patient_id: uuid.UUID) -> Patient:
    """Patients outside the user's branches are reported as not found."""
    patient = db.scalar(select(Patient).where(Patient.id == patient_id, _visible(principal)))
    if patient is None:
        raise NotFoundError()
    return patient


def possible_duplicates(
    db: Session, principal: Principal, data: PatientInput, exclude: uuid.UUID | None = None
) -> DuplicateHint:
    """Same phone and a similar name, anywhere in the lab."""
    if not data.phone:
        return DuplicateHint()
    name = " ".join(data.full_name.split())
    stmt = select(Patient.id).where(
        or_(Patient.phone == data.phone, Patient.alt_phone == data.phone),
        or_(
            func.lower(Patient.full_name) == name.lower(),
            similarity(Patient.full_name, name) >= SAME_NAME,
        ),
    )
    if exclude is not None:
        stmt = stmt.where(Patient.id != exclude)
    ids = list(db.scalars(stmt))
    if not ids:
        return DuplicateHint()
    seen = list(
        db.scalars(
            select(Patient)
            .where(Patient.id.in_(ids), _visible(principal))
            .order_by(Patient.patient_no)
        )
    )
    return DuplicateHint(seen, len(seen) < len(ids))


def insert_patient(
    db: Session,
    principal: Principal,
    data: PatientInput,
    today: date | None = None,
    confirm_new: bool = False,
) -> Patient:
    """Register at the user's branch, without an audit row: the caller writes it, after
    any other number series locks it needs (the audit lock is always taken last)."""
    _check(principal, "patient.edit")
    if principal.branch_id is None:
        raise PermissionDeniedError()
    today = today or lab_today()
    dob, estimated, problems = data.birth(today)
    problems |= data.problems()
    if problems or dob is None:
        raise ValidationFailedError(problems)
    if not confirm_new:
        hint = possible_duplicates(db, principal, data)
        if hint:
            raise PossibleDuplicateError(hint)
    branch = db.get(Branch, principal.branch_id)
    if branch is None:
        raise NotFoundError()
    patient = Patient(
        **data.columns(),
        patient_no=next_number(db, "patient", branch.id, branch.code, today),
        registered_branch_id=branch.id,
        dob=dob,
        dob_is_estimated=estimated,
        created_by=principal.user_id,
    )
    db.add(patient)
    db.flush()
    return patient


def register_patient(
    db: Session,
    principal: Principal,
    data: PatientInput,
    today: date | None = None,
    confirm_new: bool = False,
) -> Patient:
    patient = insert_patient(db, principal, data, today, confirm_new)
    audit.record(
        db,
        "patient.create",
        "patient",
        patient.id,
        user_id=principal.user_id,
        branch_id=patient.registered_branch_id,
    )
    return patient


def update_patient(
    db: Session,
    principal: Principal,
    patient_id: uuid.UUID,
    data: PatientInput,
    row_version: int,
    today: date | None = None,
) -> Patient:
    _check(principal, "patient.edit")
    patient = get_patient(db, principal, patient_id)
    if patient.row_version != row_version:
        raise stale(db, patient)
    dob, estimated, problems = data.birth(today or lab_today())
    problems |= data.problems()
    if problems or dob is None:
        raise ValidationFailedError(problems)
    # The form shows the stored date; left as it was, an estimate stays an estimate.
    if dob == patient.dob:
        estimated = patient.dob_is_estimated
    values: dict[str, object] = {**data.columns(), "dob": dob, "dob_is_estimated": estimated}
    changed = [k for k, v in values.items() if getattr(patient, k) != v]
    for k in changed:
        setattr(patient, k, values[k])
    if changed:
        patient.updated_by = principal.user_id
        db.flush()
        # Names of the fields only: the values are personal data.
        audit.record(
            db,
            "patient.update",
            "patient",
            patient.id,
            {"fields": changed},
            user_id=principal.user_id,
        )
    return patient


# Referrers


@dataclass
class ReferrerInput:
    kind: str
    name: str
    qualification: str = ""
    council_reg_no: str = ""
    phone: str = ""
    is_active: bool = True

    def problems(self) -> dict[str, str]:
        p: dict[str, str] = {}
        if self.kind not in REFERRER_KINDS:
            p["kind"] = "Choose doctor, clinic, hospital, company or self."
        if not self.name.strip():
            p["name"] = "Enter the name."
        if self.phone and not _PHONE_RE.match(self.phone):
            p["phone"] = "Ten digits, starting with 6 to 9."
        return p

    def columns(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "name": " ".join(self.name.split()),
            "qualification": self.qualification.strip(),
            "council_reg_no": self.council_reg_no.strip(),
            "phone": self.phone.strip(),
            "is_active": self.is_active,
        }


def referrer_page(db: Session, principal: Principal, page: int, q: str = "") -> Page[Referrer]:
    _check(principal, "referrer.view")
    stmt = select(Referrer)
    q = " ".join(q.split())
    if q:
        stmt = stmt.where(Referrer.name.icontains(q, autoescape=True))
    return page_of(db, stmt.order_by(Referrer.is_active.desc(), Referrer.name, Referrer.id), page)


def pick_referrers(db: Session, principal: Principal, q: str, limit: int = 10) -> list[Referrer]:
    """Active referrers for the visit screen, closest name first."""
    _check(principal, "referrer.view")
    q = " ".join(q.split())
    stmt = select(Referrer).where(Referrer.is_active)
    if q:
        stmt = stmt.where(
            or_(Referrer.name.icontains(q, autoescape=True), similar(Referrer.name, q))
        ).order_by(similarity(Referrer.name, q).desc(), Referrer.name)
    else:
        stmt = stmt.order_by(Referrer.name)
    return list(db.scalars(stmt.limit(limit)))


def get_referrer(db: Session, principal: Principal, referrer_id: uuid.UUID) -> Referrer:
    _check(principal, "referrer.view")
    referrer = db.get(Referrer, referrer_id)
    if referrer is None:
        raise NotFoundError()
    return referrer


def create_referrer(db: Session, principal: Principal, data: ReferrerInput) -> Referrer:
    _check(principal, "referrer.edit")
    problems = data.problems()
    if problems:
        raise ValidationFailedError(problems)
    referrer = Referrer(**data.columns(), created_by=principal.user_id)
    db.add(referrer)
    db.flush()
    audit.record(db, "referrer.create", "referrer", referrer.id, user_id=principal.user_id)
    return referrer


def update_referrer(
    db: Session, principal: Principal, referrer_id: uuid.UUID, data: ReferrerInput, row_version: int
) -> Referrer:
    _check(principal, "referrer.edit")
    referrer = get_referrer(db, principal, referrer_id)
    if referrer.row_version != row_version:
        raise stale(db, referrer)
    problems = data.problems()
    if problems:
        raise ValidationFailedError(problems)
    values = data.columns()
    changed = [k for k, v in values.items() if getattr(referrer, k) != v]
    for k in changed:
        setattr(referrer, k, values[k])
    if changed:
        referrer.updated_by = principal.user_id
        db.flush()
        audit.record(
            db,
            "referrer.update",
            "referrer",
            referrer.id,
            {"fields": changed},
            user_id=principal.user_id,
        )
    return referrer
