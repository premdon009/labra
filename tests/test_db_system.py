"""The System page: version, scheduled jobs, disk, database, migrations and certificate."""

import shutil
import socket
import ssl
import subprocess
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from labra import __version__
from labra.core.certs import validity
from labra.core.health import DiskUse
from labra.core.ids import utcnow
from labra.core.registry import Platform
from labra.ops import service
from labra.ops.service import cert_status, job_statuses, record_run
from tests.frontdesk import sign_in

OPENSSL = shutil.which("openssl")
needs_openssl = pytest.mark.skipif(OPENSSL is None, reason="needs openssl")
# serve(days) -> "host:port", a TLS server with a certificate valid for that many days
Serve = Callable[[int], str]


def _cert(tmp_path: Path, days: int) -> tuple[Path, Path]:
    cert, key = tmp_path / f"{days}.crt", tmp_path / f"{days}.key"
    subprocess.run(  # noqa: S603
        [
            OPENSSL or "openssl", "req", "-x509",
            "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-nodes", "-days", str(days), "-subj", "/CN=labra.lan",
            "-keyout", str(key), "-out", str(cert),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    return cert, key


@pytest.fixture
def tls_server(tmp_path: Path) -> Iterator[Serve]:
    sockets: list[socket.socket] = []

    def serve(days: int) -> str:
        cert, key = _cert(tmp_path, days)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        listener = socket.create_server(("127.0.0.1", 0))
        sockets.append(listener)

        def answer() -> None:
            while True:
                try:
                    conn, _ = listener.accept()
                except OSError:
                    return
                try:
                    with context.wrap_socket(conn, server_side=True):
                        pass
                except (OSError, ssl.SSLError):
                    conn.close()

        threading.Thread(target=answer, daemon=True).start()
        return f"127.0.0.1:{listener.getsockname()[1]}"

    yield serve
    for listener in sockets:
        listener.close()


# Scheduled jobs


@pytest.mark.item("EC-E04")
def test_each_job_is_ok_failed_overdue_or_never_run(db: Session) -> None:
    now = utcnow()
    record_run(db, "backup", now - timedelta(hours=2), ok=True)
    record_run(db, "backup", now - timedelta(minutes=15), ok=False, detail="usb: no repository")
    record_run(db, "drill", now - timedelta(days=36), ok=True)
    record_run(db, "verify", now - timedelta(hours=25), ok=True)

    states = {j.kind: j for j in job_statuses(db, now)}
    assert states["backup"].state == "failed"
    assert states["backup"].last_ok is not None
    assert states["drill"].state == "overdue"
    assert states["verify"].state == "ok"
    assert states["disk"].state == "never"
    assert [k for k, j in states.items() if j.problem] == ["backup", "drill", "disk"]
    # Upgrades have no schedule, so never having had one is fine.
    assert states["upgrade"].state == "never"
    assert states["upgrade"].overdue_after == "—"
    assert states["drill"].overdue_after == "35 days"
    assert states["verify"].overdue_after == "26 hours"


@pytest.mark.item("EC-E04")
def test_a_backup_is_overdue_just_past_its_limit(db: Session) -> None:
    now = utcnow()
    record_run(db, "backup", now - timedelta(hours=12), ok=True)
    finished = job_statuses(db, now)[0].last
    assert finished is not None
    at_limit = finished.started_at + service.OVERDUE["backup"]
    assert job_statuses(db, at_limit)[0].state == "ok"
    assert job_statuses(db, at_limit + timedelta(seconds=1))[0].state == "overdue"


# Certificate


def _der(not_before: bytes, not_after: bytes, *, version: bool) -> bytes:
    def tlv(tag: int, body: bytes) -> bytes:
        return bytes([tag, len(body)]) + body

    fields = [tlv(0xA0, tlv(0x02, b"\x02"))] if version else []
    validity = tlv(0x30, not_before + not_after)
    fields += [tlv(0x02, b"\x01"), tlv(0x30, b""), tlv(0x30, b""), validity]
    return tlv(0x30, tlv(0x30, b"".join(fields)))


@pytest.mark.item("EC-E04")
@pytest.mark.parametrize("version", [True, False])
def test_validity_reads_both_time_formats(version: bool) -> None:
    der = _der(b"\x17\x0d491231000000Z", b"\x18\x0f20600101083000Z", version=version)
    dates = validity(der)
    assert dates.not_before == datetime(2049, 12, 31, tzinfo=UTC)
    assert dates.not_after == datetime(2060, 1, 1, 8, 30, tzinfo=UTC)
    # Two-digit years from 50 are 19xx.
    assert validity(_der(b"\x17\x0d500101000000Z", b"\x17\x0d991231000000Z", version=False)) == (
        type(dates)(datetime(1950, 1, 1, tzinfo=UTC), datetime(1999, 12, 31, tzinfo=UTC))
    )


@pytest.mark.item("EC-E04")
@pytest.mark.parametrize("der", [b"", b"\x30\x05\x30", b"\x30\x02\x30\x00", b"not a cert"])
def test_validity_refuses_what_is_not_a_certificate(der: bytes) -> None:
    with pytest.raises(ValueError, match="certificate"):
        validity(der)


@needs_openssl
@pytest.mark.item("EC-E04")
def test_validity_of_a_real_certificate(tmp_path: Path) -> None:
    cert, _ = _cert(tmp_path, 400)
    dates = validity(ssl.PEM_cert_to_DER_cert(cert.read_text()))
    assert dates.not_after - dates.not_before == timedelta(days=400)
    assert abs(dates.not_before - utcnow()) < timedelta(minutes=5)


@needs_openssl
@pytest.mark.item("EC-E04")
def test_a_long_certificate_warns_30_days_before_it_runs_out(tls_server: Serve) -> None:
    address = tls_server(400)
    now = utcnow()
    fresh = cert_status(address, "labra.lan", now)
    assert (fresh.checked, fresh.problem, fresh.auto_renewed, fresh.days_left) == (
        True, False, False, 399,
    )  # fmt: skip
    assert cert_status(address, "labra.lan", now + timedelta(days=369)).problem is False
    assert cert_status(address, "labra.lan", now + timedelta(days=371)).problem is True
    expired = cert_status(address, None, now + timedelta(days=401))
    assert expired.problem
    assert expired.days_left is not None
    assert expired.days_left < 0


@needs_openssl
@pytest.mark.item("EC-E04")
def test_a_short_lived_certificate_is_a_problem_only_once_expired(tls_server: Serve) -> None:
    address = tls_server(1)
    now = utcnow()
    assert cert_status(address, "labra.lan", now).auto_renewed
    assert cert_status(address, "labra.lan", now).problem is False
    assert cert_status(address, "labra.lan", now + timedelta(days=2)).problem is True


@pytest.mark.item("EC-E04")
def test_an_unset_or_unreachable_proxy() -> None:
    assert cert_status(None, None, utcnow()) == service.CertStatus(checked=False)
    assert cert_status(None, None, utcnow()).problem is False
    with socket.create_server(("127.0.0.1", 0)) as free:
        port = free.getsockname()[1]
    down = cert_status(f"127.0.0.1:{port}", None, utcnow())
    assert down.checked
    assert down.problem
    assert down.error


# The page


@pytest.fixture
def full_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service, "disk_use", lambda _path: DiskUse(85.4, 3_000_000_000, 64_000_000_000)
    )


@pytest.mark.item("EC-E04")
@pytest.mark.item("EC-G01")
def test_the_system_page_shows_everything_an_admin_checks(
    seeded: Session, platform: Platform, db_client: TestClient, full_disk: None
) -> None:
    record_run(seeded, "backup", utcnow(), ok=False, detail="usb: no repository at /backup/usb")
    record_run(seeded, "verify", utcnow(), ok=True, detail="Audit log intact: 12 rows checked.")
    sign_in(db_client, "anil")

    home = db_client.get("/")
    assert 'href="/admin/system"' in home.text
    page = db_client.get("/admin/system")
    assert page.status_code == 200
    html = page.text
    assert __version__ in html
    assert "85% used, 3.0 GB free." in html
    assert "The alert is at 80%." in html
    assert "Up to date (" in html
    assert " MB." in html or " kB." in html
    assert "Not checked." in html
    assert "usb: no repository at /backup/usb" in html
    assert "Audit log intact: 12 rows checked." in html
    assert html.count("badge-destructive") == 4  # disk, failed backup, never: drill, disk check
    assert "need attention" in html


@pytest.mark.item("EC-E04")
def test_the_system_page_names_migrations_not_applied(
    seeded: Session,
    platform: Platform,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heads = service.head_revisions()
    monkeypatch.setattr(service, "head_revisions", lambda: heads | {"0999_future"})
    sign_in(db_client, "anil")
    html = db_client.get("/admin/system").text
    assert "1 migration not applied" in html
    assert "labra migrate" in html


@pytest.mark.item("EC-E04")
def test_only_staff_who_see_settings_see_the_system_page(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    sign_in(db_client, "priya")
    assert db_client.get("/admin/system").status_code == 403
    assert 'href="/admin/system"' not in db_client.get("/").text
