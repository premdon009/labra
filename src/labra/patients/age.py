"""Age in years, months and days, and the date of birth worked back from one. Pure: no
database, no clock; callers pass the lab's today."""

import calendar
from datetime import date, timedelta

MAX_AGE_YEARS = 150


def _add_months(day: date, months: int) -> date:
    """`day` moved by whole months; the 31st becomes the last day of a shorter month."""
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def estimated_dob(years: int, months: int, days: int, today: date) -> date:
    """The birth date of someone `years`, `months` and `days` old today."""
    if min(years, months, days) < 0:
        raise ValueError("An age can't be negative.")
    return _add_months(today, -(years * 12 + months)) - timedelta(days=days)


def age_ymd(dob: date, today: date) -> tuple[int, int, int]:
    """Completed years, then months, then days, from `dob` to `today`."""
    if dob > today:
        raise ValueError("The date of birth is after today.")
    months = (today.year - dob.year) * 12 + today.month - dob.month
    if today.day < dob.day:
        months -= 1
    days = (today - _add_months(dob, months)).days
    return months // 12, months % 12, days


def age_text(dob: date, today: date) -> str:
    """How an age is printed: `34 Y` from two years, `7 M` under that, `12 D` under a month."""
    years, months, days = age_ymd(dob, today)
    if years >= 2:
        return f"{years} Y"
    if years or months:
        return f"{years * 12 + months} M"
    return f"{days} D"
