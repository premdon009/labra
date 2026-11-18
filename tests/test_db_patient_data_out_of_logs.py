"""EC-C03: a patient's name and phone stay out of the logs and out of addresses. Errors are
logged by type and place, never by message; searches are posted, never put in a URL; and the
proxies keep no access log of full addresses."""

import io
import logging
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from labra.adapters.errors_log import LogErrorReporter
from labra.core.logging import configure_logging
from labra.core.registry import Platform
from labra.patients import service as patients
from tests.frontdesk import as_user, post, register, sign_in

ROOT = Path(__file__).resolve().parent.parent
NAME = "Sunita Testcase"
PHONE = "9000000001"
_ADDRESSES = re.compile(r'(?:href|action|hx-get|hx-post|src)="([^"]*)"')


@pytest.fixture
def log_output(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    configure_logging("json", "INFO")
    try:
        yield out
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)


def _raised(exc: IntegrityError) -> IntegrityError:
    try:
        raise exc
    except IntegrityError as caught:
        return caught


@pytest.mark.item("EC-C03")
def test_an_error_is_logged_by_its_type_and_place_never_its_message(
    log_output: io.StringIO,
) -> None:
    # A database error's message carries the row it tried to write.
    params = {"full_name": NAME, "phone": PHONE}
    error = _raised(IntegrityError("INSERT INTO patient …", params, Exception("duplicate key")))
    LogErrorReporter().report(error, "ERR-TEST1", {"route": "/frontdesk/patients"})
    logged = log_output.getvalue()
    assert "ERR-TEST1" in logged
    assert "sqlalchemy.exc.IntegrityError" in logged
    assert "test_db_patient_data_out_of_logs.py:" in logged  # where it was raised
    assert NAME not in logged and "Testcase" not in logged
    assert PHONE not in logged
    assert "duplicate key" not in logged


@pytest.mark.item("EC-C03")
def test_a_failing_search_keeps_the_patient_out_of_the_logs(
    seeded: Session,
    platform: Platform,
    db_client: TestClient,
    log_output: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register(seeded, as_user(seeded, platform, "priya"))
    sign_in(db_client, "priya")

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"search failed for {args[2]!r}")

    monkeypatch.setattr(patients, "find_patients", broken)
    for typed in (NAME, PHONE):
        failed = post(db_client, "/frontdesk/patients/search", {"q": typed})
        assert failed.status_code == 500
        assert "reference number" in failed.text
    # The reporter got the errors with their messages; what the log one writes leaves them out.
    reports = platform.errors.reports  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    assert [NAME in str(exc) or PHONE in str(exc) for _, exc, _ in reports] == [True, True]
    for reference, exc, context in reports:  # pyright: ignore[reportUnknownVariableType]
        LogErrorReporter().report(exc, reference, context)  # pyright: ignore[reportUnknownArgumentType]
    logged = log_output.getvalue()
    assert logged.count('"unhandled_error"') == 2
    assert logged.count('"route": "/frontdesk/patients/search"') == 4  # requests and errors
    assert "builtins.RuntimeError" in logged
    assert NAME not in logged and "Testcase" not in logged
    assert PHONE not in logged


@pytest.mark.item("EC-C03")
def test_patient_searches_are_posted_so_no_address_holds_them(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    for n in range(30):  # enough for a second page
        register(seeded, as_user(seeded, platform, "priya"), phone=f"90000{n:05d}")
    sign_in(db_client, "priya")

    found = post(db_client, "/frontdesk/patients/search", {"q": NAME})
    assert found.status_code == 200
    assert found.text.count(NAME) >= 2
    second = post(db_client, "/frontdesk/patients/search", {"q": NAME, "page": "2"})
    assert "Page 2" in second.text
    for page in (found.text, second.text, db_client.get("/frontdesk/visits/new").text):
        addresses = _ADDRESSES.findall(page)
        assert addresses
        assert not [a for a in addresses if "Testcase" in a or "Sunita" in a or "90000" in a]
    assert 'form method="post" action="/frontdesk/patients/search"' in found.text
    assert 'name="page" value="2"' in found.text  # the pager posts the search again

    by_phone = post(db_client, "/frontdesk/visits/new/patient", {"phone": "9000000001"}).text
    assert NAME in by_phone
    assert db_client.get("/frontdesk/visits/new/patient?phone=9000000001").status_code == 405


@pytest.mark.item("EC-C03")
def test_the_proxies_keep_no_access_log_of_full_addresses() -> None:
    nginx = (ROOT / "deploy" / "nginx" / "labra.conf").read_text(encoding="utf-8")
    assert re.search(r"^access_log off;$", nginx, re.MULTILINE)
    caddy = (ROOT / "Caddyfile").read_text(encoding="utf-8")
    assert not re.search(r"^\s*log\b", caddy, re.MULTILINE)
