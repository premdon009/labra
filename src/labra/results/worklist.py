"""What the lab reads: the worklist, a visit's tests as the grid shows them, and each row's
previous value.

Nothing here writes. The patient is carried as name, sex and date of birth only: no phone,
no address.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Select, exists, select
from sqlalchemy.orm import Session, aliased

from labra.auth.principal import Principal
from labra.catalog import service as catalog
from labra.catalog import units
from labra.catalog.models import (
    Department,
    ReferenceBand,
    ReferenceRange,
    Test,
    TestMethod,
    TestParameter,
)
from labra.core.consent import current_notice
from labra.core.dialect import latest_per
from labra.core.errors import NotFoundError, PermissionDeniedError
from labra.core.ids import IST, lab_today
from labra.core.models import Consent
from labra.core.money import ZERO, allocate
from labra.core.paging import Page, page_of
from labra.extlabs import service as extlabs
from labra.extlabs.models import ExternalLab
from labra.org.models import AppUser, Branch
from labra.patients.age import age_text
from labra.patients.models import Patient
from labra.results.flags import pick_range, state_of
from labra.results.models import (
    CriticalNotification,
    ExternalDocumentTest,
    Result,
    Verification,
)
from labra.visits.models import OrderItem, OrderTest, Sample, Visit
from labra.visits.service import main_lab_id

# Values can be typed and changed until a signatory verifies the test.
EDITABLE = ("in_lab", "resulted")
# What the worklist shows when no status is picked: work that is here or on its way.
OPEN = ("collected", "in_lab", "resulted")
STATUSES = ("collected", "in_lab", "resulted", "sent_out", "verified", "released")
# A result counts as a patient's previous value once a signatory has stood behind it.
SIGNED_OFF = ("verified", "released")
# A test can change hands until it leaves the building or has a result.
ROUTABLE = ("ordered", "collected", "in_lab")
CRITICAL = ("LL", "HH")
BADGES = {
    "normal": "✓",
    "low": "↓ L",
    "high": "↑ H",
    "abnormal": "A",
}


def plain(number: Decimal) -> str:
    """A stored number without the padding the column adds: 199.0000 reads 199."""
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def shown(number: Decimal, decimals: int) -> str:
    """A value with the decimal places its parameter reports."""
    return format(number.quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP), "f")


def range_text(low: Decimal | None, high: Decimal | None, text: str = "") -> str:
    if text:
        return text
    if low is not None and high is not None:
        return f"{plain(low)} – {plain(high)}"  # noqa: RUF001  the dash ranges print with
    if low is not None:
        return f"≥ {plain(low)}"
    return f"≤ {plain(high)}" if high is not None else ""


@dataclass
class Sheet:
    """One ordered test with everything needed to read its values: the patient's sex and
    age at collection, the parameters in report order, their ranges and the results so far."""

    ordered: OrderTest
    test: Test
    visit: Visit
    patient_name: str
    sex: str
    dob: date
    age_days: int
    parameters: list[TestParameter]
    ranges: dict[uuid.UUID, list[ReferenceRange]] = field(default_factory=dict)
    results: dict[uuid.UUID, Result] = field(default_factory=dict)
    # Set while values are being saved: why the test was reopened after verification, if
    # it was, and whether any value has changed.
    reopen_reason: str = ""
    changed: bool = False

    def range_for(self, parameter_id: uuid.UUID, approved_only: bool = True):
        return pick_range(
            self.ranges.get(parameter_id, ()), self.sex, self.age_days, None, approved_only
        )


def load_sheet(db: Session, order_test_id: uuid.UUID, lock: bool = False) -> Sheet:
    query = select(OrderTest).where(OrderTest.id == order_test_id)
    ordered = db.scalar(query.with_for_update() if lock else query)
    if ordered is None:
        raise NotFoundError()
    visit = db.get_one(Visit, ordered.visit_id)
    name, sex, dob = db.execute(
        select(Patient.full_name, Patient.sex, Patient.dob).where(Patient.id == visit.patient_id)
    ).one()
    sample = db.get(Sample, ordered.sample_id) if ordered.sample_id else None
    taken = (sample.collected_at if sample else None) or visit.visited_at
    parameters = list(
        db.scalars(
            select(TestParameter)
            .where(TestParameter.test_id == ordered.test_id, TestParameter.is_active)
            .order_by(TestParameter.display_order, TestParameter.code)
        )
    )
    ids = [p.id for p in parameters]
    ranges: dict[uuid.UUID, list[ReferenceRange]] = {}
    for rng in db.scalars(select(ReferenceRange).where(ReferenceRange.parameter_id.in_(ids))):
        ranges.setdefault(rng.parameter_id, []).append(rng)
    results = {
        r.parameter_id: r
        for r in db.scalars(select(Result).where(Result.order_test_id == ordered.id))
    }
    return Sheet(
        ordered=ordered,
        test=db.get_one(Test, ordered.test_id),
        visit=visit,
        patient_name=name,
        sex=sex,
        dob=dob,
        age_days=max((taken.astimezone(IST).date() - dob).days, 0),
        parameters=parameters,
        ranges=ranges,
        results=results,
    )


def bands_of(db: Session, rng: ReferenceRange | None) -> list[ReferenceBand]:
    if rng is None:
        return []
    return list(
        db.scalars(
            select(ReferenceBand)
            .where(ReferenceBand.range_id == rng.id)
            .order_by(ReferenceBand.display_order)
        )
    )


# The previous value


@dataclass(frozen=True)
class Previous:
    value: str
    on: date
    # How far the new value has moved from this one, in whole per cent; None when either
    # isn't a number or this one is zero.
    change_pct: int | None = None


def previous_values(
    db: Session, patient_id: uuid.UUID, before: datetime, parameter_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[Result, datetime]]:
    """The patient's last signed-off result for each parameter from an earlier visit."""
    if not parameter_ids:
        return {}
    stmt = latest_per(
        select(Result, Visit.visited_at)
        .join(OrderTest, OrderTest.id == Result.order_test_id)
        .join(Visit, Visit.id == OrderTest.visit_id)
        .where(
            Visit.patient_id == patient_id,
            Visit.visited_at < before,
            OrderTest.status.in_(SIGNED_OFF),
            Result.parameter_id.in_(parameter_ids),
        ),
        Result.parameter_id,
    ).order_by(Result.parameter_id, Visit.visited_at.desc())
    return {result.parameter_id: (result, at) for result, at in db.execute(stmt)}


