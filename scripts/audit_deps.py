"""Check and refresh the dependency register, docs/DEPENDENCIES.md (standard library only).

    audit_deps.py --check     offline: exit 0 clean, 1 on any problem
    audit_deps.py --refresh   rewrite Pinned / Latest / Rel. 12m from uv.lock and PyPI;
                              exit 2 when PyPI can't be reached (unchecked, never a pass)

--check fails when:
- a Python package, image, Action or vendored file has no row, or a row has nothing behind it
- a row's Pinned version differs from uv.lock or the vendor manifest
- a licence is outside the allowlist, or a runtime package (direct or not) is copyleft
- a workflow `uses:` isn't pinned by a 40-character commit SHA
- an image in compose.yaml or the Dockerfile has no digest
- a vendored file doesn't match its SHA-256 in static/vendor/manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "docs" / "DEPENDENCIES.md"
VENDOR = ROOT / "src" / "labra" / "static" / "vendor"
WORKFLOWS = ROOT / ".github" / "workflows"
IMAGE_FILES = (ROOT / "compose.yaml", ROOT / "Dockerfile")

ALLOWED = {
    "MIT", "MIT-CMU", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "0BSD",
    "PostgreSQL", "PSF-2.0",
}  # fmt: skip
LGPL_EXCEPTION = {"psycopg", "psycopg-binary", "psycopg-c"}
NOT_SHIPPED = {"dev", "CLI"}
PYTHON_KINDS = {"runtime", "seed", "dev", "build"}
COPYLEFT = re.compile(r"\b(A?GPL|LGPL|SSPL|EUPL|General Public)", re.IGNORECASE)
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_RE = re.compile(r"^\s*(?:image:|FROM)\s+(?:--platform=\S+\s+)?([^\s#]+)", re.IGNORECASE)


@dataclass
class Row:
    name: str
    kind: str
    licence: str
    pinned: str
    line: int


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_register(text: str) -> list[Row]:
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^\|\s*`([^`]+)`\s*\|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(Row(m.group(1), cells[1], cells[3], cells[4], n))
    return rows


def licence_problem(row: Row) -> str | None:
    if row.licence in {"", "—"}:
        return None if row.kind == "service" else "no licence"
    if " OR " in row.licence:
        parts, need_all = row.licence.split(" OR "), False
    else:
        parts, need_all = row.licence.split(" AND "), True
    ok = [_allowed(p.strip(), row) for p in parts]
    if all(ok) if need_all else any(ok):
        return None
    return f"licence {row.licence} is outside the allowlist"


def _allowed(spdx: str, row: Row) -> bool:
    if spdx in ALLOWED:
        return True
    if spdx.startswith("LGPL-3.0") and norm(row.name) in LGPL_EXCEPTION:
        return True
    return spdx == "MPL-2.0" and row.kind in NOT_SHIPPED


# Python packages


def lock_packages() -> dict[str, dict]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {norm(p["name"]): p for p in lock["package"]}


def direct_python() -> dict[str, str]:
    """Direct dependencies, by normalised name → the kind their row should have."""
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    found: dict[str, str] = {}

    def add(specs: list[str], kind: str) -> None:
        for spec in specs:
            found.setdefault(norm(re.split(r"[\s\[<>=!~;]", spec, maxsplit=1)[0]), kind)

    add(py["project"].get("dependencies", []), "runtime")
    for specs in py["project"].get("optional-dependencies", {}).values():
        add(specs, "seed")
    for specs in py.get("dependency-groups", {}).values():
        add([s for s in specs if isinstance(s, str)], "dev")
    add(py.get("build-system", {}).get("requires", []), "build")
    return found


def runtime_closure(packages: dict[str, dict]) -> set[str]:
    root = next(p for p in packages.values() if p.get("source", {}).get("editable") == ".")
    todo = [norm(d["name"]) for d in root.get("dependencies", [])]
    seen: set[str] = set()
    while todo:
        name = todo.pop()
        if name in seen or name not in packages:
            continue
        seen.add(name)
        todo += [norm(d["name"]) for d in packages[name].get("dependencies", [])]
    return seen


def installed_licence(name: str) -> str | None:
    try:
        meta = importlib.metadata.metadata(name)
    except importlib.metadata.PackageNotFoundError:
        return None
    parts = [meta.get("License-Expression") or "", (meta.get("License") or "")[:200]]
    parts += [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    return " ".join(parts)


def check_python(rows: list[Row]) -> list[str]:
    packages = lock_packages()
    direct = direct_python()
    by_name = {norm(r.name): r for r in rows if r.kind in PYTHON_KINDS}
    problems = [
        f"{name}: {kind} dependency has no row in docs/DEPENDENCIES.md"
        for name, kind in sorted(direct.items())
        if name not in by_name
    ]
    for name, row in by_name.items():
        locked = packages.get(name)
        if row.kind == "build":
            if name not in direct:
                problems.append(f"DEPENDENCIES.md:{row.line}: {row.name} isn't a build dependency")
            continue
        if locked is None:
            problems.append(
                f"DEPENDENCIES.md:{row.line}: {row.name} isn't in uv.lock; drop the row"
            )
        elif locked["version"] != row.pinned:
            problems.append(
                f"DEPENDENCIES.md:{row.line}: {row.name} pinned {row.pinned}, uv.lock has "
                f"{locked['version']}; run scripts/audit_deps.py --refresh"
            )
    for name in sorted(runtime_closure(packages)):
        text = installed_licence(name)
        if text and COPYLEFT.search(text) and name not in LGPL_EXCEPTION:
            problems.append(f"{name}: runtime package with a copyleft licence ({text.strip()})")
    return problems


# Actions, images and vendored files


def check_actions(rows: list[Row]) -> list[str]:
    known = {r.name for r in rows if r.kind == "action"}
    used: set[str] = set()
    problems = []
    for wf in sorted(WORKFLOWS.glob("*.y*ml")):
        for n, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            m = USES_RE.match(line)
            if not m or m.group(1).startswith(("./", "docker://")):
                continue
            action, _, ref = m.group(1).partition("@")
            repo = "/".join(action.split("/")[:2])
            used.add(repo)
            where = f"{wf.relative_to(ROOT)}:{n}"
            if not SHA_RE.match(ref):
                problems.append(f"{where}: {m.group(1)} isn't pinned by a 40-character SHA")
            if repo not in known:
                problems.append(f"{where}: action {repo} has no row in docs/DEPENDENCIES.md")
    problems += [
        f"DEPENDENCIES.md:{r.line}: action {r.name} isn't used in any workflow; drop the row"
        for r in rows
        if r.kind == "action" and r.name not in used
    ]
    return problems


def image_name(ref: str) -> str:
    name = ref.split("@", 1)[0]
    last = name.rsplit("/", 1)[-1]
    if ":" in last:
        name = name[: len(name) - len(last)] + last.split(":", 1)[0]
    return name.removeprefix("docker.io/").removeprefix("library/")


def check_images(rows: list[Row]) -> list[str]:
    known = {r.name for r in rows if r.kind == "image"}
    used: set[str] = set()
    problems = []
    for path in IMAGE_FILES:
        if not path.is_file():
            continue
        stages: set[str] = set()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = IMAGE_RE.match(line)
            if not m or "${" in m.group(1):
                continue
            ref = m.group(1)
            alias = re.search(r"\s+AS\s+(\S+)", line, re.IGNORECASE)
            if alias:
                stages.add(alias.group(1).lower())
            if ref.lower() in stages:
                continue
            name = image_name(ref)
            used.add(name)
            where = f"{path.name}:{n}"
            if "@sha256:" not in ref:
                problems.append(f"{where}: image {ref} has no @sha256 digest")
            if name not in known:
                problems.append(f"{where}: image {name} has no row in docs/DEPENDENCIES.md")
    if any(p.is_file() for p in IMAGE_FILES):
        problems += [
            f"DEPENDENCIES.md:{r.line}: image {r.name} isn't used; drop the row"
            for r in rows
            if r.kind == "image" and r.name not in used
        ]
    return problems


def check_vendored(rows: list[Row]) -> list[str]:
    known = {r.name: r for r in rows if r.kind == "vendored"}
    manifest = json.loads((VENDOR / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    for filename, entry in sorted(manifest.items()):
        path = VENDOR / filename
        if not path.is_file():
            problems.append(f"vendor/{filename}: listed in manifest.json but missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            problems.append(f"vendor/{filename}: SHA-256 doesn't match manifest.json")
        row = known.get(entry["package"])
        if row is None:
            problems.append(f"vendor/{filename}: {entry['package']} has no register row")
        elif row.pinned != entry["version"]:
            problems.append(
                f"DEPENDENCIES.md:{row.line}: {row.name} pinned {row.pinned}, "
                f"manifest has {entry['version']}"
            )
    listed = {e["package"] for e in manifest.values()}
    problems += [
        f"DEPENDENCIES.md:{r.line}: {r.name} isn't in vendor/manifest.json; drop the row"
        for r in known.values()
        if r.name not in listed
    ]
    on_disk = {p.name for p in VENDOR.iterdir() if p.name != "manifest.json"}
    problems += [f"vendor/{f}: not in manifest.json" for f in sorted(on_disk - set(manifest))]
    return problems


def check(rows: list[Row]) -> list[str]:
    problems = []
    seen: set[str] = set()
    for r in rows:
        if r.name in seen:
            problems.append(f"DEPENDENCIES.md:{r.line}: duplicate row {r.name}")
        seen.add(r.name)
        lp = licence_problem(r)
        if lp:
            problems.append(f"DEPENDENCIES.md:{r.line}: {r.name}: {lp}")
    return (
        problems
        + check_python(rows)
        + check_actions(rows)
        + check_images(rows)
        + check_vendored(rows)
    )


# Refresh


def pypi(name: str) -> dict:
    url = f"https://pypi.org/pypi/{name}/json"
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def freshness(data: dict, now: datetime) -> tuple[str, str, int]:
    latest = data["info"]["version"]
    dates: dict[str, datetime] = {}
    for version, files in data["releases"].items():
        stamps = [f["upload_time_iso_8601"] for f in files if not f.get("yanked")]
        if stamps:
            dates[version] = datetime.fromisoformat(min(stamps).replace("Z", "+00:00"))
    when = dates.get(latest)
    recent = sum(1 for d in dates.values() if d > now - timedelta(days=365))
    return latest, when.date().isoformat() if when else "", recent


def suggested_status(when: str, now: datetime) -> str:
    if not when:
        return ""
    age = now - datetime.fromisoformat(when).replace(tzinfo=UTC)
    if age <= timedelta(days=183):
        return "Active"
    return "Stable or Watch" if age <= timedelta(days=730) else "Watch"


def refresh(text: str) -> tuple[str, list[str], bool]:
    """The register with Python rows refreshed, status notes, and whether PyPI answered."""
    packages = lock_packages()
    now = datetime.now(UTC)
    lines = text.splitlines()
    notes: list[str] = []
    reached = True
    for row in parse_register(text):
        if row.kind not in PYTHON_KINDS - {"build"}:
            continue
        cells = [c.strip() for c in lines[row.line - 1].strip().strip("|").split("|")]
        locked = packages.get(norm(row.name))
        if locked:
            cells[4] = locked["version"]
        try:
            latest, when, recent = freshness(pypi(row.name), now)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            reached = False
            continue
        cells[5] = f"{latest} · {when}" if when else latest
        cells[6] = str(recent)
        hint = suggested_status(when, now)
        if hint and cells[7] not in hint:
            notes.append(f"{row.name}: status {cells[7]}, rules suggest {hint} (latest {when})")
        lines[row.line - 1] = "| " + " | ".join(cells) + " |"
    return "\n".join(lines) + "\n", notes, reached


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or refresh docs/DEPENDENCIES.md.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    text = REGISTER.read_text(encoding="utf-8")
    if args.refresh:
        new, notes, reached = refresh(text)
        if new != text:
            REGISTER.write_text(new, encoding="utf-8")
            print("docs/DEPENDENCIES.md refreshed")
        for n in notes:
            print(n)
        if not reached:
            print("WARN: PyPI unreachable for some rows; they are unchecked")
            return 2
        return 0

    problems = check(parse_register(text))
    for p in problems:
        print(p)
    if not problems:
        print(f"dependency register: {len(parse_register(text))} rows, all consistent")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
