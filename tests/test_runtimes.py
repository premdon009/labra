"""What keeps Labra independent of one container runtime: tests on any Postgres, and a
`migrate` that waits for the database where Compose doesn't."""

import contextlib
from typing import cast

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import OperationalError

from labra.cli import main
from labra.core.config import get_settings
from labra.core.db import get_engine, wait_for_database
from labra.core.errors import LabraError
from tests.conftest import checked_test_url

pytestmark = pytest.mark.item("W17")

# Nothing listens on port 9 on localhost, so connections are refused at once.
REFUSED = "postgresql+psycopg://labra:not-a-real-pass@127.0.0.1:9/labra"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://labra:x@db.example/labra",
        "postgresql://labra:x@db.example/labra_testing",
        "postgresql://labra:x@db.example/",
    ],
)
def test_test_database_must_be_named_for_tests(url: str) -> None:
    with pytest.raises(pytest.UsageError, match="ending in _test") as caught:
        checked_test_url(url)
    assert "x@" not in str(caught.value)


def test_test_database_url_uses_psycopg() -> None:
    url = checked_test_url("postgresql://labra:x@db.example:5433/labra_test")
    assert url == "postgresql+psycopg://labra:x@db.example:5433/labra_test"


class FlakyEngine:
    """Refuses the first `failures` connections, like Postgres while it starts."""

    def __init__(self, failures: int) -> None:
        self.failures, self.calls = failures, 0

    def connect(self) -> contextlib.nullcontext[None]:
        self.calls += 1
        if self.calls <= self.failures:
            raise OperationalError("connect", {}, Exception("connection refused"))
        return contextlib.nullcontext()


def test_wait_retries_until_the_database_is_up() -> None:
    engine = FlakyEngine(failures=2)
    wait_for_database(cast(Engine, engine), timeout=5, interval=0.01)
    assert engine.calls == 3


def test_wait_gives_up_without_leaking_the_url() -> None:
    engine = create_engine(REFUSED)
    with pytest.raises(LabraError, match=r"not reachable after 0\.2 s") as caught:
        wait_for_database(engine, timeout=0.2, interval=0.05)
    assert "not-a-real-pass" not in str(caught.value)
    engine.dispose()


def test_wait_returns_at_once_when_up(pg_engine: Engine) -> None:
    wait_for_database(pg_engine, timeout=0)


def test_migrate_exits_1_when_the_database_never_comes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LABRA_DATABASE_URL", REFUSED)
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        with pytest.raises(SystemExit) as exited:
            main(["migrate", "--wait", "0.2"])
    finally:
        get_engine.cache_clear()
    assert exited.value.code == 1
    out = capsys.readouterr().out
    assert "not reachable" in out
    assert "not-a-real-pass" not in out
