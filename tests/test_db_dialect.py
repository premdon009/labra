"""The database seam: each Postgres-only helper in labra.core.dialect does what its name says."""

from collections.abc import Callable

import pytest
from sqlalchemy import Column, Engine, Integer, MetaData, String, Table, insert, select, text
from sqlalchemy.orm import Session

from labra.core.dialect import (
    EMPTY_JSON,
    Json,
    StringList,
    advisory_lock,
    advisory_lock_for,
    latest_per,
    list_as_text,
    list_contains,
    list_items,
    similar,
    similarity,
)

pytestmark = pytest.mark.item("W20")

metadata = MetaData()
rows = Table(
    "dialect_rows",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(80), nullable=False),
    Column("tags", StringList(String(20)), nullable=False),
    Column("grp", Integer, nullable=False),
    Column("at", Integer, nullable=False),
    Column("extra", Json, nullable=False, server_default=EMPTY_JSON),
    prefixes=["TEMPORARY"],
)


@pytest.fixture
def filled(db: Session) -> Session:
    metadata.create_all(db.connection())
    db.execute(
        insert(rows),
        [
            {"name": "Sunita Rao", "tags": ["CBC", "HB"], "grp": 1, "at": 1},
            {"name": "Sunitha Rao", "tags": ["TSH"], "grp": 1, "at": 3},
            {"name": "Kavya Menon", "tags": [], "grp": 2, "at": 2},
        ],
    )
    return db


def test_similar_finds_spelling_variants(filled: Session) -> None:
    found = filled.scalars(
        select(rows.c.name)
        .where(similar(rows.c.name, "sunita rao"))
        .order_by(similarity(rows.c.name, "sunita rao").desc())
    ).all()
    assert found == ["Sunita Rao", "Sunitha Rao"]


def test_json_column_defaults_to_an_empty_object(filled: Session) -> None:
    assert filled.scalars(select(rows.c.extra).order_by(rows.c.id)).all() == [{}, {}, {}]


def test_list_helpers(filled: Session) -> None:
    assert filled.scalars(select(rows.c.name).where(list_contains(rows.c.tags, "HB"))).all() == [
        "Sunita Rao"
    ]
    assert filled.scalars(select(list_as_text(rows.c.tags)).order_by(rows.c.id)).all() == [
        "CBC HB",
        "TSH",
        "",
    ]
    assert sorted(filled.scalars(select(list_items(rows.c.tags))).all()) == ["CBC", "HB", "TSH"]


def test_latest_per_keeps_the_first_row_of_each_group(filled: Session) -> None:
    stmt = latest_per(select(rows.c.grp, rows.c.at), rows.c.grp).order_by(
        rows.c.grp, rows.c.at.desc()
    )
    assert [tuple(r) for r in filled.execute(stmt)] == [(1, 3), (2, 2)]


@pytest.mark.parametrize(
    ("take", "probe"),
    [
        (lambda db: advisory_lock(db, 7_000_001), "select pg_try_advisory_xact_lock(7000001)"),
        (
            lambda db: advisory_lock_for(db, "dialect-test"),
            "select pg_try_advisory_xact_lock(hashtextextended('dialect-test', 0))",
        ),
    ],
)
def test_advisory_locks_hold_until_the_transaction_ends(
    pg_engine: Engine, take: Callable[[Session], None], probe: str
) -> None:
    with pg_engine.connect() as holder, pg_engine.connect() as other:
        with Session(bind=holder) as db:
            take(db)
            with other.begin():
                assert other.scalar(text(probe)) is False
            db.rollback()
        with other.begin():
            assert other.scalar(text(probe)) is True