def _previous(found: tuple[Result, datetime] | None, now: Result | None, decimals: int):
    if found is None:
        return None
    old, at = found
    if old.value_num is None:
        return Previous(old.value_text, at.astimezone(IST).date()) if old.value_text else None
    change = None
    if now is not None and now.value_num is not None and old.value_num != 0:
        moved = (now.value_num - old.value_num) / old.value_num * 100
        change = int(moved.quantize(Decimal(1), ROUND_HALF_UP))
    return Previous(shown(old.value_num, decimals), at.astimezone(IST).date(), change)


# The grid's rows


@dataclass(frozen=True)
class GridRow:
    order_test_id: uuid.UUID
    parameter: TestParameter
    # What the cell holds: the saved value, or what was typed when it was refused.
    value: str
    row_version: int
    state: str
    badge: str
    band: str
    unit: str
    range: str
    range_unapproved: bool
    previous: Previous | None
    editable: bool
    error: str = ""
    # The typed value is outside the typo guard; it is saved only if confirmed.
    needs_confirm: bool = False
    result_id: uuid.UUID | None = None
    # A critical value nobody has been told about yet, and whether this user may log it.
    must_inform: bool = False
    can_inform: bool = False
    informed: CriticalNotification | None = None
    inform_error: str = ""

    @property
    def calculated(self) -> bool:
        return self.parameter.result_type == "calculated"


