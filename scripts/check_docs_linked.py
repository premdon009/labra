"""Every docs page is reachable, and the site navigation points only at real pages.

- Every `docs/**/*.md` page is in the `nav` of zensical.toml (files starting with `_`
  are templates and are skipped).
- Every nav entry exists.
- Every ADR is linked from docs/adr/index.md.
- Relative links between Markdown files resolve.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
LINK_RE = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
CODE_SPAN_RE = re.compile(r"`[^`]*`")


def nav_pages(nav: list) -> set[str]:
    pages: set[str] = set()
    for entry in nav:
        values = entry.values() if isinstance(entry, dict) else [entry]
        for v in values:
            if isinstance(v, str):
                pages.add(v)
            elif isinstance(v, list):
                pages |= nav_pages(v)
    return pages


def relative_links(text: str) -> list[tuple[int, str]]:
    """(line number, target) of every relative Markdown link. Links shown as code are
    examples, not links."""
    found = []
    in_fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        for target in LINK_RE.findall(CODE_SPAN_RE.sub("", line)):
            if not target.startswith(("http://", "https://")):
                found.append((n, target))
    return found


def main() -> int:
    config = tomllib.loads((ROOT / "zensical.toml").read_text(encoding="utf-8"))
    in_nav = nav_pages(config["project"]["nav"])
    problems = []

    pages = {
        p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md") if not p.name.startswith("_")
    }
    problems += [f"docs/{p}: not in zensical.toml nav" for p in sorted(pages - in_nav)]
    problems += [f"zensical.toml nav: {p} doesn't exist" for p in sorted(in_nav - pages)]

    index = (DOCS / "adr" / "index.md").read_text(encoding="utf-8")
    for adr in sorted((DOCS / "adr").glob("[0-9][0-9][0-9][0-9]-*.md")):
        if f"({adr.name})" not in index:
            problems.append(f"docs/adr/{adr.name}: not linked from docs/adr/index.md")

    for md in sorted([*ROOT.glob("*.md"), *DOCS.rglob("*.md")]):
        problems += [
            f"{md.relative_to(ROOT)}:{n}: broken link {target}"
            for n, target in relative_links(md.read_text(encoding="utf-8"))
            if not (md.parent / target).resolve().is_file()
        ]

    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
