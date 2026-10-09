"""Health endpoints for Docker, Caddy and any uptime monitor (ADR-0008).

`/healthz` answers while the process is up. `/readyz` answers 200 only when the app can do
real work: the database answers, its schema is at the latest migration, and the files disk
has room.
"""

import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from labra import __version__
from labra.core.config import get_settings
from labra.core.db import get_session
from labra.core.migrate import current_revisions, head_revisions

MIN_FREE_BYTES = 500 * 1024 * 1024

router = APIRouter(include_in_schema=False)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


def check_database(session: Session) -> str:
    try:
        session.execute(text("select 1"))
    except SQLAlchemyError:
        return "unreachable"
    return "ok"


def check_migrations(session: Session) -> str:
    try:
        current = current_revisions(session.connection())
    except SQLAlchemyError:
        return "unknown"
    return "ok" if current == head_revisions() else "behind"


def check_disk(path: Path, min_free: int = MIN_FREE_BYTES) -> str:
    try:
        free = shutil.disk_usage(path).free
    except OSError:
        return "missing"
    return "ok" if free >= min_free else "low"


@router.get("/readyz")
def readyz(
    session: Annotated[Session, Depends(get_session)], response: Response
) -> dict[str, object]:
    checks = {"database": check_database(session)}
    checks["migrations"] = check_migrations(session) if checks["database"] == "ok" else "unknown"
    checks["disk"] = check_disk(get_settings().files_dir)
    ok = all(v == "ok" for v in checks.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ok else "error", "checks": checks}
