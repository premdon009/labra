import os
import urllib.request
from typing import Self
from urllib.error import URLError

import structlog

from labra.core.config import Settings
from labra.core.errors import ConfigError

log = structlog.stdlib.get_logger("labra.heartbeat")


class LogHeartbeat:
    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls()

    def ping(self, job: str, ok: bool = True, detail: str = "") -> None:
        log.info("heartbeat", job=job, ok=ok, detail=detail)


class HttpHeartbeat:
    """Pings `LABRA_HEARTBEAT_URL_<JOB>` (Healthchecks.io style: `/fail` appended on failure).
    Jobs without a URL are only logged."""

    def __init__(self, urls: dict[str, str], timeout: float = 10) -> None:
        self.urls = urls
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        prefix = "LABRA_HEARTBEAT_URL_"
        # Compose passes every job's variable through, so an empty one means "not set".
        urls = {
            k[len(prefix) :].lower(): v for k, v in os.environ.items() if k.startswith(prefix) and v
        }
        for job, url in urls.items():
            if not url.startswith("https://"):
                raise ConfigError(f"Heartbeat URL for '{job}' must use https.")
        return cls(urls)

    def ping(self, job: str, ok: bool = True, detail: str = "") -> None:
        url = self.urls.get(job)
        log.info("heartbeat", job=job, ok=ok, detail=detail, sent=url is not None)
        if url is None:
            return
        target = url if ok else url.rstrip("/") + "/fail"
        try:
            # https only, enforced in from_settings.
            body = detail.encode()[:10_000]
            with urllib.request.urlopen(target, data=body, timeout=self.timeout):  # noqa: S310
                pass
        except (URLError, TimeoutError) as exc:
            # A monitor that can't be reached must never break the job itself.
            log.warning("heartbeat_failed", job=job, error=type(exc).__name__)
