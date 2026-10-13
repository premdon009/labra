"""Entering results: the range each value is read against, calculated rows, the typo guard
and the previous value."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.catalog import service as catalog
from labra.catalog.models import ReferenceRange, Test, TestParameter
from labra.core.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.results import entry, service, worklist
from labra.results.models import Result
from labra.seed import seed
from labra.visits import service as visits
from labra.visits.models import OrderTest, Sample
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, branch, patient_input, post, sign_in


@pytest.fixture
def lab(db: Session, platform: Platform) -> Session:
    """The demo cast with the starter catalog, the lipid ranges approved."""
    seed(db, platform.identity, SEED_DAY, with_catalog=True)
    _approve(db, platform, "lipid")
    return db


def _test_id(db: Session, code: str) -> uuid.UUID:
    return db.scalars(select(Test.id).where(Test.code == code)).one()


def _param(db: Session, test: str, code: str) -> TestParameter:
    return db.scalars(
        select(TestParameter).where(
            TestParameter.test_id == _test_id(db, test), TestParameter.code == code
        )
    ).one()


def _range(db: Session, test: str, code: str) -> ReferenceRange:
    """The parameter's range for an adult woman, which the synthetic patient is."""
    ranges = db.scalars(
        select(ReferenceRange).where(ReferenceRange.parameter_id == _param(db, test, code).id)
    )
    return next(r for r in ranges if r.sex in (None, "F") and r.age_max_days > 34 * 366)


def _approve(db: Session, platform: Platform, test: str) -> None:
    meera = as_user(db, platform, "meera")
    ranges = db.scalars(
        select(ReferenceRange)
        .join(TestParameter, TestParameter.id == ReferenceRange.parameter_id)
        .where(TestParameter.test_id == _test_id(db, test))
    ).all()
    for rng in ranges:
        catalog.approve_range(db, meera, rng.id, rng.row_version)


def _in_lab(
    db: Session, platform: Platform, code: str = "lipid", patient_id: uuid.UUID | None = None
) -> OrderTest:
    """A test ordered at Branch 2, collected there and received at the main lab."""
    priya = as_user(db, platform, "priya")
    data = visits.VisitInput(
        client_ref=uuid.uuid4(),
        patient_id=patient_id,
        patient=None if patient_id else patient_input(phone=f"90000{uuid.uuid4().int % 10**5:05d}"),
        consent=True,
        items=[("test", _test_id(db, code))],
    )
    visit = visits.save_visit(db, priya, data, SEED_DAY)
    sample = db.scalars(select(Sample).where(Sample.visit_id == visit.id)).one()
    visits.collect_sample(db, priya, sample.sample_no, priya.user_id)
    service.receive_sample(db, as_user(db, platform, "suresh"), sample.sample_no)
    return db.scalars(select(OrderTest).where(OrderTest.visit_id == visit.id)).one()


def _enter(db: Session, platform: Platform, ordered: OrderTest, test: str = "lipid", **values):
    """Type each value into its row as the technician; the last save's outcome."""
    suresh = as_user(db, platform, "suresh")
    saved = None
    for code, raw in values.items():
        parameter = _param(db, test, code)
        current = db.scalar(
            select(Result.row_version).where(
                Result.order_test_id == ordered.id, Result.parameter_id == parameter.id
            )
        )
        saved = entry.save_value(db, suresh, ordered.id, parameter.id, str(raw), current or 0)
    assert saved is not None
    return saved


def _result(db: Session, ordered: OrderTest, code: str, test: str = "lipid") -> Result | None:
    return db.scalar(
        select(Result).where(
            Result.order_test_id == ordered.id, Result.parameter_id == _param(db, test, code).id
        )
    )


def _grid(db: Session, ordered: OrderTest) -> dict[str, worklist.GridRow]:
    db.flush()
    rows = worklist.rows(db, worklist.load_sheet(db, ordered.id), True)
    return {row.parameter.code: row for row in rows}


def _problem(call) -> str:
    with pytest.raises(ValidationFailedError) as refused:
        call()
    return " ".join(refused.value.errors.values())


