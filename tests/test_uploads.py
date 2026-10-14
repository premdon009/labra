"""Upload checks: the type comes from the bytes, never from the file's name."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labra.core.errors import ValidationFailedError
from labra.core.uploads import JPEG, PDF, PNG, SVG, WEBP, check_upload, sniff

SMALL_PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF\n"
HTML = b"<!doctype html><html><body><script>alert(1)</script></body></html>"


def _refused(data: bytes, max_bytes: int = 1024 * 1024) -> str:
    with pytest.raises(ValidationFailedError) as caught:
        check_upload(data, allowed={PDF}, max_bytes=max_bytes)
    return caught.value.errors["file"]


@pytest.mark.item("EC-A07")
def test_a_pdf_is_recognised_by_its_bytes() -> None:
    assert sniff(SMALL_PDF) == PDF
    assert check_upload(SMALL_PDF, allowed={PDF}) == PDF


@pytest.mark.item("EC-A07")
@pytest.mark.parametrize(
    "data",
    [
        HTML,
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        b"\x89PNG\r\n\x1a\n" + b"\0" * 32,
        b"PK\x03\x04" + b"\0" * 32,
        b"MZ" + b"\0" * 64,
        b"plain text that says %PDF-1.7 and %%EOF",
        b"\n%PDF-1.7\n%%EOF",
        b"%PDF-1.7\nno end marker",
        b"%PDF-1.7\n<html><script>alert(1)</script></html>\n%%EOF",
    ],
)
def test_anything_that_is_not_a_pdf_is_refused_whatever_it_is_called(data: bytes) -> None:
    assert sniff(data) != PDF
    assert "not a PDF file" in _refused(data)


@pytest.mark.item("EC-A07")
def test_an_empty_file_and_one_over_the_cap_are_refused() -> None:
    assert _refused(b"") == "Choose a file to upload."
    padded = SMALL_PDF[:-6] + b" " * 2048 + b"%%EOF\n"
    assert check_upload(padded, allowed={PDF}, max_bytes=len(padded)) == PDF
    assert "larger than" in _refused(padded, max_bytes=len(padded) - 1)


@pytest.mark.item("EC-A07")
def test_a_type_that_is_recognised_but_not_wanted_is_refused() -> None:
    with pytest.raises(ValidationFailedError):
        check_upload(SMALL_PDF, allowed=set())


@pytest.mark.item("EC-A07")
@given(st.binary(max_size=200))
def test_bytes_that_do_not_start_as_a_pdf_never_pass(data: bytes) -> None:
    if not data.startswith(b"%PDF-"):
        assert sniff(data) != PDF


def _image(fmt: str) -> bytes:
    from io import BytesIO

    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (8, 8), "white").save(out, fmt)
    return out.getvalue()


@pytest.mark.item("EC-A07")
@pytest.mark.parametrize(("fmt", "mime"), [("PNG", PNG), ("JPEG", JPEG), ("WEBP", WEBP)])
def test_images_are_recognised_by_their_bytes(fmt: str, mime: str) -> None:
    data = _image(fmt)
    assert sniff(data) == mime
    assert check_upload(data, allowed={mime, PDF}) == mime
    with pytest.raises(ValidationFailedError):
        check_upload(data, allowed={PDF})


@pytest.mark.item("EC-A07")
def test_an_svg_is_recognised_only_when_it_parses_safely() -> None:
    assert sniff(b"<svg xmlns='http://www.w3.org/2000/svg'><rect width='1'/></svg>") == SVG
    entity_bomb = (
        b"<?xml version='1.0'?><!DOCTYPE svg [<!ENTITY a 'aaaa'>]>"
        b"<svg xmlns='http://www.w3.org/2000/svg'><text>&a;</text></svg>"
    )
    assert sniff(entity_bomb) is None
    assert sniff(b"<svg><rect/></svg>") is None  # no SVG namespace
    assert sniff(HTML) is None
