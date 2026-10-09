"""Ports and adapters: the registry, the config secret files, and one contract suite per port
that every adapter (built-in or fake) must pass."""

from pathlib import Path

import pytest

from labra.adapters.errors_log import LogErrorReporter
from labra.adapters.filestore_local import LocalFileStore
from labra.adapters.heartbeat import HttpHeartbeat, LogHeartbeat
from labra.adapters.mailer import ConsoleMailer, SmtpMailer, build_message
from labra.core.config import Settings
from labra.core.errors import ConfigError, NotFoundError
from labra.core.ports import (
    ErrorReporter,
    FileStore,
    Heartbeat,
    IdentityProvider,
    Mail,
    Mailer,
)
from labra.core.registry import available, build_platform
from tests.fakes import MemoryFileStore, RecordingErrors, RecordingHeartbeat, RecordingMailer

pytestmark = pytest.mark.item("W15")


def test_default_settings_build_every_builtin(tmp_path: Path) -> None:
    platform = build_platform(Settings(files_dir=tmp_path))
    assert isinstance(platform.identity, IdentityProvider)
    assert isinstance(platform.filestore, LocalFileStore)
    assert isinstance(platform.errors, LogErrorReporter)
    assert isinstance(platform.heartbeat, LogHeartbeat)
    assert isinstance(platform.mailer, ConsoleMailer)


@pytest.mark.parametrize("port", ["identity", "filestore", "errors", "heartbeat", "mailer"])
def test_each_port_has_a_builtin(port: str) -> None:
    assert available(port)


def test_unknown_adapter_fails_fast_with_choices(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"Unknown filestore adapter 's3'\. Available: local"):
        build_platform(Settings(files_dir=tmp_path, filestore="s3"))


def test_smtp_mailer_needs_its_url(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        build_platform(Settings(files_dir=tmp_path, mailer="smtp"))


def test_relative_files_dir_refused() -> None:
    with pytest.raises(ConfigError):
        LocalFileStore.from_settings(Settings(files_dir=Path("relative/files")))


def test_secret_read_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = tmp_path / "metrics_token"
    secret.write_text("from-a-file\n", encoding="utf-8")
    monkeypatch.setenv("LABRA_METRICS_TOKEN_FILE", str(secret))
    token = Settings().metrics_token
    assert token is not None
    assert token.get_secret_value() == "from-a-file"


# FileStore contract


@pytest.fixture(params=["local", "memory"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> FileStore:
    return LocalFileStore(tmp_path) if request.param == "local" else MemoryFileStore()


def test_filestore_round_trip(store: FileStore) -> None:
    blob = store.put(b"report body")
    assert blob.size == len(b"report body")
    assert store.exists(blob.key)
    assert store.get(blob.key) == b"report body"


def test_filestore_same_content_same_key(store: FileStore) -> None:
    assert store.put(b"same").key == store.put(b"same").key


def test_filestore_missing_key(store: FileStore) -> None:
    missing = "0" * 64
    assert not store.exists(missing)
    with pytest.raises(NotFoundError):
        store.get(missing)


def test_local_filestore_refuses_path_tricks(tmp_path: Path) -> None:
    store = LocalFileStore(tmp_path)
    with pytest.raises(NotFoundError):
        store.get("../../etc/passwd")


# ErrorReporter, Heartbeat and Mailer contracts


@pytest.mark.parametrize("reporter", [LogErrorReporter(), RecordingErrors()])
def test_error_reporter_contract(reporter: ErrorReporter) -> None:
    assert isinstance(reporter, ErrorReporter)
    reporter.report(RuntimeError("boom"), "E-TEST0001", {"route": "/x"})


@pytest.mark.parametrize("heartbeat", [LogHeartbeat(), RecordingHeartbeat()])
def test_heartbeat_contract(heartbeat: Heartbeat) -> None:
    assert isinstance(heartbeat, Heartbeat)
    heartbeat.ping("backup")
    heartbeat.ping("backup", ok=False, detail="disk full")


def test_http_heartbeat_needs_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LABRA_HEARTBEAT_URL_BACKUP", "http://monitor.example/ping")
    with pytest.raises(ConfigError):
        HttpHeartbeat.from_settings(Settings())


def test_http_heartbeat_unreachable_only_warns() -> None:
    # Port 9 on localhost refuses; a failed ping must never fail the job itself.
    HttpHeartbeat({"backup": "https://127.0.0.1:9/ping"}, timeout=1).ping("backup")


MAIL = Mail(to=["someone@example.com"], subject="Report ready", body="Your report is ready.")


@pytest.mark.parametrize("mailer", [ConsoleMailer(), RecordingMailer()])
def test_mailer_contract(mailer: Mailer) -> None:
    assert isinstance(mailer, Mailer)
    mailer.send(MAIL)


def test_build_message_headers() -> None:
    msg = build_message(MAIL, "lab@example.com")
    assert msg["From"] == "lab@example.com"
    assert msg["To"] == "someone@example.com"
    assert msg["Subject"] == "Report ready"


@pytest.mark.parametrize("url", ["http://mail.example", "smtp://", "ftp://mail.example"])
def test_smtp_mailer_refuses_bad_urls(url: str) -> None:
    with pytest.raises(ConfigError):
        SmtpMailer(url, "lab@example.com")
