"""Code 128 bars for sample labels. python-barcode works out the pattern; the label
template draws it as SVG rectangles, so nothing here needs an image library."""

from dataclasses import dataclass

from barcode.codex import Code128

# 0.25 mm is two dots on a 203 dpi label printer and three on a 300 dpi one.
MODULE_MM = 0.25
# Code 128 needs ten clear modules on each side of the bars.
QUIET_MODULES = 10


@dataclass(frozen=True)
class Bars:
    """The black bars of one barcode as (start, width) in modules, quiet zones included."""

    text: str
    modules: int
    runs: tuple[tuple[int, int], ...]

    @property
    def width_mm(self) -> float:
        return self.modules * MODULE_MM


def code128(text: str) -> Bars:
    pattern = Code128(text).build()[0]
    runs: list[tuple[int, int]] = []
    start = None
    for at, module in enumerate(pattern + "0"):
        if module == "1" and start is None:
            start = at
        elif module != "1" and start is not None:
            runs.append((QUIET_MODULES + start, at - start))
            start = None
    return Bars(text, len(pattern) + 2 * QUIET_MODULES, tuple(runs))
