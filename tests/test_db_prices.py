"""Prices with history and branch overrides, and code-first search, against real Postgres."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from labra.auth import service as auth
from labra.auth.principal import Principal
from labra.catalog import service as catalog
from labra.catalog.models import Price, Test
from labra.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from labra.core.ids import utcnow
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.org.models import Branch
from labra.seed import DEMO_PASSWORD


def _as(db: Session, platform: Platform, username: str) -> Principal:
    signed = auth.login(db, platform.identity, username, DEMO_PASSWORD, "10.0.0.5", utcnow())
    return auth.principal_for(db, signed.session)


def _branch(db: Session, code: str) -> Branch:
    branch = db.scalar(select(Branch).where(Branch.code == code))
    assert branch is not None
    return branch


def _tests(db: Session, admin: Principal) -> dict[str, Test]:
    dept = catalog.save_department(db, admin, "Biochemistry", 20)
    made = {}
    for code, name, aliases in (
        ("hb", "Haemoglobin", ["hgb"]),
        ("hba1c", "Glycated haemoglobin (HbA1c)", ["a1c"]),
        ("lipid", "Lipid profile", ["lp"]),
        ("lft", "Liver function test", []),
        ("glu-f", "Glucose, fasting", ["fbs", "sf"]),
    ):
        made[code] = catalog.save_test(
            db,
            admin,
            catalog.TestInput(code=code, name=name, department_id=dept.id, aliases=aliases),
        )
    return made


# Prices


@pytest.mark.item("M06")
@pytest.mark.item("EC-K02")
def test_a_price_change_closes_the_old_row_and_is_audited(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    hb = _tests(seeded, admin)["hb"]
    first = catalog.set_price(seeded, admin, "test", hb.id, "150")
    second = catalog.set_price(seeded, admin, "test", hb.id, "180.50", reason="Kit cost")
    assert first.valid_to == second.valid_from
    assert catalog.price_at(seeded, "test", hb.id, None) == Decimal("180.50")
    assert catalog.price_at(seeded, "test", hb.id, None, first.valid_from) == Decimal(150)
    assert catalog.price_at(seeded, "test", hb.id, None, first.valid_from - timedelta(1)) is None
    assert [p.amount for p in catalog.price_history(seeded, admin, "test", hb.id)] == [
        Decimal("180.50"),
        Decimal(150),
    ]
    details = list(
        seeded.scalars(
            select(AuditLog.detail).where(AuditLog.action == "price.set").order_by(AuditLog.id)
        )
    )
    assert (details[1]["before"], details[1]["after"], details[1]["reason"]) == (
        "150.00",
        "180.50",
        "Kit cost",
    )


@pytest.mark.item("M07")
def test_price_row_at_names_the_row_a_bill_cites(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    lipid = _tests(seeded, admin)["lipid"]
    b2, b3 = _branch(seeded, "B2"), _branch(seeded, "B3")
    assert catalog.price_row_at(seeded, "test", lipid.id, b2.id) is None
    lab = catalog.set_price(seeded, admin, "test", lipid.id, "600")
    own = catalog.set_price(seeded, admin, "test", lipid.id, "500", branch_id=b2.id)
    at_b2 = catalog.price_row_at(seeded, "test", lipid.id, b2.id)
    at_b3 = catalog.price_row_at(seeded, "test", lipid.id, b3.id)
    assert at_b2 is not None and at_b2.id == own.id
    assert at_b3 is not None and at_b3.id == lab.id


@pytest.mark.item("M06")
def test_a_branch_override_wins_at_that_branch_only(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    lipid = _tests(seeded, admin)["lipid"]
    b2, b3 = _branch(seeded, "B2"), _branch(seeded, "B3")
    catalog.set_price(seeded, admin, "test", lipid.id, "600")
    catalog.set_price(seeded, admin, "test", lipid.id, "500", branch_id=b2.id)
    assert catalog.price_at(seeded, "test", lipid.id, b2.id) == Decimal(500)
    assert catalog.price_at(seeded, "test", lipid.id, b3.id) == Decimal(600)
    catalog.set_price(seeded, admin, "test", lipid.id, "650")
    assert catalog.price_at(seeded, "test", lipid.id, b2.id) == Decimal(500)
    catalog.end_branch_price(seeded, admin, "test", lipid.id, b2.id)
    assert catalog.price_at(seeded, "test", lipid.id, b2.id) == Decimal(650)
    with pytest.raises(NotFoundError):
        catalog.end_branch_price(seeded, admin, "test", lipid.id, b2.id)
    open_rows = seeded.scalars(
        select(Price).where(Price.item_id == lipid.id, Price.valid_to.is_(None))
    ).all()
    assert len(open_rows) == 1


@pytest.mark.item("M06")
@pytest.mark.parametrize("amount", ["", "-1", "10.005", "ten"])
def test_bad_prices_are_refused(seeded: Session, platform: Platform, amount: str) -> None:
    admin = _as(seeded, platform, "anil")
    hb = _tests(seeded, admin)["hb"]
    with pytest.raises(ValidationFailedError) as exc:
        catalog.set_price(seeded, admin, "test", hb.id, amount)
    assert "amount" in exc.value.errors


@pytest.mark.item("M06")
def test_only_price_editors_set_prices(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    hb = _tests(seeded, admin)["hb"]
    for username in ("priya", "suresh", "meera", "b3desk"):
        with pytest.raises(PermissionDeniedError):
            catalog.set_price(seeded, _as(seeded, platform, username), "test", hb.id, "100")


# Search


@pytest.mark.item("M05.1")
def test_search_ranks_exact_code_then_alias_prefix_then_name(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    tests = _tests(seeded, admin)
    catalog.set_price(seeded, admin, "test", tests["hb"].id, "120")
    desk = _as(seeded, platform, "priya")

    hits = catalog.search(seeded, desk, "HB", _branch(seeded, "B2").id)
    assert [h.code for h in hits][:2] == ["hb", "hba1c"]
    assert hits[0].price == Decimal(120)
    assert catalog.search(seeded, desk, "fbs")[0].code == "glu-f"
    assert catalog.search(seeded, desk, "s")[0].code == "glu-f"  # alias prefix
    assert catalog.search(seeded, desk, "liver")[0].code == "lft"
    assert catalog.search(seeded, desk, "haemoglobn")[0].code == "hb"  # typo, by trigram
    assert catalog.search(seeded, desk, "  ") == []
    assert catalog.search(seeded, desk, "100%_") == []


@pytest.mark.item("M05.1")
def test_search_finds_packages_and_skips_inactive_tests(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    tests = _tests(seeded, admin)
    catalog.save_package(
        seeded, admin, "lft+lp", "Liver and lipid", [t.id for t in (tests["lft"], tests["lipid"])]
    )
    lft = tests["lft"]
    data = catalog.TestInput(
        code="lft", name=lft.name, department_id=lft.department_id, is_active=False
    )
    catalog.save_test(seeded, admin, data, lft.id, lft.row_version)
    hits = catalog.search(seeded, admin, "lft")
    assert [(h.item_type, h.code) for h in hits] == [("package", "lft+lp")]


@pytest.mark.item("EC-F02")
def test_name_search_uses_the_trigram_index(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    _tests(seeded, admin)
    # A handful of rows would be read by a sequential scan anyway; forbid it to see the plan.
    seeded.execute(text("set local enable_seqscan = off"))
    for index, sql in (
        ("ix_test_name_trgm", "explain select id from test where name % :q or name ilike :like"),
        (
            "ix_package_name_trgm",
            "explain select id from package where name % :q or name ilike :like",
        ),
    ):
        plan = "\n".join(seeded.scalars(text(sql), {"q": "haemoglobn", "like": "%haemo%"}))
        assert index in plan, plan
    plan = "\n".join(
        seeded.scalars(text("explain select id from test where aliases @> array['hgb']::varchar[]"))
    )
    assert "ix_test_aliases" in plan, plan
