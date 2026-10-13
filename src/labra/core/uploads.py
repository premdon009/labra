"""Checks on a file a user uploads, before it is stored.

The type is read from the file's own first bytes, never from its name or the browser's
content type, so an HTML page renamed `result.pdf` is refused. Stored files are later served
as downloads with a fixed content type and a generated name; nothing uploaded is rendered or
run by Labra.
"""

from collections.abc import Callable, Collection

from labra.core.errors import ValidationFailedError
from labra.core.files import MAX_BYTES

PDF = "application/pdf"

# Markup a browser would render or run if the bytes ever reached it under the wrong type.
_ACTIVE_MARKUP = (b"<!doctype", b"<html", b"<script", b"<svg", b"<?xml")


def _is_pdf(data: bytes) -> bool:
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-1024:]:
        return False
    return not any(mark in data[:1024].lower() for mark in _ACTIVE_MARKUP)


_SNIFFERS: dict[str, Callable[[bytes], bool]] = {PDF: _is_pdf}
_NAMES = {PDF: "PDF"}


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
