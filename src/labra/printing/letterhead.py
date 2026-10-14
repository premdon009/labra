"""A document laid out inside the letterhead's content box (design §7.2).

Two outputs share one layout, so the text sits at the same place on both:
- `digital`: the letterhead is drawn on the page. An SVG or image is the `@page` background,
  stored once and reused by every page. A vector PDF is stamped under each page with pypdf,
  as one shared form object, so a 3-page report carries the letterhead once.
- `print`: no letterhead, for paper that already has it printed, shifted by the branch's
  printer offset so the text lands inside the printed frame.
"""

import io
import uuid
from collections.abc import Sequence
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

from labra.core.errors import ValidationFailedError
from labra.printing.pdf import FILE, FileReader, Rendered, render_pdf

OUTPUTS = ("digital", "print")
A4_PT = (595.28, 841.89)
PT_PER_MM = 72 / 25.4
_A4_TOLERANCE_PT = 3
_STAMP = "/LabraLetterhead"


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


# Used when a branch has published no layout: the built-in header prints inside these margins.
BUILTIN = PageSpec(
    margin_top_mm=Decimal(15),
    margin_bottom_mm=Decimal(20),
    margin_left_mm=Decimal(15),
    margin_right_mm=Decimal(15),
    signature_area_mm=Decimal(30),
    font_size_pt=Decimal(10),
)


def _num(value: Decimal) -> str:
    """A CSS number with no exponent and no trailing zeros: 40, 12.5."""
    text = f"{Decimal(value):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def page_css(spec: PageSpec, output: str) -> str:
    """Page size, margins and font size, plus the letterhead background for a digital SVG
    or image letterhead. Templates size their signatory block with `.signature-area`."""
    top, right = _num(spec.margin_top_mm), _num(spec.margin_right_mm)
    bottom, left = _num(spec.margin_bottom_mm), _num(spec.margin_left_mm)
    css = [
        f"@page {{ size: A4; margin: {top}mm {right}mm {bottom}mm {left}mm; }}",
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
    offset_mm: tuple[Decimal, Decimal] = (Decimal(0), Decimal(0)),
    stylesheets: Sequence[str] = (),
) -> Rendered:
    """The HTML as a PDF in the spec's content box, with the letterhead for `digital` or the
    printer offset for `print`."""
    if output not in OUTPUTS:
        raise ValueError(f"unknown output {output!r}")
    rendered = render_pdf(html, files=files, stylesheets=stylesheets, css=[page_css(spec, output)])
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
