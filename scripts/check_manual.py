"""Keep the user manual in step with the screens.

    check_manual.py           exit 1 on any problem
    check_manual.py --write   also regenerate the features overview (docs/manual/index.md)

Rules:
- Every page route names its manual page (`@page("area/screen", ...)`), and that page exists.
- Every manual page has `features: [IDs]` front matter, and every ID is in the tracker.
- On a branch, a changed screen template needs its manual page changed too, unless a commit
  on the branch says `Manual: no change — <reason>`.
- docs/manual/index.md is the overview generated from the front matter, and is current.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "docs" / "manual"
INDEX = MANUAL / "index.md"
TEMPLATES = "src/labra/templates/"
MACHINE_PATHS = {"/healthz", "/readyz", "/metrics"}
FEATURES_RE = re.compile(r"^features:\s*\[([^\]]*)\]\s*$", re.MULTILINE)
TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)
NO_CHANGE_RE = re.compile(r"^Manual: no change\b", re.MULTILINE)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_tracker import CHECK_RE, CHECKLIST, TRACKER, parse_tracker  # noqa: E402


def front_matter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    return text[4:end] if end != -1 else ""


def features(path: Path) -> list[str]:
    m = FEATURES_RE.search(front_matter(path))
    return [f.strip() for f in m.group(1).split(",") if f.strip()] if m else []


def title(path: Path) -> str:
    m = TITLE_RE.search(front_matter(path))
    return m.group(1) if m else path.stem


def manual_pages() -> list[Path]:
    return sorted(p for p in MANUAL.rglob("*.md") if not p.name.startswith("_") and p != INDEX)


def screens() -> dict[str, tuple[str | None, str | None]]:
    """Route path → (manual page, template) for every GET route a person looks at."""
    from fastapi.routing import APIRoute, iter_route_contexts

    from labra.app import create_app

    found = {}
    for route in iter_route_contexts(create_app().routes):
        if not isinstance(route.original_route, APIRoute):
            continue
        if route.path is None or "GET" not in (route.methods or set()):
            continue
        if route.path in MACHINE_PATHS:
            continue
        endpoint = route.endpoint
        found[route.path] = (
            getattr(endpoint, "__manual_page__", None),
            getattr(endpoint, "__template__", None),
        )
    return found


def check_registry(registry: dict[str, tuple[str | None, str | None]]) -> list[str]:
    problems = []
    for path, (page, _) in sorted(registry.items()):
        if page is None:
            problems.append(f"route {path}: no manual page; decorate it with @page(...)")
        elif not (MANUAL / f"{page}.md").is_file():
            problems.append(f"route {path}: manual page docs/manual/{page}.md doesn't exist")
    return problems


def check_front_matter(known_ids: set[str]) -> list[str]:
    problems = []
    for p in manual_pages():
        rel = p.relative_to(ROOT).as_posix()
        ids = features(p)
        if not ids:
            problems.append(f"{rel}: front matter needs `features: [IDs]`")
        problems += [f"{rel}: unknown tracker ID {i}" for i in ids if i not in known_ids]
    return problems


def git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout


def changed_on_branch() -> tuple[set[str], str] | None:
    """Files changed since this branch left master (committed or not), and the branch's
    commit messages. None when there is no master to compare with."""
    base = next(
        (b.strip() for ref in ("origin/master", "master") if (b := git("merge-base", "HEAD", ref))),
        None,
    )
    if base is None:
        return None
    files = set((git("diff", "--name-only", base) or "").split())
    files |= set((git("ls-files", "--others", "--exclude-standard") or "").split())
    messages = git("log", "--format=%B", f"{base}..HEAD") or ""
    return files, messages


def check_staleness(registry: dict[str, tuple[str | None, str | None]]) -> list[str]:
    branch = changed_on_branch()
    if branch is None:
        print("staleness: no master branch to compare with; not checked")
        return []
    files, messages = branch
    if NO_CHANGE_RE.search(messages):
        return []
    problems = []
    for path, (page, template) in sorted(registry.items()):
        if page is None or template is None:
            continue
        page_file = f"docs/manual/{page}.md"
        if TEMPLATES + template in files and page_file not in files:
            problems.append(
                f"{TEMPLATES}{template} changed but {page_file} didn't (route {path}); update "
                "the page, or add 'Manual: no change — <reason>' to a commit message"
            )
    return problems


def overview(titles: dict[str, str]) -> str:
    rows = []
    for p in manual_pages():
        rel = p.relative_to(MANUAL).as_posix()
        for fid in features(p):
            rows.append((fid, titles.get(fid, ""), title(p), rel))
    rows.sort(key=lambda r: (_id_key(r[0]), r[3]))
    lines = [
        "# Features",
        "",
        "<!-- Generated by scripts/check_manual.py --write from the pages' front matter. -->",
        "",
        "Every feature Labra has, and the manual page that explains it.",
        "",
        "| ID | Feature | Page |",
        "|---|---|---|",
    ]
    lines += [f"| {i} | {t} | [{pt}]({rel}) |" for i, t, pt, rel in rows]
    return "\n".join(lines) + "\n"


def _id_key(fid: str) -> tuple[str, list[int]]:
    m = re.match(r"([A-Z-]+[A-O]?)(\d+(?:\.\d+)?)", fid)
    if not m:
        return fid, []
    return m.group(1), [int(n) for n in m.group(2).split(".")]


def _plain(title: str) -> str:
    return re.sub(r"\*\*|~~", "", title).strip()


def checklist_titles() -> dict[str, str]:
    """Enterprise checklist IDs, titled with their text up to the first `;` or `(`."""
    titles = {}
    for line in CHECKLIST.read_text(encoding="utf-8").splitlines():
        m = CHECK_RE.match(line)
        if m:
            text = line[m.end() :].strip()
            titles[m.group(3)] = _plain(re.split(r"[;(]", text, maxsplit=1)[0])
    return titles


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep the user manual in step with the screens.")
    parser.add_argument("--write", action="store_true", help="regenerate the overview")
    args = parser.parse_args()

    rows = parse_tracker(TRACKER.read_text(encoding="utf-8"))
    titles = {r.id: _plain(r.title) for r in rows} | checklist_titles()
    registry = screens()
    problems = check_registry(registry)
    problems += check_front_matter(set(titles))
    problems += check_staleness(registry)

    wanted = overview(titles)
    current = INDEX.read_text(encoding="utf-8") if INDEX.is_file() else ""
    if wanted != current:
        if args.write:
            INDEX.write_text(wanted, encoding="utf-8")
            print(f"wrote {INDEX.relative_to(ROOT)}")
        else:
            problems.append("docs/manual/index.md is stale; run scripts/check_manual.py --write")

    for p in problems:
        print(p)
    if not problems:
        print(f"manual: {len(registry)} screens, {len(manual_pages())} pages, all current")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
