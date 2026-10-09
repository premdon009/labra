"""Picks the platform adapters named in settings, once, at startup (ADR-0008)."""

from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import entry_points
from typing import Any

from labra.core.config import Settings, get_settings
from labra.core.errors import ConfigError
from labra.core.ports import (
    GROUPS,
    ErrorReporter,
    FileStore,
    Heartbeat,
    IdentityProvider,
    Mailer,
)


@dataclass(frozen=True)
class Platform:
    identity: IdentityProvider
    filestore: FileStore
    errors: ErrorReporter
    heartbeat: Heartbeat
    mailer: Mailer


def available(port: str) -> list[str]:
    return sorted(ep.name for ep in entry_points(group=GROUPS[port]))


def load_adapter(port: str, name: str, settings: Settings, protocol: type) -> Any:
    found = entry_points(group=GROUPS[port], name=name)
    if not found:
        choices = ", ".join(available(port)) or "none installed"
        raise ConfigError(f"Unknown {port} adapter '{name}'. Available: {choices}.")
    cls = next(iter(found)).load()
    adapter = cls.from_settings(settings)
    if not isinstance(adapter, protocol):
        raise ConfigError(f"{port} adapter '{name}' doesn't implement {protocol.__name__}.")
    return adapter


def build_platform(settings: Settings) -> Platform:
    """Build every adapter. Raises ConfigError on the first bad name or missing setting."""
    return Platform(
        identity=load_adapter("identity", settings.auth_provider, settings, IdentityProvider),
        filestore=load_adapter("filestore", settings.filestore, settings, FileStore),
        errors=load_adapter("errors", settings.errors, settings, ErrorReporter),
        heartbeat=load_adapter("heartbeat", settings.heartbeat, settings, Heartbeat),
        mailer=load_adapter("mailer", settings.mailer, settings, Mailer),
    )


_override: Platform | None = None


@lru_cache
def _default_platform() -> Platform:
    return build_platform(get_settings())


def get_platform() -> Platform:
    return _override if _override is not None else _default_platform()


def use_platform(platform: Platform | None) -> None:
    """Swap the adapters, for tests. `None` restores the configured ones."""
    global _override
    _override = platform
