"""The user manual, read from its Markdown pages and shown inside the app.

The pages are the ones the documentation site is built from (docs/manual), with the same
order (the site's nav in zensical.toml). The image carries both inside the package; a
checkout reads them from the repository. Nothing is fetched from the internet, so help
works in a lab whose line is down.
"""

import posixpath
import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import markdown

PACKAGE = Path(__file__).resolve().parent.parent
# Pages outside the manual (runbooks, developer notes) link to the documentation site.
SITE = "https://premdon009.github.io/labra/"
EXTENSIONS = ["admonition", "attr_list", "def_list", "footnotes", "md_in_html", "tables", "toc"]
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)
HREF = re.compile(r'(href|src)="([^"#:]*\.md)(#[^"]*)?"')


@dataclass(frozen=True)
class Page:
    name: str  # "admin/system"
    title: str
    section: str
    html: str


def manual_dir() -> Path:
    bundled = PACKAGE / "manual"
    return bundled if bundled.is_dir() else PACKAGE.parent.parent / "docs" / "manual"


def site_config() -> Path:
    bundled = PACKAGE / "manual" / "_site.toml"
    return bundled if bundled.is_file() else PACKAGE.parent.parent / "zensical.toml"


def _manual_nav() -> list[tuple[str, list[str]]]:
    """(section, [page names]) in the site's order."""
    nav = tomllib.loads(site_config().read_text())["project"]["nav"]
    manual = next(entry["User manual"] for entry in nav if "User manual" in entry)
    sections = []
    for entry in manual:
        if isinstance(entry, dict):
            for section, paths in entry.items():
                names = [p.removeprefix("manual/").removesuffix(".md") for p in paths]
                sections.append((section, names))
    return sections


def _link(page: str, target: str, fragment: str) -> str:
    """A page's relative .md link as the app serves it."""
    path = posixpath.normpath(posixpath.join(posixpath.dirname(page), target))
    if path.startswith("../"):  # outside the manual: the documentation site
        return f"{SITE}{posixpath.normpath(path[3:]).removesuffix('.md')}/{fragment}"
    return f"/manual/{path.removesuffix('.md')}/{fragment}"


def render(name: str, text: str) -> tuple[str, str]:
    """(title, HTML) of one Markdown page."""
    front = FRONT_MATTER.match(text)
    title = name
    if front:
        found = TITLE.search(front.group(1))
        title = found.group(1) if found else name
        text = text[front.end() :]
    html = markdown.markdown(text, extensions=EXTENSIONS, output_format="html")
    html = HREF.sub(lambda m: f'{m[1]}="{_link(name, m[2], m[3] or "")}"', html)
    return title, html


@lru_cache
def pages() -> dict[str, Page]:
    """Every manual page in the site's order, by name."""
    found = {}
    for section, names in _manual_nav():
        for name in names:
            title, html = render(name, (manual_dir() / f"{name}.md").read_text())
            found[name] = Page(name, title, section, html)
    return found


def sections() -> list[tuple[str, list[Page]]]:
    grouped: dict[str, list[Page]] = {}
    for page in pages().values():
        grouped.setdefault(page.section, []).append(page)
    return list(grouped.items())


@lru_cache
def manual_pdf(version: str) -> bytes:
    """The whole manual as one printable PDF, with the vendored fonts and nothing fetched."""
    from labra.printing.pdf import BASE_CSS, render_pdf
    from labra.web.templating import templates

    html = templates.get_template("help/manual_pdf.html").render(
        sections=sections(), version=version
    )
    rendered = render_pdf(html, stylesheets=[BASE_CSS, "labra-asset:pdf/manual.css"])
    if rendered.refused:
        raise RuntimeError(f"the manual named files it may not fetch: {rendered.refused}")
    return rendered.pdf
