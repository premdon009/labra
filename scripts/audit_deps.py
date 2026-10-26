"""Check and refresh the dependency register, docs/DEPENDENCIES.md (standard library only).

    audit_deps.py --check     offline: exit 0 clean, 1 on any problem
    audit_deps.py --refresh   rewrite Pinned / Latest / Rel. 12m from uv.lock and PyPI;
                              exit 2 when PyPI can't be reached (unchecked, never a pass)

--check fails when:
- a Python package, image, Action or vendored file has no row, or a row has nothing behind it
- a row's Pinned version differs from uv.lock or the vendor manifest
- a licence is outside the allowlist, or a runtime package (direct or not) is copyleft
- a font row (OFL-1.1) vendors anything but font files and their licence text
- a workflow `uses:` isn't pinned by a 40-character commit SHA
- an image in compose.yaml, a Dockerfile (its `# syntax=` frontend too), the CI lab's
  Containerfile or a script's `<NAME>_IMAGE=` has no digest, or a `dev-image` row names an
  image that is shipped
- a release binary a Dockerfile or script downloads (`<NAME>_VERSION`) has no `binary` row with
  that version, or lacks a SHA-256 for each arch it fetches
- a vendored file doesn't match its SHA-256 in static/vendor/manifest.json
- a pinned version is younger than MIN_AGE (uv.lock upload time, or the date in the Pinned
  cell of an Action, image or vendored row) and no Age exceptions row names its advisory
- an Age exceptions row has no GHSA, CVE or PYSEC ID, or names a version no longer pinned, or
  the Python exceptions and pyproject's exclude-newer-package entries don't match
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
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "docs" / "DEPENDENCIES.md"
VENDOR = ROOT / "src" / "labra" / "static" / "vendor"
WORKFLOWS = ROOT / ".github" / "workflows"
IMAGE_FILES = (
    ROOT / "compose.yaml",
    ROOT / "Dockerfile",
    ROOT / "deploy/nginx/compose.nginx.yaml",
    ROOT / "deploy/backup/Dockerfile",
)
# Images that build or test Labra, never shipped: kind `dev-image`, or `image` if also shipped.
DEV_IMAGE_FILES = (ROOT / "deploy/ci-lab/Containerfile", ROOT / "scripts/build_image.sh")
# Files that download release binaries, each pinned by version and a SHA-256 per arch fetched.
BINARY_FILES = {
    ROOT / "deploy/backup/Dockerfile": ("AMD64", "ARM64"),
    ROOT / "scripts/portability_job.sh": ("AMD64",),  # GitHub's runners and the CI lab
}

ALLOWED = {
    "MIT", "MIT-CMU", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "0BSD",
    "PostgreSQL", "PSF-2.0",
}  # fmt: skip
LGPL_EXCEPTION = {"psycopg", "psycopg-binary", "psycopg-c"}
# Tri-licensed (GPL-2.0+ OR LGPL-2.1+ OR MPL-1.1); used under MPL-1.1, unmodified, by WeasyPrint.
MPL11_EXCEPTION = {"pyphen"}
FONT_FILES = (".ttf", ".otf", ".woff2")
NOT_SHIPPED = {"dev", "CLI", "dev-image"}
PYTHON_KINDS = {"runtime", "seed", "dev", "build"}
COPYLEFT = re.compile(r"\b(A?GPL|LGPL|SSPL|EUPL|General Public)", re.IGNORECASE)
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_RE = re.compile(
    r"^\s*(?:(?:image:|FROM)\s+(?:--platform=\S+\s+)?|[A-Z_]+_IMAGE=)([^\s#]+)", re.IGNORECASE
)
# A Dockerfile's frontend runs in the build only, so it is never shipped.
SYNTAX_RE = re.compile(r"^#\s*syntax=([^\s#]+)", re.IGNORECASE)
NAME_CELL_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")

# Minimum release age: no pinned version younger than this, unless it fixes a published advisory.
MIN_AGE = timedelta(days=7)
DATED_KINDS = {"action", "image", "dev-image", "vendored", "font", "binary"}
ADVISORY_RE = re.compile(r"^(GHSA(-[0-9a-z]{4}){3}|CVE-\d{4}-\d{4,}|PYSEC-\d{4}-\d+)$")
EXCEPTIONS_HEADING = "## Age exceptions"


@dataclass
class Row:
    name: str
    kind: str
    licence: str
    pinned: str
    line: int

    @property
    def version(self) -> str:
        return self.pinned.partition(" · ")[0]

    @property
    def released(self) -> str:
        """The pinned release's date, from a Pinned cell written `<version> · <YYYY-MM-DD>`."""
        return self.pinned.partition(" · ")[2]