def _row(
    sheet: Sheet,
    parameter: TestParameter,
    editable: bool,
    previous: dict[uuid.UUID, tuple[Result, datetime]],
    told: dict[uuid.UUID, CriticalNotification],
) -> GridRow:
    result = sheet.results.get(parameter.id)
    value, state, badge, band = "", "empty", "", ""
    if result is not None and result.not_calculable:
        state = "not-calculable"
    elif result is not None and (result.value_num is not None or result.value_text):
        if result.value_num is not None:
            value = shown(result.value_num, parameter.decimals)
        else:
            value = result.value_text
        if result.flag is not None:
            state = state_of(result.flag, result.band_severity)
            band = result.band_label
            badge = f"⚠ {result.flag}" if state == "critical" else BADGES.get(state, "")
        else:
            state = "entered"
    unapproved = False
    if state != "empty" and result is not None:
        # The range the value was read against when it was saved, not today's.
        unit, limits = result.unit, result.ref_range_text
    else:
        # Nothing entered yet: show the range the value will be read against.
        rng = sheet.range_for(parameter.id)
        unit = parameter.unit_ucum
        limits = range_text(rng.low, rng.high, rng.display_text) if rng else ""
        unapproved = rng is None and sheet.range_for(parameter.id, False) is not None
    informed = told.get(result.id) if result is not None and state == "critical" else None
    return GridRow(
        order_test_id=sheet.ordered.id,
        parameter=parameter,
        value=value,
        row_version=result.row_version if result is not None else 0,
        state=state,
        badge=badge,
        band=band,
        unit=units.label(unit),
        range=limits,
        range_unapproved=unapproved,
        previous=_previous(previous.get(parameter.id), result, parameter.decimals),
        editable=editable and parameter.result_type != "calculated",
        result_id=result.id if result is not None else None,
        must_inform=state == "critical" and informed is None,
        can_inform=state == "critical" and informed is None and editable,
        informed=informed,
    )


def reported(result: Result, decimals: int) -> str:
    """A result's value as it is read out over the phone and kept in the critical log."""
    return shown(result.value_num, decimals) if result.value_num is not None else result.value_text


def told_about(db: Session, sheet: Sheet) -> dict[uuid.UUID, CriticalNotification]:
    """For each critical result of the test, the log entry that reports the value it has
    now. A value corrected after the call has to be reported again."""
    decimals = {p.id: p.decimals for p in sheet.parameters}
    critical = {
        r.id: r for r in sheet.results.values() if r.flag in CRITICAL and r.parameter_id in decimals
    }
    if not critical:
        return {}
    told: dict[uuid.UUID, CriticalNotification] = {}
    for note in db.scalars(
        select(CriticalNotification)
        .where(CriticalNotification.result_id.in_(critical))
        .order_by(CriticalNotification.recorded_at, CriticalNotification.id)
    ):
        result = critical[note.result_id]
        if (note.reported_value, note.reported_flag) == (
            reported(result, decimals[result.parameter_id]),
            result.flag,
        ):
            told[result.id] = note
    return told


def rows(db: Session, sheet: Sheet, editable: bool) -> list[GridRow]:
    """The test's rows in report order."""
    previous = previous_values(
        db, sheet.visit.patient_id, sheet.visit.visited_at, [p.id for p in sheet.parameters]
    )
    told = told_about(db, sheet)
    return [_row(sheet, p, editable, previous, told) for p in sheet.parameters]


# The worklist


def branches_in_view(db: Session, principal: Principal) -> dict[uuid.UUID, str]:
    """The branches whose tests the user's worklist can show, with their codes: the branch
    they work at, and every branch when that one is the main lab."""
    here = principal.branch_id
    if here is None or not principal.can("result.enter", here):
        raise PermissionDeniedError()
    branches = db.execute(
        select(Branch.id, Branch.code, Branch.kind).where(Branch.is_active).order_by(Branch.code)
    ).all()
    main = any(b.id == here and b.kind == "main_lab" for b in branches)
    return {b.id: b.code for b in branches if main or b.id == here}


@dataclass(frozen=True)
class WorkItem:
    order_test_id: uuid.UUID
    visit_id: uuid.UUID
    visit_no: str
    sample_no: str
    patient_name: str
    age: str
    sex: str
    test_code: str
    test_name: str
    department: str
    status: str
    route: str
    due_at: datetime
    from_branch: str
    done_at: str


