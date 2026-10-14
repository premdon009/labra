import os
import time
import uuid
from datetime import UTC, date, datetime, timedelta, timezone

# India has one time zone and no daylight saving, so a fixed offset needs no tz database.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def new_id() -> uuid.UUID:
    """A time-ordered UUID (version 7), so rows created on different devices sort by time."""
    stdlib = getattr(uuid, "uuid7", None)
    if stdlib is not None:
        return stdlib()
    # Python 3.13 has no uuid7: 48-bit Unix milliseconds, then version, variant and random bits.
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10))
    value = (ms & (2**48 - 1)) << 80 | 0x7 << 76 | (rand >> 68 & 0xFFF) << 64
    value |= 0b10 << 62 | rand & (2**62 - 1)
    return uuid.UUID(int=value)


def utcnow() -> datetime:
    return datetime.now(UTC)


def lab_today() -> date:
    """Today's date in India: financial years and daily numbers turn over at IST midnight."""
    return datetime.now(IST).date()


def day_start(day: date) -> datetime:
    """IST midnight at the start of `day`: a lab day runs from one to the next."""
    return datetime.combine(day, datetime.min.time(), tzinfo=IST)