@dataclass
class AgeException:
    name: str
    version: str
    advisory: str
    line: int


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_register(text: str) -> list[Row]:
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip() == EXCEPTIONS_HEADING:
            break
        m = NAME_CELL_RE.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(Row(m.group(1), cells[1], cells[3], cells[4], n))
    return rows


def parse_exceptions(text: str) -> list[AgeException]:
    """The rows of the Age exceptions table, below the register."""
    found = []
    below = False
    for n, line in enumerate(text.splitlines(), 1):
        below = below or line.strip() == EXCEPTIONS_HEADING
        m = NAME_CELL_RE.match(line)
        if below and m:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            found.append(AgeException(m.group(1), cells[1], cells[2], n))
    return found


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
    if spdx.startswith("GPL-") and row.kind in {"CLI", "dev-image"}:
        return True  # run as a separate command or a developer's lab, never imported or shipped
    if spdx == "OFL-1.1":
        return row.kind == "font"  # font files only, checked against the manifest
    if spdx == "MPL-1.1":
        return norm(row.name) in MPL11_EXCEPTION
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
        elif locked["version"] != row.version:
            problems.append(
                f"DEPENDENCIES.md:{row.line}: {row.name} pinned {row.version}, uv.lock has "
                f"{locked['version']}; run scripts/audit_deps.py --refresh"
            )
    for name in sorted(runtime_closure(packages)):
        text = installed_licence(name)
        if text and COPYLEFT.search(text) and name not in LGPL_EXCEPTION | MPL11_EXCEPTION:
            problems.append(f"{name}: runtime package with a copyleft licence ({text.strip()})")
    return problems


# Actions, images and vendored files


def check_actions(rows: list[Row]) -> list[str]:
    known = {r.name: r for r in rows if r.kind == "action"}
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
            row = known.get(repo)
            if row is None:
                problems.append(f"{where}: action {repo} has no row in docs/DEPENDENCIES.md")
                continue
            # The comment names the SHA's release, so a new SHA can't keep the row's old date.
            comment = re.match(r"\s*#\s*(\S+)", line[m.end() :])
            if not comment or comment.group(1) != row.version:
                problems.append(
                    f"{where}: {repo} needs the comment `# {row.version}`, the version its row "
                    f"pins; update the row's version and date when the SHA changes"
                )
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


def fully_qualified(ref: str) -> bool:
    """Podman and Buildah refuse short names like `postgres:18` without a registry search
    list, so every reference starts with its registry host."""
    first, sep, _ = ref.partition("/")
    return bool(sep) and ("." in first or ":" in first or first == "localhost")


def check_images(rows: list[Row]) -> list[str]:
    kinds = {r.name: r.kind for r in rows if r.kind in {"image", "dev-image"}}
    used: set[str] = set()
    problems = []
    for path in (*IMAGE_FILES, *DEV_IMAGE_FILES):
        shipped = path in IMAGE_FILES
        if not path.is_file():
            continue
        stages: set[str] = set()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            frontend = SYNTAX_RE.match(line)
            m = frontend or IMAGE_RE.match(line)
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
            if not fully_qualified(ref):
                problems.append(
                    f"{where}: image {ref} needs its registry, e.g. docker.io/library/…"
                )
            if name not in kinds:
                problems.append(f"{where}: image {name} has no row in docs/DEPENDENCIES.md")
            elif shipped and not frontend and kinds[name] == "dev-image":
                problems.append(f"{where}: image {name} is shipped; its row's kind is image")
    if any(p.is_file() for p in (*IMAGE_FILES, *DEV_IMAGE_FILES)):
        problems += [
            f"DEPENDENCIES.md:{r.line}: image {r.name} isn't used; drop the row"
            for r in rows
            if r.kind in {"image", "dev-image"} and r.name not in used
        ]
    return problems