def work_page(
    db: Session,
    principal: Principal,
    page: int = 1,
    *,
    department_id: uuid.UUID | None = None,
    status: str = "",
    branch_id: uuid.UUID | None = None,
) -> Page[WorkItem]:
    """The tests a branch performs, the most urgent first. Without a status, the work that
    is in the lab or on its way to it."""
    in_view = branches_in_view(db, principal)
    done_at = branch_id if branch_id in in_view else principal.branch_id
    if done_at is None:
        raise PermissionDeniedError()
    came_from = aliased(Branch)
    stmt = (
        select(
            OrderTest.id,
            OrderTest.visit_id,
            Visit.visit_no,
            Sample.sample_no,
            Patient.full_name,
            Patient.dob,
            Patient.sex,
            Test.code,
            Test.name,
            Department.name,
            OrderTest.status,
            OrderTest.route,
            OrderTest.due_at,
            came_from.code,
        )
        .join(Visit, Visit.id == OrderTest.visit_id)
        .join(Patient, Patient.id == Visit.patient_id)
        .join(Test, Test.id == OrderTest.test_id)
        .join(Department, Department.id == Test.department_id)
        .join(came_from, came_from.id == Visit.branch_id)
        .outerjoin(Sample, Sample.id == OrderTest.sample_id)
        .where(OrderTest.perform_branch_id == done_at)
        .where(OrderTest.status.in_((status,) if status in STATUSES else OPEN))
        .order_by(OrderTest.due_at, Visit.visit_no, Test.code, OrderTest.id)
    )
    if department_id is not None:
        stmt = stmt.where(Test.department_id == department_id)
    found = page_of(db, stmt, page)
    today = lab_today()
    code = in_view.get(done_at, "")
    items = [
        WorkItem(
            order_test_id=r[0],
            visit_id=r[1],
            visit_no=r[2],
            sample_no=r[3] or "",
            patient_name=r[4],
            age=age_text(r[5], today),
            sex=r[6],
            test_code=r[7],
            test_name=r[8],
            department=r[9],
            status=r[10],
            route=r[11],
            due_at=r[12],
            from_branch=r[13],
            done_at=code,
        )
        for r in found.items
    ]
    return Page(items, found.number, found.size, found.has_next)


def departments(db: Session) -> list[tuple[uuid.UUID, str]]:
    return [
        (d.id, d.name)
        for d in db.execute(
            select(Department.id, Department.name).order_by(
                Department.report_order, Department.name
            )
        )
    ]


# The critical-value log


@dataclass(frozen=True)
class CriticalEntry:
    """One critical value: with `note`, who was told; without, still to be told."""

    visit_id: uuid.UUID
    order_test_id: uuid.UUID
    visit_no: str
    patient_name: str
    age: str
    sex: str
    test_name: str
    parameter_name: str
    value: str
    flag: str
    unit: str
    note: CriticalNotification | None = None
    recorded_by: str = ""


_CRITICAL_COLUMNS = (
    OrderTest.visit_id,
    OrderTest.id,
    Visit.visit_no,
    Patient.full_name,
    Patient.dob,
    Patient.sex,
    Test.name,
    TestParameter.name,
    TestParameter.decimals,
    Result,
)


def _critical_from(
    stmt: Select[*tuple[Any, ...]], in_view: dict[uuid.UUID, str]
) -> Select[*tuple[Any, ...]]:
    return (
        stmt.join(OrderTest, OrderTest.id == Result.order_test_id)
        .join(Visit, Visit.id == OrderTest.visit_id)
        .join(Patient, Patient.id == Visit.patient_id)
        .join(Test, Test.id == OrderTest.test_id)
        .join(TestParameter, TestParameter.id == Result.parameter_id)
        .where(OrderTest.perform_branch_id.in_(in_view))
    )


