"""The letterhead on a PDF (design §7.2): the content box, digital and print copies that put
the text in the same place, a letterhead stored once however many pages, small files from
large pictures, and nothing fetched from outside."""

import io
import random
import uuid
from decimal import Decimal

import pdfplumber
import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.actions import JavaScript
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from labra.core.errors import ValidationFailedError
from labra.core.svg import sanitise_svg
from labra.core.uploads import JPEG, PNG, sniff
from labra.printing import samples
from labra.printing.images import a4_pixels, optimise_raster
from labra.printing.letterhead import PageSpec, compose, page_css, prepare_pdf_letterhead
from labra.printing.pdf import Rendered, render_pdf
from labra.printing.preview import page_pngs

MM = 72 / 25.4
D = Decimal


def _spec(file_id: uuid.UUID | None = None, file_type: str | None = None, **changes) -> PageSpec:
    values = {
        "margin_top_mm": D(40),
        "margin_bottom_mm": D(25),
        "margin_left_mm": D(15),
        "margin_right_mm": D(15),
        "signature_area_mm": D(30),
        "font_size_pt": D(10),
        "file_id": file_id,
        "file_type": file_type,
    }
    return PageSpec(**{**values, **changes})


def _render(spec: PageSpec, output: str = "digital", code: str = "three_pages", **kw) -> Rendered:
    return samples.render(code, spec, output, **kw)


