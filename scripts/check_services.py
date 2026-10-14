"""Check the service swap register, docs/dev/services.md (standard library only).

    check_services.py --check     exit 0 clean, 1 on any problem

--check fails when:
- a port in labra.core.ports.GROUPS, or an entry point under a `labra.*` group in
  pyproject.toml, isn't named in its port row
- a `LABRA_*` name under "Selected by" is neither a Settings field nor a Compose variable
- a Compose service, profile, override file or image, or a vendored asset, is named in no row
- a row's kind or status is unknown, or its proof is missing: a `swappable` row names a test
  (`file::name`) or script that doesn't exist, a `planned` row no open tracker ID, a `fixed`
  row no ADR
- Postgres-only code sits in src/labra outside core/dialect.py and migrations/
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = "docs/dev/services.md"
COLUMNS = ["Service", "Kind", "Default", "Alternatives", "Selected by", "Proof", "Status"]
KINDS = {"port", "setting", "endpoint", "compose", "script", "vendored", "library"}
STATUSES = {"swappable", "planned", "fixed"}
CLOSED = {"done", "dropped"}

CODE_RE = re.compile(r"`([^`]+)`")
TOKEN_SPLIT = re.compile(r"[\s,:]+")
LABRA_VAR_RE = re.compile(r"\bLABRA_[A-Z0-9_]*[A-Z0-9]\b")
COMPOSE_VAR_RE = re.compile(r"\$\{(LABRA_[A-Z0-9_]+)")
COMMENT_RE = re.compile(r"(?:^|\s+)#.*$")
FLOW_STYLE = "services must be written in block style, one key per line, for the gate to read"
DEFAULT_RE = re.compile(r"\$\{[A-Z0-9_]+:-([^}]+)\}")
TRACKER_ID_RE = re.compile(r"\b(?:W|M|X|LT)\d{2}(?:\.\d+)?\b")
ADR_LINK_RE = re.compile(r"\]\(([^)]*adr/\d{4}-[^)]+\.md)\)")

DIALECT_HOME = ("src/labra/core/dialect.py", "src/labra/migrations/")
POSTGRES_ONLY = [
    (re.compile(r"^\s*(?:from|import)\s+sqlalchemy\.dialects\b"), "a sqlalchemy.dialects import"),
    (re.compile(r"\bfunc\.(?:similarity|unnest|array_to_string)\b"), "a Postgres function"),
    (re.compile(r"pg_advisory|hashtextextended"), "a Postgres lock"),
    (re.compile(r"\bdistinct_on\b"), "DISTINCT ON"),
    (re.compile(r"\.op\(\s*[\"']%[\"']"), "the trigram % operator"),
]


@dataclass(frozen=True)
class Fact:
    """Something that needs a row, and where it was found."""

    name: str
    where: str


@dataclass
class Row:
    cells: dict[str, str]
    line: int
    spans: set[str] = field(default_factory=set)
    tokens: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.spans = {s.strip() for s in CODE_RE.findall(" ".join(self.cells.values()))}
        self.tokens = {t for s in self.spans for t in TOKEN_SPLIT.split(s) if t}


@dataclass
class Facts:
    groups: list[Fact] = field(default_factory=list)  # port entry-point groups
    entry_points: dict[str, list[Fact]] = field(default_factory=dict)  # group -> names
    settings: set[str] = field(default_factory=set)  # LABRA_* names of Settings fields
    compose_vars: set[str] = field(default_factory=set)
    services: list[Fact] = field(default_factory=list)
    profiles: list[Fact] = field(default_factory=list)
    overrides: list[Fact] = field(default_factory=list)
    images: list[Fact] = field(default_factory=list)
    vendored: list[Fact] = field(default_factory=list)
    tracker: dict[str, str] = field(default_factory=dict)  # ID -> status
    problems: list[str] = field(default_factory=list)  # files the gate can't read


# Reading the register


def parse_register(text: str) -> tuple[list[Row], list[str]]:
    """The rows of the table under "## Register", and problems with its shape."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## Register")
    except StopIteration:
        return [], [f"{REGISTER}: no '## Register' section"]
    rows: list[Row] = []
    header: list[str] | None = None
    for n, line in enumerate(lines[start + 1 :], start + 2):
        if line.startswith("## "):
            break
        if not line.startswith("|"):
            if header is not None and not line.strip():
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            if header != COLUMNS:
                return [], [f"{REGISTER}:{n}: columns must be {' | '.join(COLUMNS)}"]
        elif not set(line) <= set("|-: "):
            if len(cells) != len(COLUMNS):
                return rows, [f"{REGISTER}:{n}: expected {len(COLUMNS)} cells"]
            rows.append(Row(dict(zip(COLUMNS, cells, strict=True)), n))
    return rows, []


