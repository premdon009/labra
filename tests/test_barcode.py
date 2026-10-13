"""The Code 128 bars drawn on a sample label."""

import pytest

from labra.core.numbering import MAX_BRANCH_CODE
from labra.web.barcode import MODULE_MM, QUIET_MODULES, code128

LABEL_WIDTH_MM = 50
SIDE_MARGIN_MM = 2


@pytest.mark.item("M08")
def test_barcode_fits_label_width_longest_branch_code() -> None:
    longest = "W" * MAX_BRANCH_CODE + "2627" + "999999"

    bars = code128(longest)

    assert MODULE_MM == 0.25
    assert bars.width_mm <= LABEL_WIDTH_MM - 2 * SIDE_MARGIN_MM
    assert code128("MAIN2627000123").modules == 145 + 2 * QUIET_MODULES


@pytest.mark.item("M08")
def test_barcode_bars_keep_quiet_zones_and_never_touch() -> None:
    bars = code128("B22627000001")

    first, last = bars.runs[0], bars.runs[-1]
    assert first[0] == QUIET_MODULES
    assert last[0] + last[1] == bars.modules - QUIET_MODULES
    # Every Code 128 barcode opens with a 2-module bar and closes with a 2-module one.
    assert (first[1], last[1]) == (2, 2)
    for (start, width), (following, _) in zip(bars.runs, bars.runs[1:], strict=False):
        assert 1 <= width <= 4
        assert following > start + width
    assert code128("B22627000002").runs != bars.runs
