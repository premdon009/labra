"""A patient's history (design §8, M19): their visits, newest first, each with its tests and
its report versions, and the signed-off results of those visits side by side.

Scoped like the report screens: the visits of the user's branches, and visits with a test
performed at one of them.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, exists, or_, select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.catalog import units
from labra.catalog.models import Test, TestParameter
from labra.core.errors import NotFoundError
from labra.core.paging import Page, page_of
from labra.org.models import Branch
from labra.patients.models import Patient
from labra.reports.content import FLAGGED, NOT_CALCULABLE
from labra.reports.models import Report
from labra.results.models import Result
from labra.results.worklist import SIGNED_OFF, shown
from labra.visits.models import OrderTest, Visit

# Visits per page, and so the columns of the results table.
VISITS_PER_PAGE = 6


@dataclass(frozen=True)
class VisitLine:
    visit: Visit
    branch: str
    tests: list[tuple[str, str]]
    reports: list[Report]


@dataclass(frozen=True)
class Cell:
    value: str
    flag: str


@dataclass(frozen=True)
class Row:
    """One parameter across the page's visits, in the visits' order; None where the visit
    has no signed-off value for it."""

    test: str
    parameter: str
    unit: str
    cells: list[Cell | None]


@dataclass(frozen=True)
class History:
    patient: Patient
    visits: Page[VisitLine]
    rows: list[Row]


def _seen(principal: Principal) -> ColumnElement[bool]:
    branches = principal.branches_with("report.view")
    return or_(
        Visit.branch_id.in_(branches),
        exists().where(OrderTest.visit_id == Visit.id, OrderTest.perform_branch_id.in_(branches)),
    )


def _rows(db: Session, visits: Sequence[Visit]) -> list[Row]:
    column = {v.id: i for i, v in enumerate(visits)}
    found = db.execute(
        select(Result, TestParameter, Test.name, OrderTest.visit_id)
        .join(OrderTest, OrderTest.id == Result.order_test_id)
        .join(TestParameter, TestParameter.id == Result.parameter_id)
        .join(Test, Test.id == OrderTest.test_id)
        .where(
            OrderTest.visit_id.in_(column),
            OrderTest.status.in_(SIGNED_OFF),
            TestParameter.is_reportable,
        )
    ).all()
    rows: dict[tuple[str, int, str, str], list[Cell | None]] = {}
    for result, parameter, test, visit_id in found:
        if result.not_calculable:
            value = NOT_CALCULABLE
        elif result.value_num is not None:
            value = shown(result.value_num, parameter.decimals)
        elif result.value_text:
            value = result.value_text
        else:
            continue
        # A change of unit starts a row of its own, so values are never compared across units.
        key = (test, parameter.display_order, parameter.name, units.label(result.unit))
        cells = rows.setdefault(key, [None] * len(visits))
        cells[column[visit_id]] = Cell(value, result.flag if result.flag in FLAGGED else "")
    return [Row(test, name, unit, cells) for (test, _, name, unit), cells in sorted(rows.items())]


def history(db: Session, principal: Principal, patient_id: uuid.UUID, page: int) -> History:
    """Page `page` of the patient's visits the user may see, and their results."""
    patient = db.get(Patient, patient_id)
    branches = principal.branches_with("report.view")
    seen = select(Visit).where(Visit.patient_id == patient_id, _seen(principal))
    if patient is None or (
        patient.registered_branch_id not in branches and db.scalar(seen.limit(1)) is None
    ):
        raise NotFoundError()
    visits = page_of(db, seen.order_by(Visit.visited_at.desc(), Visit.id), page, VISITS_PER_PAGE)
    ids = [v.id for v in visits.items]
    names = dict(
        db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_({v.branch_id for v in visits.items}))
        ).all()
    )
    tests: dict[uuid.UUID, list[tuple[str, str]]] = {i: [] for i in ids}
    for visit_id, name, status in db.execute(
        select(OrderTest.visit_id, Test.name, OrderTest.status)
        .join(Test, Test.id == OrderTest.test_id)
        .where(OrderTest.visit_id.in_(ids))
        .order_by(Test.name)
    ):
        tests[visit_id].append((name, status))
    reports: dict[uuid.UUID, list[Report]] = {i: [] for i in ids}
    for report in db.scalars(
        select(Report).where(Report.visit_id.in_(ids)).order_by(Report.report_no, Report.version)
    ):
        reports[report.visit_id].append(report)
    lines = [
        VisitLine(v, names.get(v.branch_id, ""), tests[v.id], reports[v.id]) for v in visits.items
    ]
    return History(
        patient,
        Page(lines, visits.number, visits.size, visits.has_next),
        _rows(db, visits.items),
    )
