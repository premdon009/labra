"""In-memory adapters for tests. Each one passes the same contract tests as the real one."""

import hashlib
from dataclasses import dataclass, field

from labra.adapters.identity_local import LocalIdentity
from labra.core.ports import Mail, StoredBlob
from labra.core.registry import Platform


class MemoryFileStore:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def put(self, data: bytes) -> StoredBlob:
        key = hashlib.sha256(data).hexdigest()
        self.blobs[key] = data
        return StoredBlob(sha256=key, size=len(data), key=key)

    def get(self, key: str) -> bytes:
        from labra.core.errors import NotFoundError

        if key not in self.blobs:
            raise NotFoundError()
        return self.blobs[key]

    def exists(self, key: str) -> bool:
        return key in self.blobs


@dataclass
class RecordingErrors:
    reports: list[tuple[str, BaseException, dict[str, str]]] = field(default_factory=list)

    def report(self, exc: BaseException, reference: str, context: dict[str, str]) -> None:
        self.reports.append((reference, exc, context))


@dataclass
class RecordingHeartbeat:
    pings: list[tuple[str, bool, str]] = field(default_factory=list)

    def ping(self, job: str, ok: bool = True, detail: str = "") -> None:
        self.pings.append((job, ok, detail))


@dataclass
class RecordingMailer:
    sent: list[Mail] = field(default_factory=list)

    def send(self, mail: Mail) -> None:
        self.sent.append(mail)


def fake_platform() -> Platform:
    return Platform(
        identity=LocalIdentity(),
        filestore=MemoryFileStore(),
        errors=RecordingErrors(),
        heartbeat=RecordingHeartbeat(),
        mailer=RecordingMailer(),
    )
