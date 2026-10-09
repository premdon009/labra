"""Local username + password identity: argon2id hashes in the `local_credential` table.

Installs that use an external identity provider simply have no rows here.
"""

import uuid
from datetime import datetime
from functools import lru_cache
from importlib.resources import files
from typing import Self

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from labra.core.config import Settings
from labra.core.db import Base
from labra.core.ids import utcnow

MIN_LENGTH = 10
MAX_LENGTH = 128


class LocalCredential(Base):
    __tablename__ = "local_credential"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(default=utcnow)


@lru_cache
def common_passwords() -> frozenset[str]:
    text = files("labra.adapters").joinpath("common_passwords.txt").read_text(encoding="utf-8")
    return frozenset(line.strip().lower() for line in text.splitlines() if line.strip())


class LocalIdentity:
    kind = "password"

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self.hasher = hasher or PasswordHasher()

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls()

    def password_problems(self, password: str) -> list[str]:
        problems = []
        if len(password) < MIN_LENGTH:
            problems.append(f"Use at least {MIN_LENGTH} characters.")
        if len(password) > MAX_LENGTH:
            problems.append(f"Use at most {MAX_LENGTH} characters.")
        if password.lower() in common_passwords():
            problems.append("This password is too common. Choose another.")
        return problems

    def set_password(self, db: Session, user_id: uuid.UUID, password: str) -> None:
        cred = db.get(LocalCredential, user_id)
        hashed = self.hasher.hash(password)
        if cred is None:
            db.add(LocalCredential(user_id=user_id, password_hash=hashed))
        else:
            cred.password_hash = hashed
            cred.changed_at = utcnow()

    def verify_password(self, db: Session, user_id: uuid.UUID, password: str) -> bool:
        cred = db.get(LocalCredential, user_id)
        if cred is None:
            # Spend the same time as a real check, so timing doesn't reveal unknown users.
            self.hasher.hash(password)
            return False
        try:
            self.hasher.verify(cred.password_hash, password)
        except (VerificationError, InvalidHashError):
            return False
        if self.hasher.check_needs_rehash(cred.password_hash):
            cred.password_hash = self.hasher.hash(password)
        return True
