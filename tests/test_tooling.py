"""The command line and the repository gate scripts."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from labra.cli import build_parser, main

ROOT = Path(__file__).resolve().parent.parent


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.item("W04")
@pytest.mark.parametrize(
    "argv",
    [
        ["serve", "--workers", "2"],
        ["migrate"],
        ["check-config"],
        ["audit", "verify"],
        ["add-branch", "--code", "B2", "--name", "Branch 2", "--kind", "collection_centre"],
        ["create-admin", "--username", "admin", "--full-name", "Admin User"],
        ["seed"],
    ],
)
def test_cli_commands_parse(argv: list[str]) -> None:
    assert callable(build_parser().parse_args(argv).func)


@pytest.mark.item("W04")
def test_cli_rejects_unknown_kind() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["add-branch", "--code", "B2", "--name", "x", "--kind", "shop"])


@pytest.mark.item("W15")
def test_check_config_exit_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LABRA_FILES_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as ok:
        main(["check-config"])
    assert ok.value.code == 0

    from labra.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("LABRA_MAILER", "carrier-pigeon")
    with pytest.raises(SystemExit) as bad:
        main(["check-config"])
    assert bad.value.code == 2
    assert "carrier-pigeon" in capsys.readouterr().out


TRACKER = """\
| ID | Item | Gate | Status | Done |
|---|---|---|---|---|
| ~~W01~~ | ~~Repo scaffold~~ | P | done | 2026-10-09 · abc1234 |
| W02 | Docs | P | doing | |
| W02 | Docs again | P | todo | |
| ~~W03~~ | ~~Compose~~ | P | done | soon |
| W04 | Core | P | waiting | |
| W05 | Seed | P | blocked | |
| R01 | Rejected thing | never needed |
"""

CHECKLIST = """\
- [x] **P** `EC-A01` Something done
- [ ] `EC-O01` Later thing
- [ ] **P** `W01` Clashes with a tracker ID
"""


@pytest.mark.item("W08.1")
def test_tracker_problems_found() -> None:
    tracker = _script("check_tracker")
    rows = tracker.parse_tracker(TRACKER)
    checks = tracker.parse_checklist(CHECKLIST)
    assert [r.id for r in rows] == ["W01", "W02", "W02", "W03", "W04", "W05", "R01"]
    assert rows[0].struck
    assert checks[1].gate == "1"
    problems = "\n".join(tracker.check_rows(rows, checks))
    assert "duplicate ID W02" in problems
    assert "W03 is done; give" in problems
    assert "W04 has unknown status 'waiting'" in problems
    assert "W05 is blocked; give the reason" in problems
    assert "duplicate ID W01" in problems
    assert "W01 is done" not in problems
    assert "R01" not in problems


@pytest.mark.item("W08.1")
@pytest.mark.parametrize(
    ("subject", "ok"),
    [
        ("feat(billing): M07 part payment", True),
        ("chore: W01 scaffold", True),
        ("fix(core)!: EC-B01 audit rule", True),
        ("feat(billing): part payment", False),
        ("feat(billing): M07part payment", False),
    ],
)
def test_commit_subject_needs_id(subject: str, ok: bool) -> None:
    tracker = _script("check_tracker")
    assert bool(tracker.COMMIT_RE.match(subject)) is ok


@pytest.mark.item("M25.1")
def test_docs_links_skip_code_and_remote() -> None:
    linked = _script("check_docs_linked")
    text = "\n".join(
        [
            "See [Login](getting-started/login.md#steps) and [site](https://example.org/a.md).",
            "Write links as `[Title](../area/page.md)`.",
            "```",
            "[Inside a fence](nowhere.md)",
            "```",
            "[After](admin/branches.md)",
        ]
    )
    assert linked.relative_links(text) == [
        (1, "getting-started/login.md"),
        (6, "admin/branches.md"),
    ]


REGISTER = """\
| Component | Kind | Gate | Licence | Pinned | Latest · date | Rel. 12m | Status |
|---|---|---|---|---|---|---|---|
| `alpha` | runtime | P | MIT OR GPL-3.0-only | 1.0 | 1.0 | 1 | Active |
| `psycopg` | runtime | P | LGPL-3.0-only | 3.3.6 | 3.3.6 | 1 | Active |
| `beta` | runtime | P | LGPL-3.0-only | 2.0 | 2.0 | 1 | Active |
| `gamma` | dev | P | MPL-2.0 | 1.0 | 1.0 | 1 | Active |
| `delta` | runtime | P | MPL-2.0 | 1.0 | 1.0 | 1 | Active |
| `epsilon` | runtime | P | Apache-2.0 AND GPL-2.0-only | 1.0 | 1.0 | 1 | Active |
| `Example Cloud` | service | P | — | — | — | — | Active |
"""


@pytest.mark.item("W13")
def test_register_licence_rules() -> None:
    audit = _script("audit_deps")
    rows = audit.parse_register(REGISTER)
    assert [r.name for r in rows][:2] == ["alpha", "psycopg"]
    assert rows[1].pinned == "3.3.6"
    refused = {r.name for r in rows if audit.licence_problem(r)}
    assert refused == {"beta", "delta", "epsilon"}


@pytest.mark.item("W14")
@pytest.mark.parametrize(
    ("ref", "name"),
    [
        ("postgres:18@sha256:abc", "postgres"),
        ("docker.io/library/caddy:2", "caddy"),
        ("ghcr.io/astral-sh/uv:0.12.18@sha256:abc", "ghcr.io/astral-sh/uv"),
        ("localhost:5000/labra", "localhost:5000/labra"),
    ],
)
def test_image_names(ref: str, name: str) -> None:
    assert _script("audit_deps").image_name(ref) == name


@pytest.mark.item("W14")
@pytest.mark.parametrize(
    ("line", "pinned"),
    [
        ("      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0", True),
        ("      - uses: actions/checkout@v5", False),
        ("        uses: docker/build-push-action@main", False),
    ],
)
def test_action_pinning(line: str, pinned: bool) -> None:
    audit = _script("audit_deps")
    m = audit.USES_RE.match(line)
    assert m is not None
    assert bool(audit.SHA_RE.match(m.group(1).partition("@")[2])) is pinned