@pytest.mark.item("M11")
def test_a_value_keeps_the_range_it_was_read_against(lab: Session, platform: Platform) -> None:
    ordered = _in_lab(lab, platform)
    rng = _range(lab, "lipid", "TC")
    before = _grid(lab, ordered)["TC"]
    assert (before.state, before.value, before.range, before.unit) == (
        "empty",
        "",
        worklist.range_text(rng.low, rng.high, rng.display_text),
        "mg/dL",
    )

    saved = _enter(lab, platform, ordered, TC="250").result

    suresh = as_user(lab, platform, "suresh")
    assert (saved.value_num, saved.flag, saved.band_label, saved.unit) == (
        Decimal(250),
        "H",
        "High",
        "mg/dL",
    )
    assert (saved.ref_low, saved.ref_high, saved.ref_range_text) == (
        rng.low,
        Decimal(199),
        before.range,
    )
    assert (saved.source, saved.entered_by, saved.absurd_confirmed) == (
        "manual",
        suresh.user_id,
        False,
    )

    # The lab later moves the range; the value already entered still reads as it did.
    rng.high = Decimal(300)
    rng.display_text = "Up to 300"
    lab.flush()
    lab.expire_all()
    after = _grid(lab, ordered)["TC"]
    assert (after.value, after.state, after.badge, after.band, after.range) == (
        "250",
        "high",
        "↑ H",
        "High",
        before.range,
    )
    kept = _result(lab, ordered, "TC")
    assert kept is not None
    assert (kept.flag, kept.ref_high) == ("H", Decimal(199))
    # A fresh test of the same kind is read against the new range.
    assert _grid(lab, _in_lab(lab, platform))["TC"].range == "Up to 300"


@pytest.mark.item("M11")
def test_a_range_that_isnt_approved_gives_no_flag(db: Session, platform: Platform) -> None:
    seed(db, platform.identity, SEED_DAY, with_catalog=True)
    ordered = _in_lab(db, platform)
    assert _grid(db, ordered)["TC"].range_unapproved

    saved = _enter(db, platform, ordered, TC="250").result

    assert (saved.flag, saved.ref_high, saved.ref_range_text) == (None, None, "")
    row = _grid(db, ordered)["TC"]
    assert (row.value, row.state, row.badge, row.range) == ("250", "entered", "", "")


@pytest.mark.item("M11.2")
@pytest.mark.parametrize(
    ("tg", "ldl", "vldl", "not_calculable"),
    [
        ("399", Decimal(70), Decimal(80), False),
        ("400", None, None, True),
        ("401", None, None, True),
    ],
)
def test_friedewald_stops_at_a_triglyceride_of_400(
    lab: Session, platform: Platform, tg: str, ldl, vldl, not_calculable: bool
) -> None:
    ordered = _in_lab(lab, platform)

    first = _enter(lab, platform, ordered, TC="200", HDL="50")
    # Rows that still miss an input are left blank, not marked.
    assert {r.parameter_id for r in first.calculated} == {
        _param(lab, "lipid", code).id for code in ("NONHDL", "TC_HDL")
    }
    saved = _enter(lab, platform, ordered, TG=tg)

    assert len(saved.calculated) == 5
    for code, value in (("LDL", ldl), ("VLDL", vldl)):
        result = _result(lab, ordered, code)
        assert result is not None
        assert (result.value_num, result.not_calculable, result.source) == (
            value,
            not_calculable,
            "calculated",
        )
    non_hdl = _result(lab, ordered, "NONHDL")
    ratio = _result(lab, ordered, "TC_HDL")
    assert non_hdl is not None and ratio is not None
    assert (non_hdl.value_num, non_hdl.not_calculable) == (Decimal(150), False)
    assert (ratio.value_num, ratio.not_calculable) == (Decimal("4.0"), False)
    # A ratio built on a row that can't be calculated can't be calculated either.
    on_ldl = _result(lab, ordered, "LDL_HDL")
    assert on_ldl is not None
    assert (on_ldl.value_num, on_ldl.not_calculable) == (
        None if not_calculable else Decimal("1.4"),
        not_calculable,
    )
    grid = _grid(lab, ordered)
    assert grid["LDL"].state == ("not-calculable" if not_calculable else "normal")
    assert grid["LDL"].value == ("" if not_calculable else "70")
    assert not grid["LDL"].editable
    assert grid["TC_HDL"].value == "4.0"


