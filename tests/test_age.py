"""Age given in years, months and days, and the date of birth worked out from it."""

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labra.patients.age import age_text, age_ymd, estimated_dob

days = st.dates(min_value=date(1990, 1, 1), max_value=date(2100, 12, 31))


@pytest.mark.item("M03")
@given(days, st.integers(0, 150), st.integers(0, 11), st.integers(0, 30))
def test_age_ymd_to_estimated_dob(today: date, y: int, m: int, d: int) -> None:
    dob = estimated_dob(y, m, d, today)
    assert dob <= today
    years, months, rest = age_ymd(dob, today)
    # Month ends differ in length, so only dates clear of them come back exactly.
    if today.day <= 28 and d < today.day:
        assert (years, months, rest) == (y, m, d)
    if m <= 10:
        assert years == y


@pytest.mark.item("M03")
@given(days, st.integers(0, 150 * 366))
def test_age_ymd_counts_whole_units(today: date, lived: int) -> None:
    years, months, rest = age_ymd(today - timedelta(days=lived), today)
    assert years >= 0
    assert 0 <= months <= 11
    assert 0 <= rest <= 30


@pytest.mark.item("M03")
def test_age_examples() -> None:
    today = date(2026, 10, 9)
    assert estimated_dob(34, 0, 0, today) == date(1992, 10, 9)
    assert estimated_dob(0, 1, 0, date(2026, 3, 31)) == date(2026, 2, 28)
    assert age_ymd(date(2024, 2, 29), date(2025, 2, 28)) == (0, 11, 30)
    assert age_ymd(date(2024, 2, 29), date(2025, 3, 1)) == (1, 0, 1)
    assert age_text(date(1992, 10, 9), today) == "34 Y"
    assert age_text(date(2025, 4, 9), today) == "18 M"
    assert age_text(date(2026, 9, 29), today) == "10 D"
    assert age_text(today, today) == "0 D"
    with pytest.raises(ValueError):
        age_ymd(date(2026, 10, 10), today)
    with pytest.raises(ValueError):
        estimated_dob(-1, 0, 0, today)
