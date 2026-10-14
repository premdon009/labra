"""Checks on a file a user uploads, before it is stored.

The type is read from the file's own bytes, never from its name or the browser's content
type, so an HTML page renamed `result.pdf` is refused. Stored files are later served as
downloads with a fixed content type and a generated name. An uploaded SVG or image is only
ever drawn into a PDF, after `labra.core.svg` or the printing package has rebuilt it.
"""

from collections.abc import Callable, Collection

from labra.core.errors import ValidationFailedError
from labra.core.files import MAX_BYTES
from labra.core.svg import is_svg

PDF = "application/pdf"
SVG = "image/svg+xml"
PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"
IMAGES = frozenset({PNG, JPEG, WEBP})

# Markup a browser would render or run if the bytes ever reached it under the wrong type.
_ACTIVE_MARKUP = (b"<!doctype", b"<html", b"<script", b"<svg", b"<?xml")


def _is_pdf(data: bytes) -> bool:
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-1024:]:
        return False
    return not any(mark in data[:1024].lower() for mark in _ACTIVE_MARKUP)


def _is_png(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR")


def _is_jpeg(data: bytes) -> bool:
    # Start-of-image then a real segment marker, and an end-of-image marker near the end.
    return (
        len(data) > 4
        and data.startswith(b"\xff\xd8\xff")
        and data[3] in {0xC0, 0xC2, 0xC4, 0xDB, 0xFE} | set(range(0xE0, 0xF0))
        and b"\xff\xd9" in data[-1024:]
    )


def _is_webp(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:15] == b"WEBPVP8"


_SNIFFERS: dict[str, Callable[[bytes], bool]] = {
    PDF: _is_pdf,
    PNG: _is_png,
    JPEG: _is_jpeg,
    WEBP: _is_webp,
    SVG: is_svg,
}
_NAMES = {PDF: "PDF", PNG: "PNG", JPEG: "JPEG", WEBP: "WebP", SVG: "SVG"}


def sniff(data: bytes) -> str | None:
    """The type the bytes themselves show, or None when it is not one Labra knows."""
    for mime, matches in _SNIFFERS.items():
        if matches(data):
            return mime
    return None


def check_upload(
    data: bytes,
    *,
    allowed: Collection[str],
    max_bytes: int = MAX_BYTES,
    field: str = "file",
) -> str:
    """The sniffed content type of an upload, or ValidationFailedError saying what is wrong."""
    wanted = " or ".join(_NAMES.get(mime, mime) for mime in sorted(allowed))
    if not data:
        raise ValidationFailedError({field: "Choose a file to upload."})
    if len(data) > max_bytes:
        limit = max(1, max_bytes // (1024 * 1024))
        raise ValidationFailedError({field: f"The file is larger than {limit} MB."})
    mime = sniff(data)
    if mime is None or mime not in allowed:
        raise ValidationFailedError(
            {field: f"This is not a {wanted} file. Its name alone doesn't make it one."}
        )
    return mime
