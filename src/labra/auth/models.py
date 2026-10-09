import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, IdMixin
from labra.core.ids import utcnow


class UserSession(IdMixin, Base):
    """A signed-in browser. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "user_session"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branch.id"))
    csrf_token: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str] = mapped_column(String(45), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    ended_at: Mapped[datetime | None]


class LoginAttempt(IdMixin, Base):
    __tablename__ = "login_attempt"
    __table_args__ = (Index("ix_login_attempt_lookup", "username", "ip", "at"),)

    username: Mapped[str] = mapped_column(String(40))
    ip: Mapped[str] = mapped_column(String(45))
    at: Mapped[datetime] = mapped_column(default=utcnow)
    ok: Mapped[bool]
