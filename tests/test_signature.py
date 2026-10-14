"""A signatory's signature image: a new small PNG made from the pixels alone."""

import io

import pytest
from PIL import Image, ImageDraw

from labra.core.errors import ValidationFailedError
from labra.core.uploads import PNG, sniff
from labra.printing.images import signature_png

pytestmark = pytest.mark.item("M12")


def _scan(size: tuple[int, int], mode: str = "RGB", fmt: str = "JPEG", **save: object) -> bytes:
    image = Image.new(mode, size, "white" if mode == "RGB" else (0, 0, 0, 0))
    ImageDraw.Draw(image).line(
        (10, size[1] // 2, size[0] - 10, size[1] // 3), fill="black", width=8
    )
    out = io.BytesIO()
    image.save(out, fmt, **save)
    return out.getvalue()


def test_a_phone_photo_becomes_a_small_png_without_its_metadata() -> None:
    exif = Image.Exif()
    exif[0x010F] = "Synthetic Camera Co"
    photo = _scan((3000, 1200), exif=exif.tobytes(), comment=b"hidden note")

    png = signature_png(photo)

    assert sniff(png) == PNG
    with Image.open(io.BytesIO(png)) as out:
        assert out.size == (500, 200)
        assert out.mode == "RGB"
        assert not out.getexif()
    assert b"Synthetic Camera" not in png and b"hidden note" not in png


def test_a_clear_background_stays_clear_and_a_small_image_is_not_enlarged() -> None:
    png = signature_png(_scan((300, 90), mode="RGBA", fmt="PNG"))

    with Image.open(io.BytesIO(png)) as out:
        assert out.size == (300, 90)
        assert out.mode == "RGBA"
        assert out.getpixel((0, 0))[3] == 0  # pyright: ignore[reportIndexIssue, reportOptionalSubscript]


def test_bytes_that_are_not_a_picture_are_refused() -> None:
    with pytest.raises(ValidationFailedError) as refused:
        signature_png(b"\x89PNG\r\n\x1a\n" + b"not really")
    assert "signature" in refused.value.errors
