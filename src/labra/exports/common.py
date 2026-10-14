"""What both exports share: the folder they write to, who may run them, and private files.

Exports hold patient data, so they are written only under `LABRA_EXPORT_DIR` (a folder on
the data volume), only by an administrator, and only from the command line: there is no web
route. Folders are made readable by the owner alone.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from sqlalchemy import select
from sqlalchemy.orm import Session

import labra
from labra.auth.principal import Principal
from labra.auth.service import grants_for
from labra.core.config import get_settings
from labra.core.errors import ConfigError, PermissionDeniedError
from labra.org.models import AppUser, Role, UserBranchRole

# The installed app, including the static files the web server hands out.
APP_DIR = Path(labra.__file__).resolve().parent


def export_root(configured: Path | None = None) -> Path:
    """The export folder, made if missing. It must be an absolute path outside the app."""
    root = configured if configured is not None else get_settings().export_dir
    if root is None:
        raise ConfigError("Set LABRA_EXPORT_DIR to a folder on the data volume to export data.")
    if not root.is_absolute():
        raise ConfigError("LABRA_EXPORT_DIR must be an absolute path, such as /data/export.")
    resolved = root.resolve()
    if resolved == APP_DIR or APP_DIR in resolved.parents or resolved in APP_DIR.parents:
        raise ConfigError(
            "LABRA_EXPORT_DIR must be outside the app's own folder, which holds the files the"
            " web server serves."
        )
    private_dir(resolved)
    return resolved


def private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


@contextmanager
def private_file(
    path: Path, newline: str | None = None, encoding: str = "utf-8"
) -> Iterator[IO[str]]:
    """Write a text file only its owner can read. It appears under its name only once it
    is complete, so a half-written export is never mistaken for a whole one."""
    part = path.with_name(path.name + ".part")
    fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as f:
            yield f
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)


def acting_admin(db: Session, username: str) -> Principal:
    """The administrator running the export, who is named in its audit row."""
    user = db.scalar(select(AppUser).where(AppUser.username == username))
    is_admin = user is not None and (
        db.scalar(
            select(UserBranchRole.role_id)
            .join(Role, Role.id == UserBranchRole.role_id)
            .where(UserBranchRole.user_id == user.id, Role.code == "admin")
            .limit(1)
        )
        is not None
    )
    if user is None or not user.is_active or not is_admin:
        raise PermissionDeniedError(
            f"Only an active administrator can export data: not {username}."
        )
    return Principal(user.id, user.username, user.full_name, None, grants_for(db, user.id))
