"""Ports: the small interfaces through which the core reaches platform services (ADR-0008).

Each port has a built-in adapter in `labra.adapters` and can be replaced by any adapter
registered under the entry-point group named in `GROUPS`. Domain code imports this module,
never an adapter.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from labra.core.config import Settings

GROUPS = {
    "identity": "labra.identity",
    "filestore": "labra.filestore",
    "errors": "labra.errors",
    "heartbeat": "labra.heartbeat",
    "mailer": "labra.mailer",
}


@runtime_checkable
class Adapter(Protocol):
    @classmethod
    def from_settings(cls, settings: Settings) -> "Adapter":
        """Build the adapter, raising ConfigError if a required setting is missing."""
        ...


@runtime_checkable
class IdentityProvider(Protocol):
    """Proves who a user is. What the user may do is decided by the core, never here.

    `kind` tells the login screen what to show: "password" providers verify a password
    for an existing user; "redirect" providers (OIDC) send the browser elsewhere and are
    added with their own methods when the first one is built.
    """

    kind: str

    def verify_password(self, db: Session, user_id: uuid.UUID, password: str) -> bool: ...

    def set_password(self, db: Session, user_id: uuid.UUID, password: str) -> None: ...

    def password_problems(self, password: str) -> list[str]:
        """Reasons a new password is refused; empty when it's acceptable."""
        ...


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    size: int
    key: str


@runtime_checkable
class FileStore(Protocol):
    """Content-addressed file storage: the key is derived from the SHA-256 of the bytes."""

    def put(self, data: bytes) -> StoredBlob: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


@runtime_checkable
class ErrorReporter(Protocol):
    def report(self, exc: BaseException, reference: str, context: dict[str, str]) -> None:
        """Record an unexpected error under `reference`, the number shown to staff."""
        ...


@runtime_checkable
class Heartbeat(Protocol):
    def ping(self, job: str, ok: bool = True, detail: str = "") -> None:
        """Tell the monitor that `job` finished (or failed)."""
        ...


@dataclass(frozen=True)
class Mail:
    to: list[str]
    subject: str
    body: str
    attachments: list[tuple[str, bytes, str]] = field(default_factory=list)


@runtime_checkable
class Mailer(Protocol):
    def send(self, mail: Mail) -> None: ...