def _critical_entry(
    row: Any,
    today: date,
    note: CriticalNotification | None = None,
    recorded_by: str = "",
) -> CriticalEntry:
    result: Result = row[9]
    return CriticalEntry(
        visit_id=row[0],
        order_test_id=row[1],
        visit_no=row[2],
        patient_name=row[3],
        age=age_text(row[4], today),
        sex=row[5],
        test_name=row[6],
        parameter_name=row[7],
        # The log keeps the value that was reported, even if it was corrected later.
        value=note.reported_value if note else reported(result, row[8]),
        flag=note.reported_flag if note else result.flag or "",
        unit=units.label(result.unit),
        note=note,
        recorded_by=recorded_by,
    )


def critical_waiting(db: Session, principal: Principal) -> list[CriticalEntry]:
    """Critical values on tests still at the bench that nobody is on record as told about."""
    in_view = branches_in_view(db, principal)
    found = db.execute(
        _critical_from(select(*_CRITICAL_COLUMNS).select_from(Result), in_view)
        .where(Result.flag.in_(CRITICAL), OrderTest.status.in_(EDITABLE), TestParameter.is_active)
        .order_by(Result.entered_at, Result.id)
        .limit(200)
    ).all()
    today = lab_today()
    waiting = []
    for row in found:
        result: Result = row[9]
        logged = db.scalar(
            select(
                exists().where(
                    CriticalNotification.result_id == result.id,
                    CriticalNotification.reported_value == reported(result, row[8]),
                    CriticalNotification.reported_flag == result.flag,
                )
            )
        )
        if not logged:
            waiting.append(_critical_entry(row, today))
    return waiting


def critical_log(db: Session, principal: Principal, page: int = 1) -> Page[CriticalEntry]:
    """Who was told about which critical value, newest first, for the branches in view."""
    in_view = branches_in_view(db, principal)
    stmt = (
        _critical_from(
            select(*_CRITICAL_COLUMNS, CriticalNotification, AppUser.full_name)
            .select_from(CriticalNotification)
            .join(Result, Result.id == CriticalNotification.result_id),
            in_view,
        )
        .join(AppUser, AppUser.id == CriticalNotification.recorded_by)
        .order_by(CriticalNotification.informed_at.desc(), CriticalNotification.id.desc())
    )
    found = page_of(db, stmt, page)
    today = lab_today()
    items = [_critical_entry(row, today, row[10], row[11]) for row in found.items]
    return Page(items, found.number, found.size, found.has_next)


# Where a test can be done