def _picture(size: tuple[int, int] = (2480, 3508), mode: str = "RGB", fmt: str = "PNG") -> bytes:
    image = Image.new(mode, size, "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, size[0], size[1] // 9), fill=(20, 60, 140))
    draw.rectangle((0, size[1] - size[1] // 20, size[0], size[1]), fill=(20, 60, 140))
    out = io.BytesIO()
    image.save(out, fmt)
    return out.getvalue()


def _photo() -> bytes:
    """A busy A4 picture saved as a large JPEG, like a phone photo of the letterhead."""
    rng = random.Random(7)  # noqa: S311 - a fixed picture, not a secret
    width, height = 2480, 3508
    image = Image.linear_gradient("L").resize((width, height)).convert("RGB")
    draw = ImageDraw.Draw(image)
    for _ in range(400):
        x, y = rng.randrange(width), rng.randrange(height)
        colour = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
        draw.ellipse((x, y, x + rng.randrange(20, 200), y + rng.randrange(20, 200)), fill=colour)
    image = Image.blend(image, Image.effect_noise((width, height), 40).convert("RGB"), 0.15)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=95)
    return out.getvalue()


def _raster_letterhead() -> tuple[uuid.UUID, dict[uuid.UUID, tuple[str, bytes]]]:
    image = optimise_raster(_picture(), 150)
    file_id = uuid.uuid4()
    return file_id, {file_id: (image.mime, image.data)}


def _pdf_letterhead() -> bytes:
    html = (
        "<style>@page { size: A4; margin: 0 } div { height: 30mm; background: #124;"
        " color: white; font-size: 20pt }</style><div>SYNTHETIC LAB</div>"
    )
    return prepare_pdf_letterhead(render_pdf(html).pdf)


def _chars(pdf: bytes) -> list[list[tuple[str, float, float]]]:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return [
            [(c["text"], round(c["x0"], 1), round(c["top"], 1)) for c in page.chars]
            for page in doc.pages
        ]


def _images(pdf: bytes) -> set[int]:
    """The distinct image objects the pages draw, through any form objects."""
    found: set[int] = set()

    def walk(obj) -> None:
        for ref in obj.get("/Resources", {}).get("/XObject", {}).values():
            target = ref.get_object()
            if target.get("/Subtype") == "/Image":
                found.add(ref.idnum)
            elif target.get("/Subtype") == "/Form":
                walk(target)

    for page in PdfReader(io.BytesIO(pdf)).pages:
        walk(page)
    return found


def _forms(page) -> set[int]:
    return {
        ref.idnum
        for ref in page.get("/Resources", {}).get("/XObject", {}).values()
        if ref.get_object().get("/Subtype") == "/Form"
    }


@pytest.mark.item("M17")
@pytest.mark.item("EC-K03")
def test_text_stays_inside_the_content_box_on_every_page() -> None:
    file_id, files = _raster_letterhead()
    rendered = _render(_spec(file_id, "raster"), files=files.__getitem__)
    assert rendered.pages == 3
    with pdfplumber.open(io.BytesIO(rendered.pdf)) as doc:
        for page in doc.pages:
            assert page.chars
            assert min(c["x0"] for c in page.chars) >= 15 * MM - 0.5
            assert max(c["x1"] for c in page.chars) <= (210 - 15) * MM + 0.5
            assert min(c["top"] for c in page.chars) >= 40 * MM - 0.5
            assert max(c["bottom"] for c in page.chars) <= (297 - 25) * MM + 0.5


@pytest.mark.item("M17")
@pytest.mark.item("EC-K03")
def test_digital_and_print_put_every_character_in_the_same_place() -> None:
    file_id, files = _raster_letterhead()
    spec = _spec(file_id, "raster")
    digital = _render(spec, files=files.__getitem__)
    printed = _render(spec, "print", files=files.__getitem__)
    assert _chars(digital.pdf) == _chars(printed.pdf)
    assert _images(digital.pdf) and not _images(printed.pdf)

    lh_id = uuid.uuid4()
    pdf_files = {lh_id: ("application/pdf", _pdf_letterhead())}
    stamped = _render(_spec(lh_id, "pdf"), files=pdf_files.__getitem__)
    for on_digital, on_print in zip(_chars(stamped.pdf), _chars(printed.pdf), strict=True):
        assert set(on_print) <= set(on_digital)


@pytest.mark.item("M17")
@pytest.mark.item("EC-K03")
def test_an_image_letterhead_is_stored_once_and_extra_pages_cost_little() -> None:
    file_id, files = _raster_letterhead()
    spec = _spec(file_id, "raster")
    one = _render(spec, code="short", files=files.__getitem__)
    three = _render(spec, files=files.__getitem__)
    assert (one.pages, three.pages) == (1, 3)
    assert len(_images(three.pdf)) == 1
    assert len(three.pdf) <= len(one.pdf) + 100 * 1024


@pytest.mark.item("M17")
@pytest.mark.item("EC-K03")
def test_a_large_photo_letterhead_becomes_a_small_page() -> None:
    photo = _photo()
    assert len(photo) >= 2 * 1024 * 1024
    image = optimise_raster(photo, 150)
    assert image.size == a4_pixels(150) == (1240, 1754)
    file_id = uuid.uuid4()
    files = {file_id: (image.mime, image.data)}
    rendered = _render(_spec(file_id, "raster"), code="short", files=files.__getitem__)
    assert rendered.pages == 1
    assert len(rendered.pdf) <= 300 * 1024


@pytest.mark.item("EC-A07")
def test_a_webp_letterhead_is_converted() -> None:
    image = optimise_raster(_picture((1240, 1754), fmt="WEBP"), 150)
    assert image.mime in {JPEG, PNG}
    assert sniff(image.data) == image.mime
    with Image.open(io.BytesIO(image.data)) as decoded:
        assert decoded.format in {"JPEG", "PNG"}
        assert decoded.size == (1240, 1754)


@pytest.mark.item("EC-A07")
def test_a_picture_letterhead_loses_its_metadata_transparency_and_extra_resolution() -> None:
    exif = Image.Exif()
    exif[0x010F] = "Synthetic Camera"  # Make
    out = io.BytesIO()
    Image.new("RGB", (2480, 3508), "white").save(out, "JPEG", exif=exif.tobytes())
    image = optimise_raster(out.getvalue(), 200)
    with Image.open(io.BytesIO(image.data)) as decoded:
        assert decoded.size == a4_pixels(200)
        assert not decoded.getexif()
        assert "icc_profile" not in decoded.info
    clear = optimise_raster(_picture((1240, 1754), mode="RGBA"), 150)
    with Image.open(io.BytesIO(clear.data)) as decoded:
        assert decoded.convert("RGB").getpixel((600, 900)) == (255, 255, 255)


@pytest.mark.item("EC-A07")
@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_picture((1754, 1240)), "not A4 portrait"),
        (_picture((1000, 1000)), "not A4 portrait"),
        (b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" + b"\0" * 40, "can't be read"),
    ],
)
def test_a_picture_that_is_not_an_a4_page_is_refused(data: bytes, message: str) -> None:
    with pytest.raises(ValidationFailedError) as refused:
        optimise_raster(data, 150)
    assert message in refused.value.errors["file"]


@pytest.mark.item("M17")
def test_a_pdf_letterhead_is_stored_once_for_every_page() -> None:
    lh_id = uuid.uuid4()
    files = {lh_id: ("application/pdf", _pdf_letterhead())}
    rendered = _render(_spec(lh_id, "pdf"), files=files.__getitem__)
    pages = PdfReader(io.BytesIO(rendered.pdf)).pages
    shared = [_forms(page) for page in pages]
    assert len(shared) == 3
    assert len(shared[0]) == 1
    assert shared[0] == shared[1] == shared[2]
    assert all("SYNTHETIC LAB" in (page.extract_text() or "") for page in pages)

    first = _render(_spec(lh_id, "pdf", apply_on="first"), files=files.__getitem__)
    texts = [p.extract_text() or "" for p in PdfReader(io.BytesIO(first.pdf)).pages]
    assert ["SYNTHETIC LAB" in t for t in texts] == [True, False, False]


