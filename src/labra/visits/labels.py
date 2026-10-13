"""Which tubes a visit needs: one sample for each kind of specimen."""

import uuid
from collections.abc import Iterable

from labra.catalog.models import Test


def group_by_specimen(tests: Iterable[Test]) -> list[tuple[uuid.UUID | None, list[Test]]]:
    """Tests sharing a specimen type share a sample, in the order the types first appear.
    Tests with no specimen type set go together into one sample of their own."""
    groups: dict[uuid.UUID | None, list[Test]] = {}
    for test in tests:
        groups.setdefault(test.specimen_type_id, []).append(test)
    return list(groups.items())
