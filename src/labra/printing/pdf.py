"""HTML to PDF with WeasyPrint, fetching nothing from the network.

Templates name their resources with two schemes only:
- `labra-asset:<path>`: a file under `labra/static` (vendored fonts, print CSS);
- `labra-file:<uuid>`: a stored file (letterhead, signature), read through the caller's reader.

`data:` URIs are allowed too. Every other URL (`http:`, `https:`, `file:`, `ftp:` …) is refused
before anything is opened, and recorded, so a letterhead or a template can never make the
server fetch or read anything else.
"""

import mimetypes
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.request import DataHandler, Request

from weasyprint import CSS, HTML, Document
from weasyprint.text.fonts import FontConfiguration
from weasyprint.urls import URLFetcher, URLFetcherResponse

ASSET = "labra-asset:"
FILE = "labra-file:"
STATIC = Path(__file__).resolve().parent.parent / "static"
BASE_CSS = f"{ASSET}pdf/base.css"

# A stored file's content type and bytes, by its id.
FileReader = Callable[[uuid.UUID], tuple[str, bytes]]


class FetchRefusedError(ValueError):
    """A template or letterhead named a URL the renderer will not open."""


class Fetcher(URLFetcher):
    """WeasyPrint's fetcher with the network and the file system taken away."""

    def __init__(self, files: FileReader | None = None) -> None:
        super().__init__(allowed_protocols=())
        self.files = files
        self.refused: list[str] = []

    def fetch(self, url: str, headers: object = None) -> URLFetcherResponse:
        if url.startswith(ASSET):
            return self._asset(url)
        if url.startswith(FILE) and self.files is not None:
            return self._file(url, self.files)
        if url.startswith("data:"):
            # Decoded in memory by urllib's data: handler; nothing is opened.
            response = DataHandler().data_open(Request(url))  # noqa: S310 - data: only
            return URLFetcherResponse(url, response.read(), dict(response.headers))
        return self._refuse(url)

    def _asset(self, url: str) -> URLFetcherResponse:
        path = (STATIC / url.removeprefix(ASSET)).resolve()
        if not path.is_relative_to(STATIC) or not path.is_file():
            return self._refuse(url)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return URLFetcherResponse(url, path.read_bytes(), {"Content-Type": mime})

    def _file(self, url: str, files: FileReader) -> URLFetcherResponse:
        try:
            file_id = uuid.UUID(url.removeprefix(FILE))
        except ValueError:
            return self._refuse(url)
        mime, data = files(file_id)
        return URLFetcherResponse(url, data, {"Content-Type": mime})

    def _refuse(self, url: str) -> URLFetcherResponse:
        self.refused.append(url[:200])
        raise FetchRefusedError(f"not fetched: {url[:200]}")


@dataclass(frozen=True)
class Rendered:
    pdf: bytes
    pages: int
    refused: tuple[str, ...]


def layout(
    html: str,
    *,
    files: FileReader | None = None,
    stylesheets: Sequence[str] = (),
) -> tuple[Document, Fetcher]:
    """Lay the HTML out into pages, with the vendored fonts and the base print CSS."""
    fetcher = Fetcher(files=files)
    fonts = FontConfiguration()
    sheets = [
        CSS(url=url, url_fetcher=fetcher, font_config=fonts) for url in (BASE_CSS, *stylesheets)
    ]
    document = HTML(string=html, url_fetcher=fetcher).render(stylesheets=sheets, font_config=fonts)
    return document, fetcher


def render_pdf(
    html: str,
    *,
    files: FileReader | None = None,
    stylesheets: Sequence[str] = (),
) -> Rendered:
    document, fetcher = layout(html, files=files, stylesheets=stylesheets)
    pdf = document.write_pdf()
    if pdf is None:  # only when writing to a target
        raise RuntimeError("WeasyPrint returned no PDF bytes")
    return Rendered(pdf=pdf, pages=len(document.pages), refused=tuple(fetcher.refused))