@pytest.mark.item("EC-A07")
def test_a_pdf_letterhead_keeps_only_its_first_page_without_links_or_actions() -> None:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(render_pdf("<p>One</p><p>Two</p>").pdf)))
    writer.add_blank_page()
    page = writer.pages[0]
    link = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): ArrayObject([]),
        }
    )
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(link)])
    page[NameObject("/AA")] = DictionaryObject()
    writer.add_open_action(JavaScript("app.alert('synthetic');"))
    assert "/Names" in writer.root_object
    out = io.BytesIO()
    writer.write(out)

    kept = PdfReader(io.BytesIO(prepare_pdf_letterhead(out.getvalue())))
    assert len(kept.pages) == 1
    assert "/Annots" not in kept.pages[0] and "/AA" not in kept.pages[0]
    root = kept.root_object
    assert "/Names" not in root and "/OpenAction" not in root


@pytest.mark.item("EC-A07")
def test_a_pdf_letterhead_that_is_locked_or_not_a4_portrait_is_refused() -> None:
    landscape = render_pdf("<style>@page { size: A4 landscape }</style><p>x</p>").pdf
    locked = PdfWriter(clone_from=PdfReader(io.BytesIO(_pdf_letterhead())))
    locked.encrypt("synthetic")
    out = io.BytesIO()
    locked.write(out)
    for data, message in (
        (landscape, "not A4 portrait"),
        (out.getvalue(), "password-protected"),
        (b"%PDF-1.7\n%%EOF", "can't be read"),
    ):
        with pytest.raises(ValidationFailedError) as refused:
            prepare_pdf_letterhead(data)
        assert message in refused.value.errors["file"]


@pytest.mark.item("M17")
def test_the_printer_offset_moves_only_the_print_copy() -> None:
    offset = (D(5), D(-3))
    plain = _chars(_render(_spec(), "print", "short").pdf)[0]
    shifted = _chars(_render(_spec(), "print", "short", offset_mm=offset).pdf)[0]
    digital = _chars(_render(_spec(), "digital", "short", offset_mm=offset).pdf)[0]
    assert digital == plain
    assert len(shifted) == len(plain)
    for (text, x, top), (moved, mx, mtop) in zip(plain, shifted, strict=True):
        assert text == moved
        assert mx - x == pytest.approx(5 * MM, abs=0.2)
        assert mtop - top == pytest.approx(-3 * MM, abs=0.2)


@pytest.mark.item("EC-A07")
def test_an_svg_letterhead_is_drawn_without_fetching_anything() -> None:
    raw = (
        b"<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'"
        b" width='210mm' height='297mm' viewBox='0 0 210 297'>"
        b"<rect width='210' height='30' fill='#124'/>"
        b"<image xlink:href='http://example.invalid/logo.png' width='20' height='20'/>"
        b"<script>alert(1)</script></svg>"
    )
    file_id = uuid.uuid4()
    spec = _spec(file_id, "svg")
    unsafe = _render(spec, code="short", files=lambda _: ("image/svg+xml", raw))
    assert "http://example.invalid/logo.png" in unsafe.refused
    clean = sanitise_svg(raw)
    drawn = _render(spec, code="short", files=lambda _: ("image/svg+xml", clean.data))
    assert drawn.refused == ()
    assert drawn.pages == 1


@pytest.mark.item("M17")
def test_page_css_puts_the_background_on_digital_copies_only() -> None:
    file_id = uuid.uuid4()
    first = page_css(_spec(file_id, "raster", apply_on="first", margin_top_mm=D("42.5")), "digital")
    assert "margin: 42.5mm 15mm 25mm 15mm" in first
    assert f"@page :first {{ background: url(labra-file:{file_id}) no-repeat -15mm -42.5mm" in first
    assert "background" not in page_css(_spec(file_id, "raster"), "print")
    assert "background" not in page_css(_spec(file_id, "pdf"), "digital")
    with pytest.raises(ValueError, match="unknown output"):
        compose("<p>x</p>", _spec(), "fax")


@pytest.mark.item("M17")
def test_preview_pages_are_images() -> None:
    rendered = _render(_spec())
    pngs = page_pngs(rendered.pdf, limit=2)
    assert len(pngs) == 2
    for png in pngs:
        assert png.startswith(b"\x89PNG")
        with Image.open(io.BytesIO(png)) as image:
            width, height = image.size
            assert abs(width - 595.28 * 60 / 72) <= 1 and abs(height - 841.89 * 60 / 72) <= 1
