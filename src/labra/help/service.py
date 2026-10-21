"""The user manual and the runbooks, read from their Markdown pages and shown inside the app.

The pages are the ones the documentation site is built from (docs/manual and docs/runbooks),
with the same order (the site's nav in zensical.toml). The image carries them inside the
package; a checkout reads them from the repository. Nothing is fetched from the internet, so
help works in a lab whose line is down.
"""

import posixpath
import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import markdown

PACKAGE = Path(__file__).resolve().parent.parent
# Pages the app doesn't carry (install guide, developer notes, the plan) link to the site.
SITE = "https://premdon009.github.io/labra/"
EXTENSIONS = ["admonition", "attr_list", "def_list", "footnotes", "md_in_html", "tables", "toc"]
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)
HEADING = re.compile(r"^# (.+?)\s*$", re.MULTILINE)
HREF = re.compile(r'(href|src)="([^"#:]*\.md)(#[^"]*)?"')
# Folders under docs/ that the app serves, and where: the manual's pages at /manual/<page>/,
# the runbooks at /manual/runbooks/<page>/.
SERVED = {"manual/": "", "runbooks/": "runbooks/"}


@dataclass(frozen=True)
class Page:
    name: str  # "admin/system", "runbooks/disk-full"
    title: str
    section: str
    html: str


def manual_dir() -> Path:
    bundled = PACKAGE / "manual"
    return bundled if bundled.is_dir() else PACKAGE.parent.parent / "docs" / "manual"


def runbooks_dir() -> Path:
    bundled = PACKAGE / "runbooks"
    return bundled if bundled.is_dir() else PACKAGE.parent.parent / "docs" / "runbooks"


def site_config() -> Path:
    bundled = PACKAGE / "manual" / "_site.toml"
    return bundled if bundled.is_file() else PACKAGE.parent.parent / "zensical.toml"


def _nav() -> list[tuple[str, list[str]]]:
    """(section, [paths under docs/]) for the manual's sections and the runbooks, in the
    site's order."""
    sections = []
    for entry in tomllib.loads(site_config().read_text())["project"]["nav"]:
        for section, paths in entry.items():
            if section == "User manual":
                sections += [item for s in paths if isinstance(s, dict) for item in s.items()]
            elif section == "Runbooks":
                sections.append((section, paths))
    return sections


def _served(path: str) -> str | None:
    """The app's name for a page under docs/, or None when the app doesn't carry it."""
    for folder, prefix in SERVED.items():
        if path.startswith(folder):
            return prefix + path.removeprefix(folder).removesuffix(".md")
    return None


def _link(source: str, target: str, fragment: str) -> str:
    """A relative .md link in `source` (a path under docs/) as the app serves it."""
    path = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
    name = _served(path)
    if name is None:  # not carried by the app: the documentation site
        return f"{SITE}{path.removesuffix('.md')}/{fragment}"
    return f"/manual/{name}/{fragment}"


def render(source: str, text: str) -> tuple[str, str]:
    """(title, HTML) of one Markdown page; `source` is its path under docs/."""
    front = FRONT_MATTER.match(text)
    found = TITLE.search(front.group(1)) if front else None
    if front:
        text = text[front.end() :]
    found = found or HEADING.search(text)
    title = found.group(1) if found else source
    html = markdown.markdown(text, extensions=EXTENSIONS, output_format="html")
    html = HREF.sub(lambda m: f'{m[1]}="{_link(source, m[2], m[3] or "")}"', html)
    return title, html


def _read(path: str) -> str:
    folder, rest = path.split("/", 1)
    return ((manual_dir() if folder == "manual" else runbooks_dir()) / rest).read_text()


@lru_cache
def pages() -> dict[str, Page]:
    """Every page in the site's order, by name."""
    found = {}
    for section, paths in _nav():
        for path in paths:
            name = _served(path)
            if name is None:
                continue
            title, html = render(path, _read(path))
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
