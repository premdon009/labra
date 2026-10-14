"""PDF pages as PNG images, for the letterhead editor's live preview.

PDFium is not safe to call from two threads at once, so every render holds one lock. A
preview is a few pages at screen resolution, which takes well under a second.
"""

import base64
import io
import threading

import pypdfium2

PREVIEW_DPI = 60
_LOCK = threading.Lock()


def page_pngs(pdf: bytes, *, dpi: int = PREVIEW_DPI, limit: int = 4) -> list[bytes]:
    """The first `limit` pages of the PDF as PNG images."""
    pngs: list[bytes] = []
    with _LOCK:
        document = pypdfium2.PdfDocument(pdf)
        try:
            for index in range(min(limit, len(document))):
                page = document[index]
                # The stub says int; PDFium takes any positive scale.
                image = page.render(scale=dpi / 72, may_draw_forms=False).to_pil()  # type: ignore[arg-type]
                out = io.BytesIO()
                image.convert("RGB").save(out, "PNG", optimize=True)
                pngs.append(out.getvalue())
                page.close()
        finally:
            document.close()
    return pngs


def data_uri(png: bytes) -> str:
    """An `img src` the page's CSP allows (`img-src 'self' data:`)."""
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
