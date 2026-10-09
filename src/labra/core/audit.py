"""The audit log: who did what, when, kept as a hash chain (design §5, EC-B03)."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from labra.core.ids import utcnow
from labra.core.models import AuditLog

GENESIS = "0" * 64
# Serialises writers so each row sees the hash of the row before it.
_CHAIN_LOCK = 0x4C414252  # "LABR"


def _normalise(detail: dict[str, Any]) -> dict[str, Any]:
    """The detail as it reads back from JSONB, so the hash matches after a round trip."""
    return json.loads(json.dumps(detail, default=str))


def chain_hash(
    prev_hash: str,
    at: datetime,
    user_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: str | None,
    detail: dict[str, Any],
) -> str:
    body = {
        "prev": prev_hash,
        "at": at.astimezone(UTC).isoformat(),
        "user": str(user_id) if user_id else None,
        "branch": str(branch_id) if branch_id else None,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "detail": detail,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record(
    db: Session,
    action: str,
    entity: str,
    entity_id: str | uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    user_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> AuditLog:
    """Add an audit row in the caller's transaction. Never put personal data in `detail`;
    refer to records by ID."""
    db.execute(text("select pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK})
    prev = db.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)) or GENESIS
    at = utcnow()
    eid = str(entity_id) if entity_id is not None else None
    clean = _normalise(detail or {})
    row = AuditLog(
        at=at,
        user_id=user_id,
        branch_id=branch_id,
        action=action,
        entity=entity,
        entity_id=eid,
        detail=clean,
        prev_hash=prev,
        hash=chain_hash(prev, at, user_id, branch_id, action, entity, eid, clean),
    )
    db.add(row)
    db.flush()
    return row


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    checked: int
    first_bad_id: int | None = None
    reason: str = ""


def verify(db: Session) -> VerifyResult:
    """Walk the whole chain. Reports the first row whose link or hash doesn't match."""
    prev = GENESIS
    checked = 0
    rows = db.execute(select(AuditLog).order_by(AuditLog.id).execution_options(yield_per=1000))
    for (row,) in rows:
        if row.prev_hash != prev:
            return VerifyResult(False, checked, row.id, "link broken: a row before it is gone")
        expected = chain_hash(
            row.prev_hash,
            row.at,
            row.user_id,
            row.branch_id,
            row.action,
            row.entity,
            row.entity_id,
            row.detail,
        )
        if row.hash != expected:
            return VerifyResult(False, checked, row.id, "hash mismatch: the row was changed")
        prev = row.hash
        checked += 1
    return VerifyResult(True, checked)
