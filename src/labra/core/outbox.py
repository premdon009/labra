"""The outbox: events written with the change, delivered after commit by a later job."""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core.ids import utcnow
from labra.core.models import EventOutbox

MAX_ATTEMPTS = 10


def emit(db: Session, topic: str, payload: dict[str, Any]) -> EventOutbox:
    """Queue an event in the caller's transaction. Refer to records by ID, never copy
    personal data into the payload."""
    event = EventOutbox(topic=topic, payload=payload)
    db.add(event)
    db.flush()
    return event


def claim(db: Session, limit: int = 50) -> list[EventOutbox]:
    """Due events, locked so a second worker skips them."""
    return list(
        db.scalars(
            select(EventOutbox)
            .where(
                EventOutbox.processed_at.is_(None),
                EventOutbox.available_at <= utcnow(),
                EventOutbox.attempts < MAX_ATTEMPTS,
            )
            .order_by(EventOutbox.available_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )


def mark_done(event: EventOutbox) -> None:
    event.processed_at = utcnow()


def mark_failed(event: EventOutbox, error: str) -> None:
    """Retry later, waiting longer after each failure (1, 2, 4 … minutes, capped at a day)."""
    event.attempts += 1
    event.last_error = error[:2000]
    event.available_at = utcnow() + timedelta(minutes=min(2 ** (event.attempts - 1), 1440))
