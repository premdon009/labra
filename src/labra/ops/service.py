"""Write and read the run log."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core.errors import ValidationFailedError
from labra.core.ids import utcnow
from labra.ops.models import KINDS, OpsRun

DETAIL_MAX = 2000


@dataclass(frozen=True)
class LastRuns:
    """A job's newest run, and its newest run that worked (the same row when it worked)."""

    last: OpsRun | None
    last_ok: OpsRun | None


def record_run(
    session: Session,
    kind: str,
    started_at: datetime,
    *,
    ok: bool,
    snapshot: str | None = None,
    bytes_added: int | None = None,
    detail: str | None = None,
) -> OpsRun:
    if kind not in KINDS:
        message = f"Unknown job {kind!r}; one of {', '.join(KINDS)}."
        raise ValidationFailedError({"kind": message}, message)
    if detail and len(detail) > DETAIL_MAX:
        detail = detail[: DETAIL_MAX - 1] + "…"
    run = OpsRun(
        kind=kind,
        started_at=started_at,
        finished_at=max(utcnow(), started_at),
        ok=ok,
        snapshot=snapshot,
        bytes_added=bytes_added,
        detail=detail,
    )
    session.add(run)
    session.flush()
    return run


def last_runs(session: Session) -> dict[str, LastRuns]:
    """Every job kind, with its newest run and newest good run (None when it never ran)."""

    def newest(kind: str, *, ok_only: bool) -> OpsRun | None:
        query = select(OpsRun).where(OpsRun.kind == kind)
        if ok_only:
            query = query.where(OpsRun.ok)
        return session.scalar(query.order_by(OpsRun.started_at.desc(), OpsRun.id.desc()).limit(1))

    found = {}
    for kind in KINDS:
        last = newest(kind, ok_only=False)
        found[kind] = LastRuns(last, last if last and last.ok else newest(kind, ok_only=True))
    return found
