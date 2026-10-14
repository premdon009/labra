"""A document laid out inside the letterhead's content box (design §7.2).

Two outputs share one layout, so the text sits at the same place on both:
- `digital`: the letterhead is drawn on the page. An SVG or image is the `@page` background,
  stored once and reused by every page. A vector PDF is stamped under each page with pypdf,
  as one shared form object, so a 3-page report carries the letterhead once.
- `print`: no letterhead, for paper that already has it printed, shifted by the branch's
  printer offset so the text lands inside the printed frame.

A document with a running header or footer (a report's patient band, its page numbers) asks
for room for them inside the content box with `reserve`; they print in the page margin boxes.
A long document can be laid out more than once (`compose_paged`), so a table that runs onto
another page can be split there and its heading marked "(continued)".
"""

import io
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.errors import PdfReadError
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)
from weasyprint import Document

from labra.core.errors import ValidationFailedError
from labra.printing.pdf import FILE, FileReader, Rendered, layout, render_pdf

OUTPUTS = ("digital", "print")
A4_PT = (595.28, 841.89)
PT_PER_MM = 72 / 25.4
_A4_TOLERANCE_PT = 3
_STAMP = "/LabraLetterhead"
NO_RESERVE = (Decimal(0), Decimal(0))
# Rows that may carry over to another page have the id `split:<table key>:<row index>`.
SPLIT_ID = "split:"
# For each table key, the row indices that start a new page, in order.
Splits = Mapping[str, tuple[int, ...]]
MAX_PASSES = 4


@dataclass(frozen=True)
class PageSpec:
    """The content box and the letterhead file for one document."""

    margin_top_mm: Decimal
    margin_bottom_mm: Decimal
    margin_left_mm: Decimal
    margin_right_mm: Decimal
    signature_area_mm: Decimal
    font_size_pt: Decimal
    file_id: uuid.UUID | None = None
    file_type: str | None = None
    apply_on: str = "all"
    page_size: str = "A4"


# Used when a branch has published no layout: the built-in header prints inside these margins.
BUILTIN = PageSpec(
    margin_top_mm=Decimal(15),
    margin_bottom_mm=Decimal(20),
    margin_left_mm=Decimal(15),
    margin_right_mm=Decimal(15),
    signature_area_mm=Decimal(30),
    font_size_pt=Decimal(10),
)
# A5 has no letterhead file of its own: always the built-in header, inside fixed margins.
A5 = PageSpec(
    margin_top_mm=Decimal(10),
    margin_bottom_mm=Decimal(12),
    margin_left_mm=Decimal(10),
    margin_right_mm=Decimal(10),
    signature_area_mm=Decimal(22),
    font_size_pt=Decimal(9),
    page_size="A5",
)


def _num(value: Decimal) -> str:
    """A CSS number with no exponent and no trailing zeros: 40, 12.5."""
    text = f"{Decimal(value):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def page_css(spec: PageSpec, output: str, reserve: tuple[Decimal, Decimal] = NO_RESERVE) -> str:
    """Page size, margins and font size, plus the letterhead background for a digital SVG
    or image letterhead. Templates size their signatory block with `.signature-area`.
    `reserve` is the room (top, bottom) a running header and footer take from the content
    box; they print in the margin boxes, just inside the letterhead's margins."""
    top, right = _num(spec.margin_top_mm + reserve[0]), _num(spec.margin_right_mm)
    bottom, left = _num(spec.margin_bottom_mm + reserve[1]), _num(spec.margin_left_mm)
    css = [
        f"@page {{ size: {spec.page_size}; margin: {top}mm {right}mm {bottom}mm {left}mm; }}",
        f"html {{ font-size: {_num(spec.font_size_pt)}pt; }}",
        f".signature-area {{ height: {_num(spec.signature_area_mm)}mm; }}",
    ]
    if output == "digital" and spec.file_id is not None and spec.file_type in {"svg", "raster"}:
        # The page background is placed from the content box, so it is pulled back by the
        # margins to cover the whole sheet.
        selector = "@page :first" if spec.apply_on == "first" else "@page"
        css.append(
            f"{selector} {{ background: url({FILE}{spec.file_id}) no-repeat -{left}mm -{top}mm;"
            " background-size: 210mm 297mm; }"
        )
    return "\n".join(css)


def _refuse(message: str, field: str) -> ValidationFailedError:
    return ValidationFailedError({field: message})


def _is_a4_portrait(page: PageObject) -> bool:
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    return abs(width - A4_PT[0]) <= _A4_TOLERANCE_PT and abs(height - A4_PT[1]) <= _A4_TOLERANCE_PT


