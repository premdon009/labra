"""The one module that knows the database is PostgreSQL.

Domain code reaches every Postgres-only type, function and lock through the names here, never
through `sqlalchemy.dialects` or a Postgres function called by name, so moving to another engine
changes this module, the models' index options and the migrations, and nothing else.
`scripts/check_services.py` enforces that; docs/dev/services.md lists what ties Labra to
PostgreSQL.
"""

from typing import Any

from sqlalchemy import ColumnElement, Select, SQLColumnExpression, String, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, distinct_on
from sqlalchemy.orm import Session

# Column types for models. `StringList(String(20))` is a list of short strings in one column.
Json = JSONB
StringList = ARRAY


# Locks


def advisory_lock(db: Session, key: int) -> None:
    """Wait for the lock numbered `key` and hold it until the transaction ends."""
    db.execute(text("select pg_advisory_xact_lock(:k)"), {"k": key})


def advisory_lock_for(db: Session, name: str) -> None:
    """Wait for the lock named by any text and hold it until the transaction ends."""
    db.execute(text("select pg_advisory_xact_lock(hashtextextended(:name, 0))"), {"name": name})


# Fuzzy name search (pg_trgm). Both ignore case; the column's trigram index serves them.


def similar(column: SQLColumnExpression[str], term: str) -> ColumnElement[bool]:
    """True when the column's value looks like `term`, spelling variants included."""
    return column.op("%", is_comparison=True)(term)


def similarity(column: SQLColumnExpression[str], term: str) -> ColumnElement[Any]:
    """How alike the column's value and `term` are, from 0 to 1; for ordering and thresholds."""
    return func.similarity(column, term)


# Lists held in one column (StringList)


def list_contains(column: SQLColumnExpression[list[str]], item: str) -> ColumnElement[bool]:
    """True when the list holds `item`."""
    return column.contains([item])


def list_as_text(column: SQLColumnExpression[list[str]], sep: str = " ") -> ColumnElement[str]:
    """The list's items joined by `sep`, for matching text inside them."""
    return func.array_to_string(column, sep, type_=String)


def list_items(column: SQLColumnExpression[list[str]]) -> ColumnElement[str]:
    """Each item of the list as a row of its own, for use in a select."""
    return func.unnest(column, type_=String)


# Rows


def latest_per[*Ts](stmt: Select[*Ts], column: SQLColumnExpression[Any]) -> Select[*Ts]:
    """Keep only the first row for each value of `column`. Order the statement by `column`
    first, then newest first, so the row kept is the latest."""
    return stmt.ext(distinct_on(column))
