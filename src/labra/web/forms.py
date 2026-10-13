"""Reading what a form or URL sent: every value arrives as text."""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import Form
from pydantic import BeforeValidator

from labra.core.errors import NotFoundError
from labra.core.ids import IST


def as_uuid(value: str) -> uuid.UUID:
    """A record id from a URL or hidden field; anything else is simply not found."""
    try:
        return uuid.UUID(value)
    except ValueError:
        raise NotFoundError() from None


def whole(value: str) -> int | None:
    """An age part as typed: empty is None, anything else not a whole number is -1, which
    the form check reports as out of range."""
    value = value.strip()
    if not value:
        return None
    return int(value) if value.isdigit() else -1


def day(value: str) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def local_minute(value: str) -> datetime | None:
    """A `datetime-local` box, which the browser sends without a zone: India time."""
    try:
        return datetime.fromisoformat(value).replace(tzinfo=IST) if value else None
    except ValueError:
        return None


def page_no(value: str) -> int:
    """The page of a list asked for in the URL; the first page when it isn't a number."""
    value = value.strip()
    # Nine digits are more pages than any list has, and never too long to read as a number.
    return max(int(value[:9]), 1) if value.isascii() and value.isdigit() else 1


def version_no(value: object) -> int:
    """The version of a row that a form carried back. Anything that isn't a number counts
    as 0, which no saved row has, so the save is refused as out of date."""
    text = str(value).strip()
    return int(text[:9]) if text.isascii() and text.isdigit() else 0


RowVersion = Annotated[int, BeforeValidator(version_no), Form()]
