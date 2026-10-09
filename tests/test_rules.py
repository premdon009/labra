"""Pure rules with no database: passwords, permissions, numbering, hash chain, settings,
log scrubbing, IDs and the data model."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from labra.adapters.identity_local import LocalIdentity
from labra.auth.deps import tokens_match
from labra.auth.principal import Principal
from labra.core.audit import GENESIS, chain_hash
from labra.core.db import Base
from labra.core.errors import ConfigError, ValidationFailedError
from labra.core.ids import IST, lab_today, new_id
from labra.core.lab_settings import DEFINITIONS, coerce
from labra.core.logging import REDACTED, scrub_processor, scrub_text
from labra.core.numbering import financial_year, format_problems, render
from labra.models import __all__ as _tables  # noqa: F401  registers every table
from labra.org.permissions import PERMISSIONS, SYSTEM_ROLES

# Passwords


@pytest.mark.item("EC-A01")
@pytest.mark.parametrize(
    ("password", "ok"),
    [
        ("short", False),
        ("password123", False),
        ("PASSWORD123", False),
        ("x" * 129, False),
        ("correct horse battery", True),
        ("demo-password-1", True),
    ],
)
def test_password_policy(password: str, ok: bool) -> None:
    assert (LocalIdentity().password_problems(password) == []) is ok


@pytest.mark.item("EC-A04")
@pytest.mark.parametrize(
    ("expected", "submitted", "ok"),
    [("abc", "abc", True), ("abc", "abd", False), (None, "abc", False), ("abc", None, False)],
)
def test_tokens_match(expected: str | None, submitted: str | None, ok: bool) -> None:
    assert tokens_match(expected, submitted) is ok


# Permissions and branch scoping

B1, B2, B3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _principal(grants: dict[uuid.UUID, frozenset[str]], at: uuid.UUID | None) -> Principal:
    return Principal(uuid.uuid4(), "user", "A User", at, grants)


@pytest.mark.item("EC-A05")
def test_branch_permission_only_where_granted() -> None:
    p = _principal({B2: frozenset({"branch.view"})}, B2)
    assert p.can("branch.view")
    assert p.can("branch.view", B2)
    assert not p.can("branch.view", B3)
    assert p.branches_with("branch.view") == {B2}


@pytest.mark.item("EC-A05")
def test_current_branch_decides_default_scope() -> None:
    p = _principal({B2: frozenset({"setting.edit_branch"})}, B3)
    assert not p.can("setting.edit_branch")
    assert p.can("setting.edit_branch", B2)


@pytest.mark.item("M01.1")
def test_lab_permission_from_any_branch() -> None:
    p = _principal({B1: frozenset({"user.edit"}), B2: frozenset()}, B2)
    assert p.can("user.edit")
    assert p.branches_with("user.edit") == {B1, B2}


@pytest.mark.item("EC-A05")
def test_deny_by_default() -> None:
    p = _principal({B1: frozenset(PERMISSIONS)}, B1)
    assert not p.can("no.such.permission")
    assert p.branches_with("no.such.permission") == set()
    assert not _principal({}, None).can("branch.view")


@pytest.mark.item("M01.1")
def test_system_roles_use_known_permissions() -> None:
    assert set(SYSTEM_ROLES) >= {"admin", "front_desk", "branch_manager"}
    for role in SYSTEM_ROLES.values():
        assert set(role.permissions) <= set(PERMISSIONS)
    front_desk = SYSTEM_ROLES["front_desk"]
    assert not {"user.edit", "branch.edit", "setting.edit"} & set(front_desk.permissions)


# Numbering


@pytest.mark.item("W04")
@pytest.mark.parametrize(
    ("day", "fy"),
    [(date(2026, 3, 31), 2025), (date(2026, 4, 1), 2026), (date(2027, 1, 15), 2026)],
)
def test_financial_year_starts_in_april(day: date, fy: int) -> None:
    assert financial_year(day) == fy


@pytest.mark.item("W04")
def test_render_tokens() -> None:
    assert render("{BR}/BS/{FY2}/{SEQ:5}", "B2", 2026, 123) == "B2/BS/2627/00123"
    assert render("{BR}-{FY}-{SEQ:3}", "MAIN", 2099, 7) == "MAIN-2099-00-007"
    with pytest.raises(ConfigError):
        render("{XX}{SEQ:3}", "B2", 2026, 1)


@pytest.mark.item("W04")
def test_gst_numbers_limited_to_16_characters() -> None:
    assert format_problems("bos", "{BR}/BS/{FY2}/{SEQ:5}", "B2") == []
    # Too long for a four-letter branch code, or when the branch isn't known yet.
    assert format_problems("bos", "{BR}/BS/{FY2}/{SEQ:5}", "MAIN")
    assert format_problems("bos", "{BR}/BS/{FY2}/{SEQ:5}")
    assert format_problems("bos", "{BR}/BILL/{FY}/{SEQ:6}", "B2")
    # Non-GST documents may be longer.
    assert format_problems("visit", "{BR}/VISIT/{FY}/{SEQ:6}") == []


@pytest.mark.item("W04")
def test_gst_numbers_limited_characters() -> None:
    assert format_problems("tax_inv", "{BR}_{SEQ:5}")


@pytest.mark.item("W04")
def test_format_needs_sequence() -> None:
    assert format_problems("visit", "{BR}/V")


# Audit hash chain

AT = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)


def _hash(prev: str = GENESIS, **change: object) -> str:
    args: dict = {
        "prev_hash": prev,
        "at": AT,
        "user_id": None,
        "branch_id": None,
        "action": "branch.create",
        "entity": "branch",
        "entity_id": "1",
        "detail": {"code": "B2"},
    } | change
    return chain_hash(**args)


@pytest.mark.item("M15")
def test_chain_hash_is_stable_and_sensitive() -> None:
    assert _hash() == _hash()
    assert len(_hash()) == 64
    assert _hash(prev="1" * 64) != _hash()
    assert _hash(detail={"code": "B3"}) != _hash()
    assert _hash(action="branch.update") != _hash()
    assert _hash(at=AT + timedelta(seconds=1)) != _hash()


@pytest.mark.item("M15")
def test_chain_hash_ignores_timezone_and_key_order() -> None:
    assert _hash(at=AT.astimezone(IST)) == _hash()
    assert _hash(detail={"b": 1, "a": 2}) == _hash(detail={"a": 2, "b": 1})


# Data model


@pytest.mark.item("M15")
def test_no_fetal_sex_fields_anywhere() -> None:
    """PCPNDT Act: the system never records the sex of a fetus."""
    words = ("fetal", "foetal", "fetus", "foetus", "pndt")
    for table in Base.metadata.tables.values():
        for column in table.columns:
            name = f"{table.name}.{column.name}".lower()
            assert not any(w in name for w in words), name


@pytest.mark.item("W04")
def test_ids_and_lab_day() -> None:
    assert new_id().version == 7
    assert new_id() != new_id()
    assert isinstance(lab_today(), date)
    assert IST.utcoffset(None) == timedelta(hours=5, minutes=30)


@pytest.mark.item("W04")
def test_uuid7_fallback_without_stdlib(monkeypatch: pytest.MonkeyPatch) -> None:
    # Python 3.13 has no uuid.uuid7; the hand-built one must still be a sortable version 7.
    monkeypatch.delattr(uuid, "uuid7", raising=False)
    before = datetime.now(UTC).timestamp() * 1000
    first, second = new_id(), new_id()
    assert (first.version, first.variant) == (7, uuid.RFC_4122)
    assert first != second
    assert abs((first.int >> 80) - before) < 5_000


# Lab settings


@pytest.mark.item("W04")
def test_setting_coercion() -> None:
    tat = DEFINITIONS["visit.default_tat_hours"]
    assert coerce(tat, " 24 ") == 24
    for bad in ("abc", "0", "721"):
        with pytest.raises(ValidationFailedError):
            coerce(tat, bad)
    name = DEFINITIONS["lab.display_name"]
    assert coerce(name, "  Synthetic Lab ") == "Synthetic Lab"
    with pytest.raises(ValidationFailedError):
        coerce(name, "x" * 501)


# Logs


@pytest.mark.item("EC-E01")
def test_logs_scrub_personal_data() -> None:
    event = scrub_processor(
        None,
        "info",
        {
            "event": "sent to 9876543210 and someone@example.com",
            "password": "secret-value",
            "extra": {"phone": "x", "count": 3, "items": ["+91 9876543210"]},
        },
    )
    assert "9876543210" not in event["event"]
    assert "someone@example.com" not in event["event"]
    assert event["password"] == REDACTED
    assert event["extra"]["phone"] == REDACTED
    assert event["extra"]["count"] == 3
    assert event["extra"]["items"] == [REDACTED]
    # Not a mobile number: IDs and amounts stay readable.
    assert scrub_text("invoice 1234567890") == "invoice 1234567890"