def prepare_pdf_letterhead(data: bytes, *, field: str = "file") -> bytes:
    """The first page of a vector PDF letterhead, without links, actions or anything else
    the document carried, or ValidationFailedError."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise _refuse("This PDF is password-protected. Save it without a password.", field)
        page = reader.pages[0]
    except (PdfReadError, IndexError, ValueError, KeyError) as exc:
        raise _refuse("This PDF can't be read.", field) from exc
    if page.rotation % 360 or not _is_a4_portrait(page):
        raise _refuse(
            "The letterhead PDF's first page is not A4 portrait. Export it at A4 (210 x 297 mm),"
            " upright.",
            field,
        )
    writer = PdfWriter()
    kept = writer.add_page(page)
    for key in ("/Annots", "/AA"):
        if key in kept:
            del kept[key]
    kept.compress_content_streams()
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _stamp_page(writer: PdfWriter, letterhead: bytes) -> PageObject:
    """The letterhead page as one form object in `writer`, and a blank page that draws it,
    for merging under each page."""
    source = PdfReader(io.BytesIO(letterhead)).pages[0]
    form = DecodedStreamObject()
    contents = source.get_contents()
    form.set_data(contents.get_data() if contents is not None else b"")
    form.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject(source.mediabox),
            NameObject("/Resources"): source.get("/Resources", DictionaryObject()),
        }
    )
    # pypdf has no public call to add a new indirect object.
    ref = writer._add_object(form.flate_encode().clone(writer))
    wrapper = PageObject.create_blank_page(None, *A4_PT)
    resources = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject(_STAMP): ref})}
    )
    wrapper[NameObject("/Resources")] = resources
    draw = DecodedStreamObject()
    draw.set_data(f"q {_STAMP} Do Q".encode())
    wrapper.replace_contents(draw.flate_encode())
    return wrapper


def compose(
    html: str,
    spec: PageSpec,
    output: str,
    *,
    files: FileReader | None = None,
    offset_mm: tuple[Decimal, Decimal] = NO_RESERVE,
    stylesheets: Sequence[str] = (),
    reserve: tuple[Decimal, Decimal] = NO_RESERVE,
) -> Rendered:
    """The HTML as a PDF in the spec's content box, with the letterhead for `digital` or the
    printer offset for `print`."""
    if output not in OUTPUTS:
        raise ValueError(f"unknown output {output!r}")
    css = [page_css(spec, output, reserve)]
    rendered = render_pdf(html, files=files, stylesheets=stylesheets, css=css)
    return _finish(rendered, spec, output, files, offset_mm)


def splits_in(document: Document) -> dict[str, tuple[int, ...]]:
    """Where each split table runs onto a new page: the index of its first row on every page
    after the one it starts on."""
    first_on_page: dict[str, list[int]] = {}
    for page in document.pages:
        here: dict[str, int] = {}
        for anchor in page.anchors:
            if not anchor.startswith(SPLIT_ID):
                continue
            key, _, index = anchor.removeprefix(SPLIT_ID).rpartition(":")
            if key and index.isdigit():
                here[key] = min(here.get(key, int(index)), int(index))
        for key, index in here.items():
            first_on_page.setdefault(key, []).append(index)
    return {key: tuple(i for i in starts[1:] if i > 0) for key, starts in first_on_page.items()}


def compose_paged(
    build: Callable[[Splits], str],
    spec: PageSpec,
    output: str,
    *,
    files: FileReader | None = None,
    offset_mm: tuple[Decimal, Decimal] = NO_RESERVE,
    stylesheets: Sequence[str] = (),
    reserve: tuple[Decimal, Decimal] = NO_RESERVE,
) -> Rendered:
    """Like `compose`, for a document whose tables may run over pages. `build` returns the
    HTML for the splits found so far; it starts each part after a split on a new page, under
    a heading marked as continued. Splitting at the row where the page broke anyway leaves the
    earlier pages as they were, so a few passes find every split."""
    if output not in OUTPUTS:
        raise ValueError(f"unknown output {output!r}")
    css = [page_css(spec, output, reserve)]
    splits: dict[str, tuple[int, ...]] = {}
    document, fetcher = layout(build(splits), files=files, stylesheets=stylesheets, css=css)
    for _ in range(MAX_PASSES - 1):
        found = splits_in(document)
        merged = {
            key: tuple(sorted(set(splits.get(key, ())) | set(found.get(key, ()))))
            for key in splits.keys() | found.keys()
        }
        merged = {key: rows for key, rows in merged.items() if rows}
        if merged == splits:
            break
        splits = merged
        document, fetcher = layout(build(splits), files=files, stylesheets=stylesheets, css=css)
    pdf = document.write_pdf()
    if pdf is None:  # only when writing to a target
        raise RuntimeError("WeasyPrint returned no PDF bytes")
    rendered = Rendered(pdf=pdf, pages=len(document.pages), refused=tuple(fetcher.refused))
    return _finish(rendered, spec, output, files, offset_mm)


def _finish(
    rendered: Rendered,
    spec: PageSpec,
    output: str,
    files: FileReader | None,
    offset_mm: tuple[Decimal, Decimal],
) -> Rendered:
    """The letterhead stamped under a digital copy, or the printer offset on a print copy."""
    stamp = output == "digital" and spec.file_type == "pdf" and spec.file_id is not None
    shift = output == "print" and any(offset_mm)
    if not stamp and not shift:
        return rendered
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(rendered.pdf)))
    if stamp and files is not None and spec.file_id is not None:
        wrapper = _stamp_page(writer, files(spec.file_id)[1])
        pages = writer.pages[:1] if spec.apply_on == "first" else writer.pages
        for page in pages:
            page.merge_page(wrapper, over=False)
    if shift:
        dx, dy = (float(v) * PT_PER_MM for v in offset_mm)
        for page in writer.pages:
            # Down on paper is down the page, which is negative y in PDF space.
            page.add_transformation(Transformation().translate(dx, -dy))
    for page in writer.pages:
        page.compress_content_streams()  # pypdf leaves edited content uncompressed
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    out = io.BytesIO()
    writer.write(out)
    return Rendered(pdf=out.getvalue(), pages=rendered.pages, refused=rendered.refused)