@pytest.mark.item("M11.2")
def test_calculated_rows_follow_every_change(lab: Session, platform: Platform) -> None:
    ordered = _in_lab(lab, platform)
    _enter(lab, platform, ordered, TC="200", HDL="50", TG="450")
    ldl = _result(lab, ordered, "LDL")
    assert ldl is not None and ldl.not_calculable

    _enter(lab, platform, ordered, TG="150")
    assert (ldl.value_num, ldl.not_calculable, ldl.flag) == (Decimal(120), False, "H")
    assert ldl.ref_high == Decimal(99)

    # Clearing an input empties what was worked out from it.
    _enter(lab, platform, ordered, TG="")
    assert (ldl.value_num, ldl.not_calculable, ldl.flag) == (None, False, None)
    assert _grid(lab, ordered)["LDL"].state == "empty"
    tg = _result(lab, ordered, "TG")
    assert tg is not None and tg.value_num is None

    # A calculated row can't be typed.
    suresh = as_user(lab, platform, "suresh")
    assert "calculated" in _problem(
        lambda: entry.save_value(
            lab, suresh, ordered.id, _param(lab, "lipid", "LDL").id, "90", ldl.row_version
        )
    )


@pytest.mark.item("M11")
def test_an_absurd_value_is_refused_then_saved_on_a_confirm(
    lab: Session, platform: Platform
) -> None:
    ordered = _in_lab(lab, platform)
    suresh = as_user(lab, platform, "suresh")
    tc = _param(lab, "lipid", "TC")

    with pytest.raises(entry.AbsurdValueError) as refused:
        entry.save_value(lab, suresh, ordered.id, tc.id, "2500")
    assert "Check value: 2500" in refused.value.errors["value"]
    lab.flush()
    assert _result(lab, ordered, "TC") is None

    saved = entry.save_value(lab, suresh, ordered.id, tc.id, "2500", confirm_absurd=True).result

    assert (saved.value_num, saved.absurd_confirmed, saved.flag) == (Decimal(2500), True, "H")
    logged = lab.scalars(select(AuditLog).where(AuditLog.action.like("result.%"))).one()
    assert (logged.action, logged.entity_id, logged.user_id) == (
        "result.absurd_confirm",
        str(saved.id),
        suresh.user_id,
    )
    assert logged.detail == {
        "order_test_id": str(ordered.id),
        "visit_id": str(ordered.visit_id),
        "parameter": "TC",
        "value": "2500",
    }
    assert logged.branch_id == branch(lab, "MAIN").id

    # Corrected to a believable value, the mark goes; the confirm stays in the audit trail.
    fixed = entry.save_value(lab, suresh, ordered.id, tc.id, "250", saved.row_version).result
    assert (fixed.value_num, fixed.absurd_confirmed) == (Decimal(250), False)
    # A confirm sent with a believable value confirms nothing.
    again = entry.save_value(
        lab, suresh, ordered.id, tc.id, "251", fixed.row_version, confirm_absurd=True
    ).result
    assert not again.absurd_confirmed
    assert (
        lab.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action.like("result.%"))
        )
        == 1
    )


@pytest.mark.item("M11")
def test_the_typo_guard_works_before_the_range_is_approved(db: Session, platform: Platform) -> None:
    seed(db, platform.identity, SEED_DAY, with_catalog=True)
    ordered = _in_lab(db, platform)
    suresh = as_user(db, platform, "suresh")

    with pytest.raises(entry.AbsurdValueError):
        entry.save_value(db, suresh, ordered.id, _param(db, "lipid", "TC").id, "5")


@pytest.mark.item("M11")
def test_saving_values_writes_no_audit_rows(lab: Session, platform: Platform) -> None:
    # Signing in is audited, and the helpers sign in; everything else is counted.
    logged = select(func.count()).select_from(AuditLog).where(AuditLog.action != "auth.login")
    before = lab.scalar(logged)
    ordered = _in_lab(lab, platform)
    in_lab = lab.scalar(logged)
    assert in_lab is not None and before is not None and in_lab > before

    _enter(lab, platform, ordered, TC="200", HDL="50", TG="150")
    _enter(lab, platform, ordered, TC="210", TG="")

    assert lab.scalar(logged) == in_lab
    assert lab.scalar(select(func.count()).select_from(Result)) == 8


