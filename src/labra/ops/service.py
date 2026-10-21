"""Write and read the run log."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from labra.core.certs import fetch_validity
from labra.core.errors import ValidationFailedError
from labra.core.health import DISK_ALERT_PERCENT, disk_use
from labra.core.ids import utcnow
from labra.core.migrate import current_revisions, head_revisions
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


JOB_LABELS = {
    "backup": "Backup",
    "drill": "Restore drill",
    "verify": "Audit log check",
    "disk": "Disk space check",
    "upgrade": "Upgrade",
}
# A job is overdue when its last good run is older than this. Backups run every 15 minutes in
# lab hours and at 23:30, so the night is the longest gap; upgrades have no schedule.
OVERDUE = {
    "backup": timedelta(hours=12),
    "drill": timedelta(days=35),
    "verify": timedelta(hours=26),
    "disk": timedelta(hours=2),
}
# Other certificates are renewed by hand, so warn this long before they run out.
CERT_WARN = timedelta(days=30)
# Caddy names its local authority "Caddy Local Authority - <year> ECC Root" and its intermediate
# "Caddy Local Authority - ECC Intermediate".
CADDY_ISSUER = "Caddy Local Authority"


@dataclass(frozen=True)
class JobStatus:
    kind: str
    label: str
    last: OpsRun | None
    last_ok: OpsRun | None
    state: str  # ok, failed, overdue, never
    every: timedelta | None

    @property
    def problem(self) -> bool:
        return self.state in ("failed", "overdue") or (self.state == "never" and bool(self.every))

    @property
    def overdue_after(self) -> str:
        if self.every is None:
            return "—"
        hours = int(self.every.total_seconds() // 3600)
        return f"{hours} hours" if hours < 48 else f"{hours // 24} days"


def job_statuses(session: Session, now: datetime) -> list[JobStatus]:
    statuses = []
    for kind, runs in last_runs(session).items():
        limit = OVERDUE.get(kind)
        if runs.last is None:
            state = "never"
        elif not runs.last.ok:
            state = "failed"
        elif limit and now - runs.last.started_at > limit:
            state = "overdue"
        else:
            state = "ok"
        statuses.append(JobStatus(kind, JOB_LABELS[kind], runs.last, runs.last_ok, state, limit))
    return statuses


@dataclass(frozen=True)
class DiskStatus:
    percent: int | None
    free: int | None
    error: str | None = None

    @property
    def problem(self) -> bool:
        return self.percent is None or self.percent >= DISK_ALERT_PERCENT


def disk_status(path: Path) -> DiskStatus:
    try:
        use = disk_use(path)
    except OSError as e:
        return DiskStatus(None, None, e.strerror or str(e))
    return DiskStatus(int(use.percent), use.free)


@dataclass(frozen=True)
class MigrationStatus:
    current: set[str]
    pending: set[str]
    error: bool = False

    @property
    def problem(self) -> bool:
        return self.error or bool(self.pending)


def migration_status(session: Session) -> MigrationStatus:
    heads = head_revisions()
    try:
        current = current_revisions(session.connection())
    except SQLAlchemyError:
        return MigrationStatus(set(), heads, error=True)
    return MigrationStatus(current, heads - current)


def database_bytes(session: Session) -> int:
    return session.scalar(text("select pg_database_size(current_database())")) or 0


@dataclass(frozen=True)
class CertStatus:
    checked: bool
    expires: datetime | None = None
    days_left: int | None = None
    auto_renewed: bool = False
    error: str | None = None

    @property
    def problem(self) -> bool:
        if not self.checked:
            return False
        if self.error or self.days_left is None or self.days_left < 0:
            return True
        return not self.auto_renewed and self.days_left < CERT_WARN.days


def cert_status(address: str | None, server_name: str | None, now: datetime) -> CertStatus:
    if not address:
        return CertStatus(checked=False)
    try:
        dates = fetch_validity(address, server_name)
    except (OSError, ValueError) as e:
        return CertStatus(checked=True, error=str(e) or type(e).__name__)
    left = dates.not_after - now
    # A certificate from Caddy's own authority is renewed by the proxy itself.
    auto = dates.issuer_cn.startswith(CADDY_ISSUER)
    return CertStatus(True, dates.not_after, left.days, auto)
