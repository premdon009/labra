"""Lists come a page at a time, without counting the rows."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth import service as auth
from labra.catalog import service as catalog
from labra.catalog.models import CommentPreset
from labra.core.ids import utcnow
from labra.core.paging import MAX_PAGE, MAX_PAGE_SIZE, page_of
from labra.core.registry import Platform
from labra.seed import DEMO_PASSWORD


@pytest.mark.item("EC-F03")
def test_page_of_caps_and_has_next(seeded: Session, platform: Platform) -> None:
    signed = auth.login(seeded, platform.identity, "anil", DEMO_PASSWORD, "10.0.0.5", utcnow())
    admin = auth.principal_for(seeded, signed.session)
    for i in range(26):
        catalog.save_preset(seeded, admin, f"Preset {i:02d}", "Synthetic comment.")
    stmt = select(CommentPreset).order_by(CommentPreset.label)
    first = page_of(seeded, stmt)
    assert (len(first.items), first.has_prev, first.has_next) == (25, False, True)
    assert first.items[0].label == "Preset 00"
    last = page_of(seeded, stmt, 2)
    assert [p.label for p in last.items] == ["Preset 25"]
    assert (last.has_prev, last.has_next) == (True, False)
    assert page_of(seeded, stmt, 1, size=10_000).size == MAX_PAGE_SIZE
    assert page_of(seeded, stmt, 1, size=0).size == 1
    assert page_of(seeded, stmt, -3).number == 1
    beyond = page_of(seeded, stmt, 10**30)
    assert (beyond.number, beyond.items, beyond.has_next) == (MAX_PAGE, [], False)
    pairs = page_of(seeded, select(CommentPreset.label, CommentPreset.id).order_by("label"), 2)
    assert pairs.items[0][0] == "Preset 25"