def has_sharing_consent(db: Session, patient_id: uuid.UUID) -> bool:
    """Whether the patient agreed, under the notice now in force, to their details going to
    an outside lab."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    Consent.subject_type == "patient",
                    Consent.subject_id == patient_id,
                    Consent.purpose == "referral_lab_sharing",
                    Consent.notice_id == current_notice(db).id,
                    Consent.withdrawn_at.is_(None),
                )
            )
        )
    )


def charged_for(db: Session, ordered: OrderTest) -> Decimal:
    """What the patient was charged for this test. A test ordered inside a package gets its
    share of the package's price, split by the list prices of the package's tests."""
    item = db.get_one(OrderItem, ordered.order_item_id)
    if item.item_type != "package":
        return item.net_price
    visit = db.get_one(Visit, ordered.visit_id)
    members = db.scalars(
        select(OrderTest)
        .where(OrderTest.order_item_id == item.id)
        .order_by(OrderTest.created_at, OrderTest.id)
    ).all()
    weights = [
        catalog.price_at(db, "test", m.test_id, visit.branch_id, visit.visited_at) or ZERO
        for m in members
    ]
    if sum(weights) < item.net_price:
        # Tests without a price of their own, or a package dearer than its parts.
        weights = [item.net_price or Decimal(1) for _ in members]
    shares = allocate(item.net_price, weights)
    return shares[[m.id for m in members].index(ordered.id)]


@dataclass(frozen=True)
class RouteChoice:
    """One place a test can be done, as the routing list offers it. Cost, margin and
    turnaround are known for outside labs only."""

    value: str
    name: str
    current: bool
    cost: Decimal | None = None
    margin: Decimal | None = None
    tat_hours: int | None = None


def can_route(principal: Principal, ordered: OrderTest, visit: Visit) -> bool:
    return principal.can("test.route", visit.branch_id) or principal.can(
        "test.route", ordered.perform_branch_id
    )


def route_choices(db: Session, principal: Principal, sheet: Sheet) -> list[RouteChoice]:
    return choices_for(db, principal, sheet.ordered, sheet.visit)


def choices_for(
    db: Session, principal: Principal, ordered: OrderTest, visit: Visit
) -> list[RouteChoice]:
    """Where the test can go from here: the main lab, the branch that took the sample, and
    each outside lab that has a rate for it, cheapest first. Empty when the test can't be
    moved any more or the user may not move it."""
    if ordered.status not in ROUTABLE or not can_route(principal, ordered, visit):
        return []
    in_house = ordered.route == "in_house"
    choices = []
    branches = dict.fromkeys(b for b in (main_lab_id(db), visit.branch_id) if b is not None)
    codes = dict(db.execute(select(Branch.id, Branch.code).where(Branch.id.in_(branches))).all())
    for branch_id in branches:
        choices.append(
            RouteChoice(
                value=f"branch:{branch_id}",
                name=f"In-house at {codes[branch_id]}",
                current=in_house and ordered.perform_branch_id == branch_id,
            )
        )
    if principal.can("extlab.view"):
        charged = charged_for(db, ordered)
        for quote in extlabs.quotes_for(db, principal, ordered.test_id):
            current = ordered.external_lab_id == quote.lab.id
            # A test already with this lab keeps the cost it was routed at.
            cost = ordered.external_cost if current and ordered.external_cost else quote.rate.cost
            choices.append(
                RouteChoice(
                    value=f"lab:{quote.lab.id}",
                    name=quote.lab.name,
                    current=current,
                    cost=cost,
                    margin=charged - cost,
                    tat_hours=quote.rate.tat_hours,
                )
            )
    return choices


def has_document(db: Session, order_test_id: uuid.UUID) -> bool:
    """Whether an outside lab's result PDF is attached to the test."""
    return bool(
        db.scalar(select(exists().where(ExternalDocumentTest.order_test_id == order_test_id)))
    )


# A visit on the grid


@dataclass(frozen=True)
class MethodChoice:
    id: uuid.UUID
    name: str
    is_default: bool


@dataclass(frozen=True)
class SampleNote:
    """The sample a test is read from and the remark printed above its panel."""

    id: uuid.UUID
    sample_no: str
    remarks: str
    row_version: int


@dataclass(frozen=True)
class TestBlock:
    """One test of the visit with its rows, what is still to look at before it goes for
    verification, and what this user may do with it."""

    __test__ = False

    order_test_id: uuid.UUID
    visit_id: uuid.UUID
    name: str
    status: str
    route: str
    row_version: int
    editable: bool
    rows: list[GridRow]
    can_submit: bool = False
    can_verify: bool = False
    can_reopen: bool = False
    choices: list[RouteChoice] = field(default_factory=list)
    lab_name: str = ""
    external_cost: Decimal | None = None
    margin: Decimal | None = None
    verified_by: str = ""
    error: str = ""
    accession_no: str = ""
    # Routed to an outside lab and its PDF isn't here yet, so nothing can be typed.
    awaiting_pdf: bool = False
    # The methods the report can name; `method_id` None prints the default one.
    methods: list[MethodChoice] = field(default_factory=list)
    method_id: uuid.UUID | None = None
    sample: SampleNote | None = None

    def count(self, *states: str) -> int:
        return sum(1 for r in self.rows if r.state in states)

    @property
    def missing(self) -> int:
        return sum(1 for r in self.rows if r.state == "empty" and not r.calculated)

    @property
    def to_inform(self) -> int:
        return sum(1 for r in self.rows if r.must_inform)


