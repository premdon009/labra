"""What the lab reads: the worklist, a visit's tests as the grid shows them, and each row's
previous value.

Nothing here writes. The patient is carried as name, sex and date of birth only: no phone,
no address.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, aliased

from labra.auth.principal import Principal
from labra.catalog import units
from labra.catalog.models import Department, ReferenceBand, ReferenceRange, Test, TestParameter
from labra.core.errors import NotFoundError, PermissionDeniedError
from labra.core.ids import IST, lab_today
from labra.core.paging import Page, page_of
from labra.org.models import Branch
from labra.patients.age import age_text
from labra.patients.models import Patient
from labra.results.flags import pick_range, state_of
from labra.results.models import Result
from labra.visits.models import OrderTest, Sample, Visit

# Values can be typed and changed until a signatory verifies the test.
EDITABLE = ("in_lab", "resulted")
# What the worklist shows when no status is picked: work that is here or on its way.
OPEN = ("collected", "in_lab", "resulted")
STATUSES = ("collected", "in_lab", "resulted", "sent_out", "verified", "released")
# A result counts as a patient's previous value once a signatory has stood behind it.
SIGNED_OFF = ("verified", "released")
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
    stmt = (
        select(Result, Visit.visited_at)
        .join(OrderTest, OrderTest.id == Result.order_test_id)
        .join(Visit, Visit.id == OrderTest.visit_id)
        .where(
            Visit.patient_id == patient_id,
            Visit.visited_at < before,
            OrderTest.status.in_(SIGNED_OFF),
            Result.parameter_id.in_(parameter_ids),
        )
        .ext(distinct_on(Result.parameter_id))
        .order_by(Result.parameter_id, Visit.visited_at.desc())
    )
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

    @property
    def calculated(self) -> bool:
        return self.parameter.result_type == "calculated"


def _row(
    sheet: Sheet,
    parameter: TestParameter,
    editable: bool,
    previous: dict[uuid.UUID, tuple[Result, datetime]],
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
    )


def rows(db: Session, sheet: Sheet, editable: bool) -> list[GridRow]:
    """The test's rows in report order."""
    previous = previous_values(
        db, sheet.visit.patient_id, sheet.visit.visited_at, [p.id for p in sheet.parameters]
    )
    return [_row(sheet, p, editable, previous) for p in sheet.parameters]


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


# A visit on the grid


@dataclass(frozen=True)
class TestBlock:
    """One test of the visit with its rows, and what is still to look at before it goes
    for verification."""

    __test__ = False

    order_test_id: uuid.UUID
    name: str
    status: str
    route: str
    editable: bool
    rows: list[GridRow]

    def count(self, *states: str) -> int:
        return sum(1 for r in self.rows if r.state in states)

    @property
    def missing(self) -> int:
        return sum(1 for r in self.rows if r.state == "empty" and not r.calculated)


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
    blocks = []
    sheet = load_sheet(db, here[0].id)
    for o in here:
        sheet = load_sheet(db, o.id) if o.id != sheet.ordered.id else sheet
        can_type = sheet.ordered.status in EDITABLE and principal.can(
            "result.enter", o.perform_branch_id
        )
        blocks.append(
            TestBlock(
                order_test_id=o.id,
                name=o.name,
                status=sheet.ordered.status,
                route=sheet.ordered.route,
                editable=can_type,
                rows=rows(db, sheet, can_type),
            )
        )
    return VisitSheet(
        visit_id=visit_id,
        visit_no=sheet.visit.visit_no,
        patient_name=sheet.patient_name,
        age=age_text(sheet.dob, lab_today()),
        sex=sheet.sex,
        blocks=blocks,
        elsewhere=[f"{o.name} ({o.code})" for o in ordered if o.perform_branch_id not in in_view],
    )
