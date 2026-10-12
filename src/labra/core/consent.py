"""The consent notice patients agree to (DPDP Act). Each change is a new version, so a
consent always points at the exact words that were shown."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.core.errors import ConfigError
from labra.core.ids import utcnow
from labra.core.models import ConsentNotice

MAX_NOTICE_LENGTH = 5000


def current_notice(db: Session, language: str = "en") -> ConsentNotice:
    """The newest version already in force."""
    notice = db.scalar(
        select(ConsentNotice)
        .where(ConsentNotice.language == language, ConsentNotice.effective_from <= utcnow())
        .order_by(ConsentNotice.version.desc())
        .limit(1)
    )
    if notice is None:
        raise ConfigError(f"No consent notice in {language}.")
    return notice


def publish_notice(db: Session, body_text: str, language: str = "en") -> ConsentNotice:
    """Add the next version, in force from now. Patients tick again on their next visit."""
    latest = db.scalar(
        select(func.max(ConsentNotice.version)).where(ConsentNotice.language == language)
    )
    notice = ConsentNotice(version=(latest or 0) + 1, language=language, body_text=body_text)
    db.add(notice)
    db.flush()
    return notice