def check_binaries(rows: list[Row]) -> list[str]:
    known = {r.name: r for r in rows if r.kind == "binary"}
    used: set[str] = set()
    problems = []
    for path, arches in BINARY_FILES.items():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        # A Dockerfile's `ARG NAME=value`, or a script's `NAME=value`.
        args = dict(re.findall(r"^(?:ARG\s+)?(\w+)=(\S*)", text, re.M))
        for n, line in enumerate(text.splitlines(), 1):
            m = re.match(r"(ARG\s+)?(\w+)_VERSION=(\S*)", line)
            if not m:
                continue
            arg, key, version = m.groups()
            name = key.lower()
            used.add(name)
            where = f"{path.relative_to(ROOT)}:{n}"
            for arch in arches:
                if not re.fullmatch(r"[0-9a-f]{64}", args.get(f"{key}_SHA256_{arch}", "")):
                    problems.append(
                        f"{where}: {name} needs {arg or ''}{key}_SHA256_{arch}=<sha256>"
                    )
            row = known.get(name)
            if row is None:
                problems.append(f"{where}: binary {name} has no row in docs/DEPENDENCIES.md")
            elif row.version != version:
                problems.append(
                    f"DEPENDENCIES.md:{row.line}: {name} pinned {row.version}, "
                    f"{path.relative_to(ROOT)} downloads {version}"
                )
    problems += [
        f"DEPENDENCIES.md:{r.line}: binary {r.name} isn't downloaded anywhere; drop the row"
        for r in known.values()
        if r.name not in used
    ]
    return problems