# Gathering the facts from the repository


def port_groups(source: str, path: str) -> list[Fact]:
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "GROUPS" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            return [
                Fact(v.value, f"{path}:{v.lineno}")
                for v in node.value.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            ]
    return []


def settings_names(source: str) -> set[str]:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            return {
                f"LABRA_{item.target.id.upper()}"
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    return set()


def entry_point_facts(pyproject: str) -> dict[str, list[Fact]]:
    groups = tomllib.loads(pyproject).get("project", {}).get("entry-points", {})
    lines = pyproject.splitlines()
    found: dict[str, list[Fact]] = {}
    for group, names in groups.items():
        if not group.startswith("labra."):
            continue
        header = f'[project.entry-points."{group}"]'
        line = next((n for n, text in enumerate(lines, 1) if text.strip() == header), 0)
        found[group] = [Fact(name, f"pyproject.toml:{line}") for name in names]
    return found


def image_name(ref: str) -> str:
    """`docker.io/library/postgres:18@sha256:…` -> `postgres`."""
    ref = DEFAULT_RE.sub(r"\1", ref).split("@")[0]
    last = ref.rsplit("/", 1)[-1]
    return last.split(":")[0]


def _scalar(value: str) -> str:
    return value.strip().strip("\"'")


def compose_facts(text: str, path: str, facts: Facts) -> None:
    """Services, profiles and images in a Compose file. The standard library has no YAML
    parser, so this reads block style line by line, at any indentation; a service written in
    flow style (`{…}`) would go unseen, so it is refused instead."""
    facts.compose_vars |= set(COMPOSE_VAR_RE.findall(text))
    section = ""
    service_indent: int | None = None
    profiles_indent: int | None = None
    for n, raw in enumerate(text.splitlines(), 1):
        where = f"{path}:{n}"
        line = COMMENT_RE.sub("", raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        item = line.strip()
        if profiles_indent is not None:
            if indent >= profiles_indent and item.startswith("- "):
                facts.profiles.append(Fact(_scalar(item[2:]), where))
                continue
            profiles_indent = None
        key, _, value = item.partition(":")
        key, value = _scalar(key), value.strip()
        if indent == 0:
            section, service_indent = key, None
            if section == "services" and value:
                facts.problems.append(f"{where}: {FLOW_STYLE}")
            continue
        if section == "services":
            service_indent = indent if service_indent is None else service_indent
            if indent == service_indent:
                facts.services.append(Fact(key, where))
                if value.startswith("{"):
                    facts.problems.append(f"{where}: {FLOW_STYLE}")
                continue
        if key == "image" and value:
            facts.images.append(Fact(image_name(_scalar(value)), where))
        elif key == "profiles":
            if value:
                inline = value.strip("[]").split(",")
                facts.profiles += [Fact(_scalar(p), where) for p in inline if _scalar(p)]
            else:
                profiles_indent = indent


def tracker_status(text: str) -> dict[str, str]:
    status: dict[str, str] = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) >= 4:
            ident = cells[0].strip("~")
            if TRACKER_ID_RE.fullmatch(ident):
                status[ident] = cells[3]
    return status


def gather(root: Path) -> Facts:
    def read(rel: str) -> str:
        return (root / rel).read_text(encoding="utf-8")

    facts = Facts(
        groups=port_groups(read("src/labra/core/ports.py"), "src/labra/core/ports.py"),
        entry_points=entry_point_facts(read("pyproject.toml")),
        settings=settings_names(read("src/labra/core/config.py")),
        tracker=tracker_status(read("docs/TRACKER.md")),
    )
    compose_facts(read("compose.yaml"), "compose.yaml", facts)
    for override in sorted(root.glob("deploy/*/compose.*.yaml")):
        rel = override.relative_to(root).as_posix()
        facts.overrides.append(Fact(rel, rel))
        compose_facts(override.read_text(encoding="utf-8"), rel, facts)
    manifest_path = "src/labra/static/vendor/manifest.json"
    manifest = json.loads(read(manifest_path))
    facts.vendored = [Fact(entry["package"], manifest_path) for entry in manifest.values()]
    return facts


# The checks


def _missing(facts: list[Fact], named: set[str], what: str) -> list[str]:
    seen: set[str] = set()
    problems = []
    for fact in facts:
        if fact.name not in named and fact.name not in seen:
            seen.add(fact.name)
            problems.append(f"{fact.where}: {what} '{fact.name}' has no row in {REGISTER}")
    return problems


def check_ports(rows: list[Row], facts: Facts) -> list[str]:
    problems = []
    groups = list(facts.groups)
    known = {g.name for g in groups}
    groups += [Fact(g, eps[0].where) for g, eps in facts.entry_points.items() if g not in known]
    for group in groups:
        row = next((r for r in rows if r.cells["Kind"] == "port" and group.name in r.tokens), None)
        if row is None:
            problems.append(f"{group.where}: port group '{group.name}' has no row in {REGISTER}")
            continue
        problems += [
            f"{ep.where}: entry point '{group.name}:{ep.name}' isn't named in its row "
            f"({REGISTER}:{row.line})"
            for ep in facts.entry_points.get(group.name, [])
            if ep.name not in row.tokens
        ]
    return problems


def check_settings(rows: list[Row], facts: Facts) -> list[str]:
    def known(name: str) -> bool:
        base = name.removesuffix("_FILE")
        return name in facts.settings or name in facts.compose_vars or base in facts.settings

    return [
        f"{REGISTER}:{row.line}: {name} is neither a setting in labra.core.config nor a "
        "Compose variable"
        for row in rows
        for name in LABRA_VAR_RE.findall(row.cells["Selected by"])
        if not known(name)
    ]


def check_compose(rows: list[Row], facts: Facts) -> list[str]:
    tokens = set().union(*(r.tokens for r in rows))
    spans = set().union(*(r.spans for r in rows))
    profiles = {p.name for p in facts.profiles if f"--profile {p.name}" in spans}
    return [
        *_missing(facts.services, tokens, "Compose service"),
        *_missing(facts.profiles, profiles, "Compose profile"),
        *_missing(facts.overrides, spans, "Compose override"),
        *_missing(facts.images, tokens, "image"),
        *_missing(facts.vendored, tokens, "vendored asset"),
    ]


def _proof_problem(span: str, root: Path) -> str | None:
    path, _, test = span.partition("::")
    if "/" not in path:
        return f"`{span}` is neither a test (file::name) nor a script"
    if not (root / path).is_file():
        return f"`{path}` doesn't exist"
    if test:
        source = (root / path).read_text(encoding="utf-8")
        if not re.search(rf"^\s*(?:async\s+)?def {re.escape(test)}\(", source, re.MULTILINE):
            return f"`{path}` has no test {test}"
    return None


def check_row(row: Row, facts: Facts, root: Path) -> list[str]:
    at = f"{REGISTER}:{row.line}"
    kind, status, proof = row.cells["Kind"], row.cells["Status"], row.cells["Proof"]
    problems = []
    if kind not in KINDS:
        problems.append(f"{at}: unknown kind '{kind}' (use {', '.join(sorted(KINDS))})")
    if status == "swappable":
        spans = CODE_RE.findall(proof)
        if not spans:
            problems.append(f"{at}: a swappable row names the test or script that proves it")
        problems += [f"{at}: {p}" for s in spans if (p := _proof_problem(s, root))]
    elif status == "planned":
        ids = TRACKER_ID_RE.findall(proof)
        if not ids:
            problems.append(f"{at}: a planned row names its tracker ID")
        for ident in ids:
            if ident not in facts.tracker:
                problems.append(f"{at}: {ident} isn't in docs/TRACKER.md")
            elif facts.tracker[ident] in CLOSED:
                problems.append(f"{at}: {ident} is {facts.tracker[ident]}; update the row")
    elif status == "fixed":
        links = ADR_LINK_RE.findall(proof)
        if not links:
            problems.append(f"{at}: a fixed row links the ADR that decided it")
        base = (root / REGISTER).parent
        problems += [f"{at}: {link} doesn't exist" for link in links if not (base / link).is_file()]
    else:
        problems.append(f"{at}: unknown status '{status}' (use {', '.join(sorted(STATUSES))})")
    return problems


def postgres_leaks(files: dict[str, str]) -> list[str]:
    """Postgres-only code outside the dialect seam and the migrations."""
    problems = []
    for path, text in sorted(files.items()):
        if path.startswith(DIALECT_HOME):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            problems += [
                f"{path}:{n}: {what}; use labra.core.dialect instead"
                for pattern, what in POSTGRES_ONLY
                if pattern.search(line)
            ]
    return problems


def check(register: str, facts: Facts, sources: dict[str, str], root: Path) -> list[str]:
    rows, problems = parse_register(register)
    if not rows:
        return problems or [f"{REGISTER}: the register has no rows"]
    problems += facts.problems
    problems += check_ports(rows, facts)
    problems += check_settings(rows, facts)
    problems += check_compose(rows, facts)
    for row in rows:
        problems += check_row(row, facts, root)
    problems += postgres_leaks(sources)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the service swap register.")
    parser.add_argument("--check", action="store_true", required=True, help="check, offline")
    parser.parse_args(argv)
    sources = {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted((ROOT / "src" / "labra").rglob("*.py"))
    }
    register = (ROOT / REGISTER).read_text(encoding="utf-8")
    problems = check(register, gather(ROOT), sources, ROOT)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
