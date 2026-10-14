"""Letterhead images made small and safe to draw.

A phone photo or a designer's export can be tens of megabytes, carry EXIF, colour profiles
and an alpha channel, or be WebP, which not every PDF reader shows. The image is decoded,
turned upright, checked for A4 portrait shape, scaled to A4 at the chosen resolution, laid on
white, and re-encoded as JPEG and as a 256-colour PNG; the smaller one is kept. Re-encoding
keeps only pixels, so nothing hidden in the original file reaches a PDF.
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from labra.core.errors import ValidationFailedError

A4_MM = (210, 297)
# A4 portrait is 1 : 1.414; a scan or export a little off that is still accepted.
ASPECT_TOLERANCE = 0.03
# Decoding is refused above this many pixels (a 600 dpi A4 scan is about 35 million).
MAX_PIXELS = 50_000_000


@dataclass(frozen=True)
class Optimised:
    data: bytes
    mime: str
    size: tuple[int, int]


def a4_pixels(dpi: int) -> tuple[int, int]:
    """A4 at `dpi`, in pixels: 1240 x 1754 at 150 dpi."""
    return tuple(round(mm / 25.4 * dpi) for mm in A4_MM)  # type: ignore[return-value]


def _refuse(message: str, field: str) -> ValidationFailedError:
    return ValidationFailedError({field: message})


def _open(data: bytes, field: str) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
        if width * height > MAX_PIXELS:
            raise _refuse("This image is too large to use. Save it at A4, 300 dpi or less.", field)
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise _refuse("This image can't be read.", field) from exc
    return image


def _on_white(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA", "PA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        white = Image.new("RGB", rgba.size, "white")
        white.paste(rgba, mask=rgba.getchannel("A"))
        return white
    return image.convert("RGB")


def _encode(image: Image.Image) -> tuple[bytes, str]:
    jpeg = io.BytesIO()
    image.save(jpeg, "JPEG", quality=80, optimize=True, progressive=True)
    png = io.BytesIO()
    image.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(png, "PNG", optimize=True)
    if len(png.getvalue()) < len(jpeg.getvalue()):
        return png.getvalue(), "image/png"
    return jpeg.getvalue(), "image/jpeg"


def optimise_raster(data: bytes, dpi: int, *, field: str = "file") -> Optimised:
    """The letterhead image at A4 and `dpi`, re-encoded, or ValidationFailedError."""
    image = ImageOps.exif_transpose(_open(data, field))
    width, height = image.size
    expected = A4_MM[1] / A4_MM[0]
    if abs(height / width - expected) / expected > ASPECT_TOLERANCE:
        raise _refuse(
            f"The image is {width} x {height} pixels, which is not A4 portrait. Export the"
            " whole page at A4 size (for example 2480 x 3508 pixels).",
            field,
        )
    target = a4_pixels(dpi)
    image = _on_white(image)
    if image.size != target:
        image = image.resize(target, Image.Resampling.LANCZOS)
    encoded, mime = _encode(image)
    return Optimised(data=encoded, mime=mime, size=target)