def test_block(db: Session, principal: Principal, sheet: Sheet) -> TestBlock:
    ordered = sheet.ordered
    enters = principal.can("result.enter", ordered.perform_branch_id)
    verifies = principal.can("result.verify", ordered.perform_branch_id)
    # Routed out but still here: its values come from the outside lab, once it has been.
    waiting_to_go = ordered.route == "external" and not has_document(db, ordered.id)
    can_type = ordered.status in EDITABLE and enters and not waiting_to_go
    lab_name, margin, verified_by = "", None, ""
    if ordered.external_lab_id is not None:
        lab_name = db.get_one(ExternalLab, ordered.external_lab_id).name
        if ordered.external_cost is not None and can_route(principal, ordered, sheet.visit):
            margin = charged_for(db, ordered) - ordered.external_cost
    if ordered.status in SIGNED_OFF:
        verified_by = (
            db.scalar(
                select(AppUser.full_name)
                .join(Verification, Verification.verified_by == AppUser.id)
                .where(Verification.order_test_id == ordered.id)
                .order_by(Verification.verified_at.desc(), Verification.id.desc())
                .limit(1)
            )
            or ""
        )
    methods = [
        MethodChoice(m.id, m.name, m.is_default)
        for m in db.scalars(
            select(TestMethod)
            .where(TestMethod.test_id == ordered.test_id, TestMethod.is_active)
            .order_by(TestMethod.is_default.desc(), TestMethod.name)
        )
    ]
    sample = db.get(Sample, ordered.sample_id) if ordered.sample_id else None
    return TestBlock(
        order_test_id=ordered.id,
        visit_id=ordered.visit_id,
        name=sheet.test.name,
        status=ordered.status,
        route=ordered.route,
        row_version=ordered.row_version,
        editable=can_type,
        rows=rows(db, sheet, can_type),
        can_submit=ordered.status == "in_lab" and enters and not waiting_to_go,
        can_verify=ordered.status == "resulted" and verifies,
        can_reopen=ordered.status == "verified" and verifies,
        choices=route_choices(db, principal, sheet),
        lab_name=lab_name,
        external_cost=ordered.external_cost if margin is not None else None,
        margin=margin,
        verified_by=verified_by,
        accession_no=ordered.external_accession_no,
        awaiting_pdf=waiting_to_go,
        methods=methods,
        method_id=ordered.method_id,
        sample=SampleNote(sample.id, sample.sample_no, sample.remarks, sample.row_version)
        if sample
        else None,
    )


@dataclass(frozen=True)
class VisitSheet:
    visit_id: uuid.UUID
    visit_no: str
    patient_name: str
    age: str
    sex: str
    blocks: list[TestBlock]
    # Tests of the visit that another branch does, as "name (branch code)".
    elsewhere: list[str]
    # The patient hasn't agreed to their details going to an outside lab.
    sharing_consent_missing: bool = False


def visit_sheet(db: Session, principal: Principal, visit_id: uuid.UUID) -> VisitSheet:
    """The visit's tests that the user's lab does, ready for the grid."""
    in_view = branches_in_view(db, principal)
    ordered = db.execute(
        select(OrderTest.id, OrderTest.perform_branch_id, Test.name, Branch.code)
        .join(Test, Test.id == OrderTest.test_id)
        .join(Branch, Branch.id == OrderTest.perform_branch_id)
        .where(OrderTest.visit_id == visit_id, OrderTest.status != "cancelled")
        .order_by(Test.name, OrderTest.id)
    ).all()
    here = [o for o in ordered if o.perform_branch_id in in_view]
    if not here:
        raise NotFoundError()
    sheets = [load_sheet(db, o.id) for o in here]
    first = sheets[0]
    return VisitSheet(
        visit_id=visit_id,
        visit_no=first.visit.visit_no,
        patient_name=first.patient_name,
        age=age_text(first.dob, lab_today()),
        sex=first.sex,
        blocks=[test_block(db, principal, sheet) for sheet in sheets],
        elsewhere=[f"{o.name} ({o.code})" for o in ordered if o.perform_branch_id not in in_view],
        sharing_consent_missing=not has_sharing_consent(db, first.visit.patient_id),
    )
