from typing import Self

import structlog

from labra.core.config import Settings

log = structlog.stdlib.get_logger("labra.errors")


class LogErrorReporter:
    """Writes unexpected errors to the log under their reference number (EC-E03).
    A GlitchTip or Sentry adapter would send them to that service instead (EC-E05)."""

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls()

    def report(self, exc: BaseException, reference: str, context: dict[str, str]) -> None:
        log.error("unhandled_error", error_ref=reference, exc_info=exc, **context)
