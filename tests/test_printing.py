"""The PDF engine: vendored fonts, Indian scripts, and no fetching outside Labra."""

import io
import uuid

import pdfplumber
import pytest

from labra.printing.pdf import Fetcher, FetchRefusedError, render_pdf

TEXT = "Total ₹1,250.00 — रमेश कुमार"


def _text_and_fonts(pdf: bytes) -> tuple[str, set[str]]:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        text = "\n".join(page.extract_text() or "" for page in doc.pages)
        fonts = {ch["fontname"].split("+", 1)[-1] for page in doc.pages for ch in page.chars}
    return text, fonts


@pytest.mark.item("M17")
def test_rupee_sign_and_devanagari_come_back_out_of_the_pdf_in_the_vendored_fonts() -> None:
    rendered = render_pdf(f"<p>{TEXT}</p>")
    text, fonts = _text_and_fonts(rendered.pdf)
    assert TEXT in text
    assert fonts == {"Labra-Sans", "Labra-Devanagari"}
    assert rendered.pages == 1
    assert rendered.refused == ()


@pytest.mark.item("EC-A07")
@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid/x.png",
        "https://example.invalid/a.css",
        "file:///etc/passwd",
        "ftp://example.invalid/x",
        "labra-asset:../../../../etc/passwd",
        "labra-asset:/etc/passwd",
        "labra-file:not-a-uuid",
    ],
)
def test_a_template_or_letterhead_cannot_make_the_renderer_fetch_anything_else(url: str) -> None:
    html = (
        f"<link rel='stylesheet' href='{url}'><img src='{url}'>"
        f"<p style=\"background:url('{url}')\">x</p>"
    )
    rendered = render_pdf(html)
    assert url in rendered.refused
    with pytest.raises(FetchRefusedError):
        Fetcher().fetch(url)


@pytest.mark.item("M17")
def test_stored_files_come_through_the_callers_reader_and_data_uris_decode_in_memory() -> None:
    svg = (
        b"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        b"<rect width='10' height='10'/></svg>"
    )
    asked: list[uuid.UUID] = []

    def reader(file_id: uuid.UUID) -> tuple[str, bytes]:
        asked.append(file_id)
        return "image/svg+xml", svg

    file_id = uuid.uuid4()
    fetched = Fetcher(files=reader).fetch(f"labra-file:{file_id}")
    assert asked == [file_id]
    assert fetched.read() == svg
    rendered = render_pdf(
        f"<img src='labra-file:{file_id}'><img src='data:image/svg+xml,{svg.decode()}'>",
        files=reader,
    )
    assert rendered.refused == ()
    # Without a reader, stored files are refused too.
    assert f"labra-file:{file_id}" in render_pdf(f"<img src='labra-file:{file_id}'>").refused