@pytest.mark.item("M11")
def test_what_can_be_typed_into_a_cell(lab: Session, platform: Platform) -> None:
    _approve(lab, platform, "urine")
    ordered = _in_lab(lab, platform)
    suresh = as_user(lab, platform, "suresh")
    tc, ratio = _param(lab, "lipid", "TC"), _param(lab, "lipid", "HDL")

    def typed(raw: str) -> str:
        return _problem(lambda: entry.save_value(lab, suresh, ordered.id, tc.id, raw))

    assert typed("abc") == "Enter a number."
    assert typed("NaN") == "Enter a number."
    assert typed("1e3") == "Enter a number."
    assert typed("12.5") == "Enter a whole number."
    assert "row any more" in _problem(
        lambda: entry.save_value(lab, suresh, ordered.id, _param(lab, "urine", "UPROT").id, "Nil")
    )
    saved = entry.save_value(lab, suresh, ordered.id, tc.id, " 1,80 ").result
    assert saved.value_num == Decimal(180)
    assert (saved.flag, saved.band_label) == ("N", "Desirable")
    assert entry.save_value(lab, suresh, ordered.id, ratio.id, "45.0").result.value_num == 45

    urine = _in_lab(lab, platform, "urine")
    protein = _param(lab, "urine", "UPROT")
    assert "listed values" in _problem(
        lambda: entry.save_value(lab, suresh, urine.id, protein.id, "Lots")
    )
    grade = entry.save_value(lab, suresh, urine.id, protein.id, "trace").result
    assert (grade.value_text, grade.value_num, grade.flag) == ("Trace", None, "A")
    nil = entry.save_value(lab, suresh, urine.id, protein.id, "Nil", grade.row_version).result
    assert (nil.value_text, nil.flag) == ("Nil", "N")


@pytest.mark.item("M11")
def test_who_can_enter_a_value_and_when(lab: Session, platform: Platform) -> None:
    ordered = _in_lab(lab, platform)
    suresh = as_user(lab, platform, "suresh")
    tc = _param(lab, "lipid", "TC")

    for username in ("priya", "anil"):
        with pytest.raises(PermissionDeniedError):
            entry.save_value(lab, as_user(lab, platform, username), ordered.id, tc.id, "200")

    # A test kept at a collection centre is entered there, not at the main lab.
    anil = as_user(lab, platform, "anil")
    kept = service.route_test(
        lab, anil, ordered.id, ordered.row_version, branch_id=branch(lab, "B2").id
    )
    with pytest.raises(PermissionDeniedError):
        entry.save_value(lab, suresh, kept.id, tc.id, "200")
    service.route_test(lab, anil, kept.id, kept.row_version, branch_id=branch(lab, "MAIN").id)
    lab.refresh(ordered)

    for status in ("ordered", "collected", "sent_out", "verified", "released", "cancelled"):
        ordered.status = status
        lab.flush()
        with pytest.raises(ConflictError):
            entry.save_value(lab, suresh, ordered.id, tc.id, "200")
    ordered.status = "resulted"
    lab.flush()
    saved = entry.save_value(lab, suresh, ordered.id, tc.id, "200").result

    # Someone else changed the cell since this screen loaded it.
    with pytest.raises(ConflictError):
        entry.save_value(lab, suresh, ordered.id, tc.id, "210", saved.row_version + 1)
    with pytest.raises(ConflictError):
        entry.save_value(lab, suresh, ordered.id, _param(lab, "lipid", "HDL").id, "50", 3)
    assert saved.value_num == Decimal(200)


@pytest.mark.item("M11")
def test_the_previous_value_and_how_far_the_new_one_moved(lab: Session, platform: Platform) -> None:
    earlier = _in_lab(lab, platform)
    _enter(lab, platform, earlier, TC="200", HDL="50")
    visit = lab.get_one(visits.Visit, earlier.visit_id)
    visit.visited_at -= timedelta(days=30)
    lab.flush()

    now = _in_lab(lab, platform, patient_id=visit.patient_id)
    # A value nobody has signed off isn't shown as the patient's previous one.
    assert _grid(lab, now)["TC"].previous is None

    earlier.status = "verified"
    grid = _grid(lab, now)
    assert grid["TC"].previous == worklist.Previous(
        "200", (visit.visited_at + timedelta(hours=5, minutes=30)).date()
    )
    assert grid["TG"].previous is None

    _enter(lab, platform, now, TC="210", HDL="44")
    grid = _grid(lab, now)
    assert grid["TC"].previous is not None and grid["TC"].previous.change_pct == 5
    assert grid["HDL"].previous is not None and grid["HDL"].previous.change_pct == -12
    assert grid["NONHDL"].previous is not None and grid["NONHDL"].previous.value == "150"
    # Another patient's test of the same kind has no previous value.
    assert _grid(lab, _in_lab(lab, platform))["TC"].previous is None
    # And the earlier visit doesn't see the later one.
    assert _grid(lab, earlier)["TC"].previous is None


