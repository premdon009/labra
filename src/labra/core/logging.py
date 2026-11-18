"""Structured logs to stdout (EC-E01), with personal data scrubbed and errors logged without
their messages (EC-C03).

Logs are the stdout "port": any collector that reads container output can ship them.
Domain code calls `get_logger()` and never imports structlog itself.
"""

import logging
import re
import sys
import traceback
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Keys whose values are never logged, whatever they hold.
SECRET_OR_PERSONAL_KEYS = frozenset(
    {
        "address",
        "authorization",
        "cookie",
        "dob",
        "email",
        "full_name",
        "mobile",
        "name",
        "password",
        "phone",
        "secret",
        "set-cookie",
        "token",
        "username",
    }
)
REDACTED = "[redacted]"
# Indian mobile numbers (optionally +91), and email addresses, inside free text. A number
# run into letters is part of an ID (a request ID's hex), not a phone.
_PHONE_RE = re.compile(r"(?<![\dA-Za-z])(?:\+?91[\s-]?)?[6-9]\d{9}(?![\dA-Za-z])")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def scrub_text(value: str) -> str:
    return _EMAIL_RE.sub(REDACTED, _PHONE_RE.sub(REDACTED, value))


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {
            k: REDACTED if str(k).lower() in SECRET_OR_PERSONAL_KEYS else _scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


def scrub_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key.lower() in SECRET_OR_PERSONAL_KEYS:
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _scrub(event_dict[key])
    return event_dict


def _exception(exc_info: Any) -> BaseException | None:
    if isinstance(exc_info, BaseException):
        return exc_info
    if isinstance(exc_info, tuple) and len(exc_info) == 3:  # pyright: ignore[reportUnknownArgumentType]
        found: Any = exc_info[1]  # pyright: ignore[reportUnknownVariableType]
        return found if isinstance(found, BaseException) else None
    return sys.exc_info()[1] if exc_info else None


def _frame(frame: traceback.FrameSummary) -> str:
    path = frame.filename.replace("\\", "/")
    for marker in ("/site-packages/", "/src/"):
        if marker in path:
            path = path.rsplit(marker, 1)[1]
            break
    return f"{path}:{frame.lineno} in {frame.name}"


def exception_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """An error's type and where it was raised, never its message: a message (a database
    error's parameters above all) can carry a patient's name, phone or result."""
    exc = _exception(event_dict.pop("exc_info", None))
    if exc is None:
        return event_dict
    chain: list[str] = []
    seen: BaseException | None = exc
    while seen is not None and len(chain) < 5:
        chain.append(f"{type(seen).__module__}.{type(seen).__qualname__}")
        seen = seen.__cause__ or seen.__context__
    event_dict["exception"] = " <- ".join(chain)
    event_dict["stack"] = [_frame(f) for f in traceback.extract_tb(exc.__traceback__)][-15:]
    return event_dict


def _add_request_id(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    rid = request_id_var.get()
    if rid is not None:
        event_dict.setdefault("request_id", rid)
    return event_dict


def configure_logging(fmt: str = "json", level: str = "INFO") -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        exception_processor,
        scrub_processor,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Uvicorn's access log repeats what the request middleware logs, with full URLs.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> Any:
    return structlog.stdlib.get_logger(name)
