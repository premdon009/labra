import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from labra.core.errors import ConfigError

ENV_PREFIX = "LABRA_"


class FileEnvSource(EnvSettingsSource):
    """Reads `LABRA_<NAME>_FILE`, the path of a file holding the value (Docker secrets)."""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        path = os.environ.get(f"{ENV_PREFIX}{field_name.upper()}_FILE")
        if path:
            return Path(path).read_text(encoding="utf-8").strip(), field_name, False
        return None, field_name, False


class Settings(BaseSettings):
    """Process-level settings, read from `LABRA_*` environment variables.

    Lab-level settings that admins change at runtime live in the `setting` table, not here.
    Any value can come from a file instead: `LABRA_<NAME>_FILE=/run/secrets/<name>`.
    """

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, extra="ignore")

    database_url: SecretStr = SecretStr("postgresql+psycopg://labra@localhost:5432/labra")
    files_dir: Path = Path("/data/files")
    # Where `labra export` writes; exports hold patient data, so a folder on the data volume.
    export_dir: Path | None = None

    # Platform adapters, by entry-point name (ADR-0008).
    auth_provider: str = "local"
    filestore: str = "local"
    errors: str = "log"
    heartbeat: str = "log"
    mailer: str = "console"
    smtp_url: SecretStr | None = None
    mail_from: str = "labra@localhost"

    log_format: Literal["json", "console"] = "json"
    log_level: str = "INFO"

    metrics: Literal["prometheus", "off"] = "prometheus"
    metrics_token: SecretStr | None = None
    internal_networks: list[str] = [
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
    ]

    # Where the help button points: the manual inside the app, so help works offline.
    manual_url: str = "/manual"

    # The System page reads the HTTPS certificate's expiry from this proxy (host[:port]),
    # asking for the site's name; unset, the certificate isn't checked.
    cert_check_host: str | None = None
    cert_check_name: str | None = None

    cookie_secure: bool = True
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12

    @field_validator("database_url")
    @classmethod
    def _postgresql_only(cls, url: SecretStr) -> SecretStr:
        # ConfigError passes through pydantic unwrapped, so `labra check-config` exits 2. The
        # URL holds a password, so it is never echoed.
        scheme = url.get_secret_value().partition("://")[0]
        if scheme.partition("+")[0] != "postgresql":
            raise ConfigError(
                "LABRA_DATABASE_URL must start with postgresql:// or postgresql+<driver>://. "
                "Labra runs on PostgreSQL; see docs/dev/services.md."
            )
        return url

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            FileEnvSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