def _cell(client: TestClient, ordered: OrderTest, parameter: TestParameter, **form: object):
    return post(client, f"/lab/tests/{ordered.id}/cells/{parameter.id}", form)


@pytest.mark.item("M11")
def test_the_cell_endpoint_shows_each_state(
    lab: Session, platform: Platform, db_client: TestClient
) -> None:
    _approve(lab, platform, "urine")
    _range(lab, "lipid", "TG").critical_high = Decimal(500)
    ordered = _in_lab(lab, platform)
    row_id = f'id="r-{ordered.id}-'
    sign_in(db_client, "suresh")

    def cell(code: str, value: str, version: int = 0, **more: object):
        parameter = _param(lab, "lipid", code)
        got = _cell(db_client, ordered, parameter, value=value, row_version=version, **more)
        own = got.text.split("<tr ")[1]
        assert own.startswith(f'{row_id}{parameter.id}"')
        return got, own

    got, own = cell("TC", "180")
    assert got.status_code == 200
    assert 'class="result-row flag-normal"' in own and "✓" in own and "Desirable" in own
    assert 'value="180"' in own and '"row_version": 1' in own
    assert "hx-swap-oob" not in own
    # The calculated rows come along, each swapped into its own place.
    assert got.text.count('hx-swap-oob="true"') == 6

    _, own = cell("TC", "250", 1)
    assert "flag-high" in own and "↑ H" in own and "High" in own
    _, own = cell("HDL", "30")
    assert "flag-low" in own and "↓ L" in own
    got, own = cell("TG", "600")
    assert "flag-critical" in own and "⚠ HH" in own
    ldl = got.text.split(f"{row_id}{_param(lab, 'lipid', 'LDL').id}")[1].split("</tr>")[0]
    assert "flag-not-calculable" in ldl and "Not calculable, measure directly" in ldl
    assert "<input" not in ldl

    # A refused value stays in its box with the reason, and nothing else is swapped.
    got, own = cell("TC", "abc", 2)
    assert got.status_code == 422
    assert 'value="abc"' in own and "Enter a number." in own and 'aria-invalid="true"' in own
    assert "hx-swap-oob" not in got.text and "anyway" not in own
    got, own = cell("TC", "2500", 2)
    assert got.status_code == 422
    assert "Check value: 2500" in own and "Save 2500 anyway" in own
    assert '"confirm": "1"' in own
    got, own = cell("TC", "2500", 2, confirm="1")
    assert got.status_code == 200 and 'value="2500"' in own and "anyway" not in own

    # Out of date, signed in without the permission, or not a record at all.
    assert cell_status(db_client, ordered, _param(lab, "lipid", "TC"), 2) == 409
    assert db_client.post(f"/lab/tests/{ordered.id}/cells/{uuid.uuid4()}").status_code == 403
    assert _cell(db_client, ordered, _param(lab, "urine", "UPROT"), value="Nil").status_code == 422
    missing = post(db_client, f"/lab/tests/{uuid.uuid4()}/cells/{uuid.uuid4()}", {"value": "1"})
    assert missing.status_code == 404
    assert post(db_client, "/lab/tests/x/cells/y", {"value": "1"}).status_code == 404

    urine = _in_lab(lab, platform, "urine")
    protein = _param(lab, "urine", "UPROT")
    got = _cell(db_client, urine, protein, value="Trace", row_version=0)
    assert "flag-abnormal" in got.text and '<option value="Trace" selected>' in got.text
    assert "<select" in got.text and ">A</span>" in got.text

    for username in ("priya", "anil"):
        sign_in(db_client, username)
        assert cell_status(db_client, ordered, _param(lab, "lipid", "TC"), 3) == 403


def cell_status(client: TestClient, ordered: OrderTest, parameter: TestParameter, version: int):
    return _cell(client, ordered, parameter, value="190", row_version=version).status_code
