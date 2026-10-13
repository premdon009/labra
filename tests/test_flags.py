"""Reading a result against its range: the range picked, the flag, the tier, the colour."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labra.catalog import formula
from labra.catalog.models import ReferenceBand, ReferenceRange
from labra.results.flags import (
    Flagged,
    band_for,
    compute_flag,
    is_absurd,
    pick_range,
    state_of,
)

APPROVED = datetime(2026, 1, 1, tzinfo=UTC)
ADULT = 18 * 365


def D(text: str | int | None) -> Decimal | None:  # noqa: N802  reads as a literal in tables
    return None if text is None else Decimal(str(text))


def rng(
    low: int | str | None = None,
    high: int | str | None = None,
    *,
    crit: tuple[int | None, int | None] = (None, None),
    absurd: tuple[int | None, int | None] = (None, None),
    sex: str | None = None,
    ages: tuple[int, int] = (0, 54750),
    condition: str | None = None,
    approved: bool = True,
    active: bool = True,
) -> ReferenceRange:
    return ReferenceRange(
        id=uuid.uuid4(),
        low=D(low),
        high=D(high),
        critical_low=D(crit[0]),
        critical_high=D(crit[1]),
        absurd_low=D(absurd[0]),
        absurd_high=D(absurd[1]),
        sex=sex,
        age_min_days=ages[0],
        age_max_days=ages[1],
        condition=condition,
        approved_at=APPROVED if approved else None,
        is_active=active,
    )


def band(low: int | None, high: int | None, label: str, severity: str) -> ReferenceBand:
    return ReferenceBand(low=D(low), high=D(high), label=label, severity=severity)


CHOLESTEROL = [
    band(None, 199, "Desirable", "normal"),
    band(200, 239, "Borderline high", "borderline"),
    band(240, None, "High", "abnormal"),
]
GRADES = [
    {"value": "Nil", "abnormal": False, "default": True},
    {"value": "Trace", "abnormal": True},
]


@pytest.mark.item("M11.1")
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("29", "LL"),
        ("30", "LL"),
        ("31", "L"),
        ("69", "L"),
        ("69.9", "L"),
        ("70", "N"),
        ("99", "N"),
        ("99.1", "H"),
        ("100", "H"),
        ("449", "H"),
        ("450", "HH"),
        ("900", "HH"),
    ],
)
def test_flag_at_each_limit_of_a_two_sided_range(value: str | None, expected: str | None) -> None:
    glucose = rng(70, 99, crit=(30, 450))
    assert compute_flag(D(value), glucose).flag == expected


@pytest.mark.item("M11.1")
@pytest.mark.parametrize(
    ("low", "high", "value", "expected"),
    [
        (40, None, "39", "L"),
        (40, None, "40", "N"),
        (40, None, "95", "N"),
        (None, 149, "149", "N"),
        (None, 149, "150", "H"),
        (None, 149, "0", "N"),
        (None, None, "12", "N"),
    ],
)
def test_a_one_sided_range_checks_only_its_own_side(
    low: int | None, high: int | None, value: str, expected: str
) -> None:
    assert compute_flag(D(value), rng(low, high)).flag == expected


@pytest.mark.item("M11.1")
def test_no_range_means_no_flag_and_free_text_is_never_flagged() -> None:
    assert compute_flag(D("12"), None) == Flagged()
    assert compute_flag("clear", None) == Flagged()
    assert compute_flag("  ", None, options=GRADES) == Flagged()
    assert compute_flag("Plenty", None, options=GRADES) == Flagged()


@pytest.mark.item("M11.1")
def test_an_option_is_abnormal_only_when_the_catalog_says_so() -> None:
    assert compute_flag("Nil", None, options=GRADES).flag == "N"
    assert compute_flag(" Trace ", None, options=GRADES).flag == "A"
    assert compute_flag("Trace", None, options=GRADES).state == "abnormal"


@pytest.mark.item("M11.1")
@pytest.mark.parametrize(
    ("value", "flag", "label", "state"),
    [
        ("150", "N", "Desirable", "normal"),
        ("199", "N", "Desirable", "normal"),
        ("199.5", "H", "Desirable", "high"),
        ("200", "H", "Borderline high", "high"),
        ("239", "H", "Borderline high", "high"),
        ("240", "H", "High", "high"),
        ("600", "H", "High", "high"),
    ],
)
def test_the_tier_label_rides_beside_the_flag(
    value: str, flag: str, label: str, state: str
) -> None:
    got = compute_flag(D(value), rng(None, 199), CHOLESTEROL)
    assert (got.flag, got.band_label, got.state) == (flag, label, state)


@pytest.mark.item("M11.1")
def test_amber_only_inside_the_range_with_a_borderline_tier() -> None:
    wide = rng(None, 239)
    inside = compute_flag(D("210"), wide, CHOLESTEROL)
    assert (inside.flag, inside.band_label, inside.state) == ("N", "Borderline high", "borderline")
    outside = compute_flag(D("210"), rng(None, 199), CHOLESTEROL)
    assert (outside.flag, outside.state) == ("H", "high")
    assert state_of("N", "abnormal") == "normal"
    assert state_of(None, "borderline") == "empty"
    assert state_of("LL", "borderline") == state_of("HH", None) == "critical"
    assert state_of("L", "borderline") == "low"


@pytest.mark.item("M11.1")
def test_a_value_outside_every_tier_has_none() -> None:
    tiers = [band(70, 99, "Normal", "normal"), band(100, 125, "Prediabetes", "borderline")]
    assert band_for(Decimal(60), tiers) is None
    assert band_for(Decimal(130), tiers) is None
    found = band_for(Decimal("99.5"), tiers)
    assert found is not None and found.label == "Normal"
    assert band_for(Decimal(5), []) is None


@pytest.mark.item("M11.2")
@pytest.mark.parametrize(
    ("value", "absurd"),
    [("9", True), ("10", False), ("1500", False), ("1501", True), ("1320", False)],
)
def test_absurd_limits_are_a_typo_guard_outside_the_limits_only(value: str, absurd: bool) -> None:
    glucose = rng(70, 99, absurd=(10, 1500))
    assert is_absurd(Decimal(value), glucose) is absurd


@pytest.mark.item("M11.2")
def test_no_absurd_limits_means_nothing_is_absurd() -> None:
    assert not is_absurd(Decimal(10**6), rng(70, 99))
    assert not is_absurd(Decimal(10**6), None)
    assert is_absurd(Decimal(-1), rng(absurd=(0, None)))
    assert not is_absurd(Decimal(10**6), rng(absurd=(0, None)))


@pytest.mark.item("M11.2")
@pytest.mark.parametrize(("tg", "calculable"), [(399, True), (400, False), (401, False)])
def test_friedewald_is_refused_from_triglycerides_400(tg: int, calculable: bool) -> None:
    values = {"TC": Decimal(215), "HDL": Decimal(38), "TG": Decimal(tg)}
    assert formula.holds("TG < 400", values) is calculable
    if calculable:
        assert formula.evaluate("TC - HDL - TG / 5", values) == Decimal("97.2")


@pytest.mark.item("M11.1")
def test_pick_range_by_sex_and_age_in_days() -> None:
    newborn = rng(14, 22, ages=(0, 28))
    child = rng(11, 14, ages=(28, ADULT))
    man = rng(13, 17, sex="M", ages=(ADULT, 54750))
    woman = rng(12, 15, sex="F", ages=(ADULT, 54750))
    anyone = rng(12, 17, ages=(ADULT, 54750))
    ranges = [newborn, child, anyone, man, woman]
    assert pick_range(ranges, "M", 27) is newborn
    assert pick_range(ranges, "M", 28) is child
    assert pick_range(ranges, "F", ADULT - 1) is child
    assert pick_range(ranges, "F", ADULT) is woman
    assert pick_range(ranges, "M", 58 * 365) is man
    assert pick_range(ranges, "O", 58 * 365) is anyone
    assert pick_range(ranges, None, 58 * 365) is anyone
    assert pick_range(ranges, "M", 54750) is None
    assert pick_range([man], "F", 58 * 365) is None


@pytest.mark.item("M11.1")
def test_pick_range_uses_only_approved_active_ranges() -> None:
    waiting = rng(13, 17, sex="M", approved=False)
    retired = rng(13, 17, sex="M", active=False)
    general = rng(12, 17)
    assert pick_range([waiting, retired], "M", ADULT) is None
    assert pick_range([waiting, retired, general], "M", ADULT) is general


@pytest.mark.item("M11.1")
def test_a_condition_range_is_used_only_for_that_condition() -> None:
    plain = rng(12, 15, sex="F")
    pregnant = rng(11, 14, sex="F", condition="pregnancy_t1")
    assert pick_range([pregnant, plain], "F", ADULT) is plain
    assert pick_range([plain, pregnant], "F", ADULT, "pregnancy_t1") is pregnant
    assert pick_range([pregnant], "F", ADULT) is None
    assert pick_range([plain], "F", ADULT, "pregnancy_t2") is plain


limits = st.one_of(st.none(), st.integers(0, 1000))
numbers = st.decimals(min_value=-10, max_value=1100, places=2)


@pytest.mark.item("M11.1")
@given(numbers, limits, limits, limits, limits)
def test_flag_agrees_with_the_limits_whatever_they_are(
    value: Decimal, low: int | None, high: int | None, c_low: int | None, c_high: int | None
) -> None:
    flag = compute_flag(value, rng(low, high, crit=(c_low, c_high))).flag
    beyond_low = c_low is not None and value <= c_low
    beyond_high = c_high is not None and value >= c_high
    assert (flag in ("LL", "HH")) == (beyond_low or beyond_high)
    if flag == "L":
        assert low is not None and value < low
    if flag == "H":
        assert high is not None and value > high
    if flag == "N":
        assert low is None or value >= low
        assert high is None or value <= high


@pytest.mark.item("M11.1")
@given(numbers, numbers)
def test_a_higher_value_never_gets_a_lower_flag(a: Decimal, b: Decimal) -> None:
    order = {"LL": 0, "L": 1, "N": 2, "H": 3, "HH": 4}
    glucose = rng(70, 99, crit=(30, 450))
    low, high = sorted((a, b))
    first, second = compute_flag(low, glucose).flag, compute_flag(high, glucose).flag
    assert first is not None and second is not None
    assert order[first] <= order[second]