def check_vendored(rows: list[Row]) -> list[str]:
    known = {r.name: r for r in rows if r.kind in {"vendored", "font"}}
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
        elif row.kind == "font" and not filename.endswith((*FONT_FILES, "-OFL.txt")):
            problems.append(f"vendor/{filename}: a font row vendors font files only")
        elif row.version != entry["version"]:
            problems.append(
                f"DEPENDENCIES.md:{row.line}: {row.name} pinned {row.version}, "
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


# Minimum release age


def exempt_packages() -> set[str]:
    """Packages that pyproject's [tool.uv] exclude-newer-package lets past the age limit."""
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {norm(n) for n in py.get("tool", {}).get("uv", {}).get("exclude-newer-package", {})}


def uploaded(package: dict) -> datetime | None:
    """When a locked version was published: the earliest upload of its files."""
    files = [package.get("sdist", {}), *package.get("wheels", [])]
    stamps = [datetime.fromisoformat(f["upload-time"]) for f in files if "upload-time" in f]
    return min(stamps) if stamps else None


def day_end(day: str) -> datetime | None:
    """A Pinned date counts from the end of its day, since the release could be any time in it."""
    try:
        return datetime.combine(date.fromisoformat(day) + timedelta(days=1), time(), UTC)
    except ValueError:
        return None


def too_young(where: str, what: str, released: str, since: datetime, now: datetime) -> str | None:
    if now - since >= MIN_AGE:
        return None
    return (
        f"{where}{what} was released {released}, under {MIN_AGE.days} days ago; allowed from "
        f"{since + MIN_AGE:%Y-%m-%d %H:%M} UTC, or sooner only with an Age exceptions row "
        f"naming its advisory"
    )


def check_age(
    rows: list[Row],
    exceptions: list[AgeException],
    packages: dict[str, dict],
    exempt: set[str],
    now: datetime,
) -> list[str]:
    allowed = {(norm(e.name), e.version) for e in exceptions}
    other = {norm(r.name): r for r in rows if r.kind not in PYTHON_KINDS}
    problems = []
    for e in exceptions:
        where = f"DEPENDENCIES.md:{e.line}: age exception {e.name} {e.version}"
        if not ADVISORY_RE.match(e.advisory):
            problems.append(f"{where}: advisory {e.advisory!r} isn't a GHSA, CVE or PYSEC ID")
        name = norm(e.name)
        pinned = packages[name]["version"] if name in packages else None
        if pinned is None and name in other:
            pinned = other[name].version
        if pinned != e.version:
            problems.append(f"{where}: the pinned version is {pinned or 'none'}; drop the row")
    python = {norm(e.name) for e in exceptions if norm(e.name) in packages}
    problems += [
        f"pyproject.toml: exclude-newer-package {name} has no Age exceptions row"
        for name in sorted(exempt - python)
    ]
    problems += [
        f"pyproject.toml: age exception {name} needs an exclude-newer-package entry"
        for name in sorted(python - exempt)
    ]
    for name, package in sorted(packages.items()):
        if "registry" not in package.get("source", {}):
            continue
        version = package["version"]
        since = uploaded(package)
        if since is None:
            problems.append(f"uv.lock: {name} {version} has no upload-time; re-lock with uv")
        elif (name, version) not in allowed:
            released = f"{since:%Y-%m-%d %H:%M} UTC"
            problems.append(too_young("uv.lock: ", f"{name} {version}", released, since, now))
    for r in rows:
        if not r.released:
            if r.kind in DATED_KINDS:
                problems.append(
                    f"DEPENDENCIES.md:{r.line}: {r.name}: Pinned needs the release date, "
                    f"as `{r.version} · YYYY-MM-DD`"
                )
            continue
        since = day_end(r.released)
        if since is None:
            problems.append(f"DEPENDENCIES.md:{r.line}: {r.name}: {r.released} isn't YYYY-MM-DD")
        elif (norm(r.name), r.version) not in allowed:
            where = f"DEPENDENCIES.md:{r.line}: "
            problems.append(too_young(where, f"{r.name} {r.version}", r.released, since, now))
    return [p for p in problems if p]


def unneeded_exceptions(
    rows: list[Row], exceptions: list[AgeException], packages: dict[str, dict], now: datetime
) -> list[str]:
    """Age exceptions whose version has since reached the minimum age."""
    dated = {norm(r.name): r for r in rows if r.released}
    notes = []
    for e in exceptions:
        name = norm(e.name)
        if name in packages:
            since = uploaded(packages[name])
        else:
            since = day_end(dated[name].released) if name in dated else None
        if since and now - since >= MIN_AGE:
            notes.append(
                f"age exception for {e.name} {e.version} is no longer needed; drop its row "
                f"and any exclude-newer-package entry"
            )
    return notes


def check(rows: list[Row], exceptions: list[AgeException] | None = None) -> list[str]:
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
        + check_binaries(rows)
        + check_vendored(rows)
        + check_age(rows, exceptions or [], lock_packages(), exempt_packages(), datetime.now(UTC))
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


def suggested_status(when: str, now: datetime, latest: str = "") -> str:
    if not when:
        return ""
    if latest.startswith("0."):
        return "Watch"  # a pre-1.0 API is a risk to its future, however often it releases
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
        hint = suggested_status(when, now, latest)
        if hint and cells[7] not in hint:
            notes.append(f"{row.name}: status {cells[7]}, rules suggest {hint} (latest {when})")
        lines[row.line - 1] = "| " + " | ".join(cells) + " |"
    notes += unneeded_exceptions(parse_register(text), parse_exceptions(text), packages, now)
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

    problems = check(parse_register(text), parse_exceptions(text))
    for p in problems:
        print(p)
    if not problems:
        print(f"dependency register: {len(parse_register(text))} rows, all consistent")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
