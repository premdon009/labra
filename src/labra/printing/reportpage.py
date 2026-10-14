"""A patient report laid out on a letterhead: its template and stylesheet, and the room its
running patient band and page-number line take inside the letterhead's margins. The band
grows with long names, so it is laid out once on its own and measured first; it can then
never run up into the letterhead.

The values come from `labra.reports.content.view`, or from a made-up report in
`labra.printing.samples` for the letterhead preview, so the preview shows the real layout.
"""

from collections.abc import Mapping
from decimal import ROUND_UP, Decimal
from typing import Any

from labra.printing.letterhead import NO_RESERVE, PageSpec, Splits, compose_paged, page_css
from labra.printing.pdf import ASSET, FileReader, Rendered, layout
from labra.printing.templates import render_html
from labra.web.barcode import code128

TEMPLATE = "reports/report.html"
STYLESHEET = f"{ASSET}pdf/report.css"
FOOTER_MM = Decimal(7)
# Between the band and the first line of the page.
_GAP_MM = Decimal(2)
_MM_PER_PX = Decimal("25.4") / 96
# The visit barcode in the band is read off paper by a hand scanner, not a label printer.
BARCODE_MODULE_MM = 0.2


def barcode(text: str) -> dict[str, Any]:
    """Code 128 bars for the band, drawn by the template as SVG rectangles."""
    bars = code128(text)
    return {
        "text": text,
        "modules": bars.modules,
        "runs": [list(run) for run in bars.runs],
        "width_mm": round(bars.modules * BARCODE_MODULE_MM, 2),
    }


def _context(report: Mapping[str, Any], builtin: bool, **extra: Any) -> dict[str, Any]:
    return {
        "report": report,
        "builtin": builtin,
        "builtin_header": None,
        "splits": {},
        "guides": "",
        "measure": False,
    } | extra


def reserve(
    report: Mapping[str, Any], spec: PageSpec, builtin: bool, files: FileReader | None = None
) -> tuple[Decimal, Decimal]:
    """Room (top, bottom) for the running header, as tall as this report's band, and for the
    footer line."""
    html = render_html(TEMPLATE, **_context(report, builtin, measure=True))
    document, _ = layout(html, files=files, stylesheets=[STYLESHEET], css=[page_css(spec, "print")])
    anchors = document.pages[0].anchors
    height = Decimal(anchors["head-end"][1] - anchors["head-start"][1]) * _MM_PER_PX
    return height.quantize(Decimal("0.1"), ROUND_UP) + _GAP_MM, FOOTER_MM


def compose_report(
    report: Mapping[str, Any],
    spec: PageSpec,
    output: str,
    *,
    files: FileReader | None = None,
    offset_mm: tuple[Decimal, Decimal] = NO_RESERVE,
    guides: str = "",
) -> Rendered:
    """The report as a PDF on this layout. With no letterhead file the built-in header
    prints above the patient band on every page."""
    builtin = spec.file_id is None

    def build(splits: Splits) -> str:
        return render_html(TEMPLATE, **_context(report, builtin, splits=splits, guides=guides))

    return compose_paged(
        build,
        spec,
        output,
        files=files,
        offset_mm=offset_mm,
        stylesheets=[STYLESHEET],
        reserve=reserve(report, spec, builtin, files),
    )
