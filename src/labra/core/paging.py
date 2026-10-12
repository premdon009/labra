"""One page of a list. Lists are never loaded whole and never counted: a page fetches one
row more than it shows, and that extra row is how it knows there is a next page."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select
from sqlalchemy.orm import Session

PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
# Far beyond any real list; keeps OFFSET inside a Postgres bigint for a hand-typed URL.
MAX_PAGE = 1_000_000


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    number: int
    size: int
    has_next: bool

    @property
    def has_prev(self) -> bool:
        return self.number > 1


def page_of(
    db: Session, stmt: Select[*tuple[Any, ...]], page: int = 1, size: int = PAGE_SIZE
) -> Page[Any]:
    """Page `page` (from 1) of `stmt`, which must be ordered. A statement that selects one
    entity or column gives those; one that selects several gives tuples."""
    size = max(1, min(size, MAX_PAGE_SIZE))
    page = max(1, min(page, MAX_PAGE))
    result = db.execute(stmt.limit(size + 1).offset((page - 1) * size))
    if len(stmt.column_descriptions) == 1:
        rows: list[Any] = list(result.scalars())
    else:
        rows = [tuple(r) for r in result]
    return Page(rows[:size], page, size, len(rows) > size)
