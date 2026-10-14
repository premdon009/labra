"""The command line and the repository gate scripts."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
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
        ["import-starter", "--as", "admin"],
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


PLAN_WITH_A_COPY = """\
## 0. Master tracker
**Progress** (maintained by the script): Work 0/15 · Minimal 0/33

| ID | Item | Gate | Status | Done (date · PR) |
|---|---|---|---|---|
| M01 | Login and roles | P | todo | |
| ~~W01~~ | ~~Repo scaffold~~ | P | done | 2026-10-09 · abc1234 |

| ID | Area | Feature | Where |
|---|---|---|---|
| M07 | Billing | Bill of supply | Row 7 |
"""


@pytest.mark.item("W22")
def test_status_copy_outside_the_tracker_is_refused() -> None:
    tracker = _script("check_tracker")
    problems = tracker.status_copies("docs/design/plan.md", PLAN_WITH_A_COPY)
    assert problems == [
        "docs/design/plan.md:6: M01 has a status row; statuses live only in TRACKER.md",
        "docs/design/plan.md:7: W01 has a status row; statuses live only in TRACKER.md",
        "docs/design/plan.md:2: progress line; it lives only in TRACKER.md",
    ]


@pytest.mark.item("W22")
def test_repo_docs_keep_no_status_copy() -> None:
    assert _script("check_tracker").check_copies() == []


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
| `zeta` | CLI | P | GPL-2.0-only | 1.0 | 1.0 | 1 | Active |
| `eta` | dev | P | GPL-2.0-only | 1.0 | 1.0 | 1 | Active |
| `Example Cloud` | service | P | — | — | — | — | Active |
"""


@pytest.mark.item("W13")
def test_register_licence_rules() -> None:
    audit = _script("audit_deps")
    rows = audit.parse_register(REGISTER)
    assert [r.name for r in rows][:2] == ["alpha", "psycopg"]
    assert rows[1].pinned == "3.3.6"
    refused = {r.name for r in rows if audit.licence_problem(r)}
    # A GPL program is fine as a separate command (CLI), never as a Python package.
    assert refused == {"beta", "delta", "epsilon", "eta"}


FONT_REGISTER = """\
| Component | Kind | Gate | Licence | Pinned | Latest · date | Rel. 12m | Status |
|---|---|---|---|---|---|---|---|
| `some-font` | font | P | OFL-1.1 | 1.0 · 2026-01-01 | 1.0 · 2026-01-01 | — | Stable |
| `font-js` | vendored | P | OFL-1.1 | 1.0 · 2026-01-01 | 1.0 · 2026-01-01 | — | Stable |
| `font-lib` | runtime | P | OFL-1.1 | 1.0 | 1.0 | 1 | Active |
| `pyphen` | runtime | P | MPL-1.1 | 1.0 | 1.0 | 1 | Active |
| `other-mpl` | runtime | P | MPL-1.1 | 1.0 | 1.0 | 1 | Active |
"""


@pytest.mark.item("M17")
def test_ofl_only_for_font_files_and_mpl11_only_for_pyphen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = _script("audit_deps")
    rows = audit.parse_register(FONT_REGISTER)
    refused = {r.name for r in rows if audit.licence_problem(r)}
    assert refused == {"font-js", "font-lib", "other-mpl"}

    files = {"Some-Regular.ttf": b"font", "Some-OFL.txt": b"licence", "some.js": b"code"}
    manifest = {}
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        manifest[name] = {"package": "some-font", "version": "1.0", "sha256": digest}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(audit, "VENDOR", tmp_path)
    problems = audit.check_vendored([r for r in rows if r.name == "some-font"])
    assert problems == ["vendor/some.js: a font row vendors font files only"]


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


@pytest.mark.item("W17")
@pytest.mark.parametrize(
    ("ref", "ok"),
    [
        ("postgres:18@sha256:abc", False),
        ("cloudflare/cloudflared:2026.10.0", False),
        ("docker.io/library/postgres:18@sha256:abc", True),
        ("ghcr.io/astral-sh/uv:0.12.18", True),
        ("localhost:5000/labra", True),
        ("localhost/labra:dev", True),
    ],
)
def test_image_refs_name_their_registry(ref: str, ok: bool) -> None:
    # Podman refuses short names when it has no registry search list.
    assert _script("audit_deps").fully_qualified(ref) is ok


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


NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)

AGE_REGISTER = """\
| Component | Kind | Gate | Licence | Pinned | Latest · date |
|---|---|---|---|---|---|
| `alpha` | runtime | P | MIT | 1.0 | 1.0 |
| `actions/old` | action | P | MIT | v1.0.0 · 2026-09-01 | — |
| `actions/new` | action | P | MIT | v2.0.0 · 2026-10-10 | — |
| `actions/undated` | action | P | MIT | v3.0.0 | — |
| `kaniko` | CLI | P | Apache-2.0 | v1.0 · 2026-10-12 | — |

## Age exceptions

| Component | Version | Advisory | Why it can't wait | Added |
|---|---|---|---|---|
"""


def _locked(name: str, version: str, *uploads: datetime | None) -> dict:
    files = [{"url": "x"} if u is None else {"upload-time": f"{u:%Y-%m-%dT%H:%M:%S.%f}Z"}
             for u in uploads]  # fmt: skip
    return {"name": name, "version": version, "source": {"registry": "https://pypi.org/simple"},
            "sdist": files[0], "wheels": files[1:]}  # fmt: skip


def _age_problems(
    register: str, packages: dict[str, dict], exempt: frozenset[str] | set[str] = frozenset()
) -> list[str]:
    audit = _script("audit_deps")
    rows, exceptions = audit.parse_register(register), audit.parse_exceptions(register)
    return audit.check_age(rows, exceptions, packages, set(exempt), NOW)


@pytest.mark.item("W21")
def test_age_python_packages_from_their_lock_upload_time() -> None:
    packages = {
        "old": _locked("old", "1.0", NOW - timedelta(days=8), NOW - timedelta(days=1)),
        "young": _locked("young", "2.0", NOW - timedelta(days=6)),
        "unknown": _locked("unknown", "3.0", None),
        "labra": {"name": "labra", "version": "0.1.0", "source": {"editable": "."}},
    }
    problems = [p for p in _age_problems(AGE_REGISTER, packages) if p.startswith("uv.lock")]
    assert len(problems) == 2
    assert problems[0] == "uv.lock: unknown 3.0 has no upload-time; re-lock with uv"
    assert problems[1].startswith("uv.lock: young 2.0 was released 2026-10-08 12:00 UTC")
    assert "allowed from 2026-10-15 12:00 UTC" in problems[1]


@pytest.mark.item("W21")
def test_age_dated_rows_count_from_the_end_of_their_day() -> None:
    problems = _age_problems(AGE_REGISTER, {})
    assert len(problems) == 3
    # Released some time on 2026-10-10, so allowed once that day is 7 days behind.
    assert problems[0].startswith("DEPENDENCIES.md:5: actions/new v2.0.0 was released 2026-10-10")
    assert "allowed from 2026-10-18 00:00 UTC" in problems[0]
    assert problems[1] == (
        "DEPENDENCIES.md:6: actions/undated: Pinned needs the release date, "
        "as `v3.0.0 · YYYY-MM-DD`"
    )
    # A CLI row needs no date, but a date it gives is checked.
    assert problems[2].startswith("DEPENDENCIES.md:7: kaniko v1.0 was released 2026-10-12")
    allowed = AGE_REGISTER + "| `kaniko` | v1.0 | CVE-2026-12345 | fix | 2026-10-14 |\n"
    assert not any("kaniko" in p for p in _age_problems(allowed, {}))


@pytest.mark.item("W21")
def test_age_exception_needs_an_advisory_the_pinned_version_and_its_uv_entry() -> None:
    young = {"young": _locked("young", "2.0", NOW - timedelta(days=1))}

    def with_rows(*rows: str) -> str:
        return AGE_REGISTER.replace("| `actions/new` |", "| `actions/skip` |") + "".join(rows)

    good = with_rows(
        "| `young` | 2.0 | GHSA-abcd-23fg-hj45 | remote code execution | 2026-10-14 |\n",
        "| `actions/skip` | v2.0.0 | CVE-2026-12345 | token leak | 2026-10-14 |\n",
    )
    assert [p for p in _age_problems(good, young, {"young"}) if "actions/undated" not in p] == [
        "DEPENDENCIES.md:7: kaniko v1.0 was released 2026-10-12, under 7 days ago; allowed from "
        "2026-10-20 00:00 UTC, or sooner only with an Age exceptions row naming its advisory"
    ]

    bad = with_rows(
        "| `young` | 2.0 | upstream says so | crash | 2026-10-14 |\n",
        "| `actions/skip` | v1.9.0 | PYSEC-2026-7 | stale | 2026-10-01 |\n",
    )
    problems = _age_problems(bad, young)
    assert (
        "DEPENDENCIES.md:13: age exception young 2.0: advisory 'upstream says so' isn't a GHSA, "
        "CVE or PYSEC ID" in problems
    )
    assert (
        "DEPENDENCIES.md:14: age exception actions/skip v1.9.0: the pinned version is v2.0.0; "
        "drop the row" in problems
    )
    assert "pyproject.toml: age exception young needs an exclude-newer-package entry" in problems
    assert any(
        p.startswith("DEPENDENCIES.md:5: actions/skip v2.0.0 was released") for p in problems
    )

    stray = _age_problems(AGE_REGISTER, young, {"young"})
    assert "pyproject.toml: exclude-newer-package young has no Age exceptions row" in stray


@pytest.mark.item("W21")
def test_age_exception_noted_once_no_longer_needed() -> None:
    audit = _script("audit_deps")
    register = AGE_REGISTER + (
        "| `old` | 1.0 | GHSA-abcd-23fg-hj45 | fix | 2026-10-01 |\n"
        "| `actions/new` | v2.0.0 | CVE-2026-12345 | fix | 2026-10-10 |\n"
    )
    packages = {"old": _locked("old", "1.0", NOW - timedelta(days=13))}
    notes = audit.unneeded_exceptions(
        audit.parse_register(register), audit.parse_exceptions(register), packages, NOW
    )
    assert notes == [
        "age exception for old 1.0 is no longer needed; drop its row and any "
        "exclude-newer-package entry"
    ]


@pytest.mark.item("W21")
def test_exception_rows_are_not_register_rows() -> None:
    audit = _script("audit_deps")
    register = AGE_REGISTER + "| `alpha` | 1.1 | CVE-2026-12345 | fix | 2026-10-14 |\n"
    assert [r.name for r in audit.parse_register(register)] == [
        "alpha", "actions/old", "actions/new", "actions/undated", "kaniko"
    ]  # fmt: skip
    assert [(e.name, e.version) for e in audit.parse_exceptions(register)] == [("alpha", "1.1")]
    assert audit.parse_register(register)[1].version == "v1.0.0"
    assert audit.parse_register(register)[1].released == "2026-09-01"


@pytest.mark.item("W21")
@pytest.mark.parametrize(
    ("comment", "ok"), [(" # v1.0.0", True), (" # v1.1.0", False), ("", False)]
)
def test_action_comment_names_the_row_version(
    comment: str, ok: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The date in the row belongs to that version, so a new SHA must change the row too.
    audit = _script("audit_deps")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    sha = "a" * 40
    (workflows / "ci.yml").write_text(f"    steps:\n      - uses: actions/old@{sha}{comment}\n")
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "WORKFLOWS", workflows)
    rows = [r for r in audit.parse_register(AGE_REGISTER) if r.name == "actions/old"]
    problems = audit.check_actions(rows)
    assert (problems == []) is ok
    if not ok:
        assert problems == [
            ".github/workflows/ci.yml:2: actions/old needs the comment `# v1.0.0`, the version "
            "its row pins; update the row's version and date when the SHA changes"
        ]


@pytest.mark.item("W21")
def test_dated_vendored_row_matches_its_manifest_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = _script("audit_deps")
    asset = b"/* synthetic */\n"
    (tmp_path / "lib.js").write_bytes(asset)
    manifest = {"lib.js": {"package": "lib", "version": "1.2.0",
                           "sha256": hashlib.sha256(asset).hexdigest()}}  # fmt: skip
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(audit, "VENDOR", tmp_path)
    row = "| `lib` | vendored | P | MIT | {} | — |\n"
    assert audit.check_vendored(audit.parse_register(row.format("1.2.0 · 2026-09-01"))) == []
    assert audit.check_vendored(audit.parse_register(row.format("1.1.0 · 2026-09-01"))) == [
        "DEPENDENCIES.md:1: lib pinned 1.1.0, manifest has 1.2.0"
    ]


@pytest.mark.item("W20")
@pytest.mark.parametrize(
    "url", ["sqlite:///labra.db", "mysql+pymysql://labra:hunter2@db.example/labra"]
)
def test_check_config_refuses_other_databases(
    url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LABRA_DATABASE_URL", url)
    with pytest.raises(SystemExit) as bad:
        main(["check-config"])
    out = capsys.readouterr().out
    assert bad.value.code == 2
    assert "LABRA_DATABASE_URL must start with postgresql://" in out
    assert "hunter2" not in out


SAMPLE_REPO = {
    "src/labra/core/ports.py": 'GROUPS = {"mailer": "labra.mailer"}\n',
    "src/labra/core/config.py": (
        "class Settings:\n    mailer: str = 'console'\n    url: str = ''\n"
    ),
    "src/labra/core/dialect.py": "from sqlalchemy.dialects.postgresql import JSONB\n",
    "src/labra/migrations/versions/0001.py": "from sqlalchemy.dialects import postgresql\n",
    "src/labra/billing/service.py": "# func.similarity is reached through the seam\nx = 1\n",
    "pyproject.toml": (
        '[project.entry-points."labra.mailer"]\n'
        'console = "a:B"\nsmtp = "a:C"\n\n'
        '[project.entry-points."other.group"]\nx = "a:D"\n'
    ),
    "compose.yaml": (
        "name: labra\nservices:\n"
        "  db:\n    image: docker.io/library/postgres:18@sha256:abc\n"
        "  web:\n    image: ${LABRA_IMAGE:-ghcr.io/example/labra:0.1.0}\n"
        "    environment:\n      LABRA_MAILER: ${LABRA_MAILER:-console}\n"
        "  tunnel:\n    image: docker.io/cloudflare/cloudflared:2026.1\n"
        "    profiles: [tunnel]\n"
        "volumes:\n  pgdata:\n"
    ),
    "deploy/x/compose.x.yaml": "services:\n  proxy:\n    image: nginx:1.30\n",
    "src/labra/static/vendor/manifest.json": '{"htmx.min.js": {"package": "htmx.org"}}',
    "docs/TRACKER.md": (
        "| ID | Item | Gate | Status | Done |\n|---|---|---|---|---|\n"
        "| X40 | Second engine | — | todo | |\n"
        "| ~~M16~~ | ~~Backups~~ | P | done | 2026-10-01 · abc1234 |\n"
    ),
    "docs/adr/0003-stack.md": "# Stack\n",
    "tests/t.py": "def test_ok() -> None:\n    pass\n",
    "bin/up.sh": "#!/bin/sh\n",
}

SAMPLE_REGISTER = """\
# Services

## Register

| Service | Kind | Default | Alternatives | Selected by | Proof | Status |
|---|---|---|---|---|---|---|
| Database | setting | `db`, `postgres` | — | `LABRA_URL` | `tests/t.py::test_ok` | swappable |
| Engine | setting | PostgreSQL | MariaDB | `LABRA_URL` | X40 | planned |
| `labra.mailer` | port | `console` | `smtp` | `LABRA_MAILER` | `tests/t.py::test_ok` | swappable |
| App | script | `labra` image, `web` | — | `LABRA_IMAGE` | `bin/up.sh` | swappable |
| Proxy | compose | `proxy` | `deploy/x/compose.x.yaml`, `nginx` | — | `bin/up.sh` | swappable |
| Remote | compose | `--profile tunnel`, `cloudflared` image | — | — | `bin/up.sh` | swappable |
| UI | vendored | `htmx.org` | — | — | [ADR-0003](../adr/0003-stack.md) | fixed |

Text after the table.
"""


def _services_problems(
    tmp_path: Path, replace: tuple[str, str] = ("", ""), files: dict[str, str] | None = None
) -> list[str]:
    mod = _script("check_services")
    for rel, text in {**SAMPLE_REPO, **(files or {})}.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    old, new = replace
    assert old in SAMPLE_REGISTER
    register = SAMPLE_REGISTER.replace(old, new) if old else SAMPLE_REGISTER
    (tmp_path / mod.REGISTER).parent.mkdir(parents=True)
    (tmp_path / mod.REGISTER).write_text(register)
    sources = {
        p.relative_to(tmp_path).as_posix(): p.read_text()
        for p in (tmp_path / "src" / "labra").rglob("*.py")
    }
    return mod.check(register, mod.gather(tmp_path), sources, tmp_path)


@pytest.mark.item("W20")
def test_service_register_passes() -> None:
    assert _script("check_services").main(["--check"]) == 0


@pytest.mark.item("W20")
def test_sample_service_register_passes(tmp_path: Path) -> None:
    assert _services_problems(tmp_path) == []


@pytest.mark.item("W20")
@pytest.mark.parametrize(
    ("old", "new", "problem"),
    [
        ("| `labra.mailer` |", "| Mail |", "port group 'labra.mailer' has no row"),
        ("`smtp`", "SMTP", "entry point 'labra.mailer:smtp' isn't named in its row"),
        ("`LABRA_MAILER`", "`LABRA_MAILLER`", "LABRA_MAILLER is neither a setting"),
        ("| `db`, `postgres` |", "| `postgres` |", "Compose service 'db' has no row"),
        ("`--profile tunnel`", "the tunnel", "Compose profile 'tunnel' has no row"),
        (
            "`deploy/x/compose.x.yaml`",
            "an override",
            "Compose override 'deploy/x/compose.x.yaml' has no row",
        ),
        ("`cloudflared` image", "a tunnel image", "image 'cloudflared' has no row"),
        ("| `htmx.org` |", "| htmx |", "vendored asset 'htmx.org' has no row"),
        ("| port |", "| plugin |", "unknown kind 'plugin'"),
        ("| fixed |", "| frozen |", "unknown status 'frozen'"),
        ("::test_ok` | swappable |", "::test_gone` | swappable |", "no test test_gone"),
        ("`bin/up.sh` | swappable |", "`bin/gone.sh` | swappable |", "doesn't exist"),
        ("| `bin/up.sh` |", "| by hand |", "names the test or script that proves it"),
        ("| X40 |", "| M16 |", "M16 is done; update the row"),
        ("| X40 |", "| X39 |", "X39 isn't in docs/TRACKER.md"),
        ("| X40 |", "| soon |", "a planned row names its tracker ID"),
        ("(../adr/0003-stack.md)", "(../adr/0099-gone.md)", "0099-gone.md doesn't exist"),
        ("| Proof |", "| Tests |", "columns must be"),
    ],
)
def test_service_register_problems_found(tmp_path: Path, old: str, new: str, problem: str) -> None:
    problems = _services_problems(tmp_path, (old, new))
    assert any(problem in p for p in problems), problems


@pytest.mark.item("W20")
@pytest.mark.parametrize(
    ("line", "what"),
    [
        ("from sqlalchemy.dialects.postgresql import JSONB", "a sqlalchemy.dialects import"),
        ("import sqlalchemy.dialects.postgresql", "a sqlalchemy.dialects import"),
        ("rank = func.similarity(Patient.name, q)", "a Postgres function"),
        ("names = select(func.unnest(Test.aliases))", "a Postgres function"),
        ('db.execute(text("select pg_advisory_xact_lock(1)"))', "a Postgres lock"),
        ("stmt = stmt.ext(distinct_on(Result.parameter_id))", "DISTINCT ON"),
        ('match = Patient.name.op("%")(q)', "the trigram % operator"),
        ("extra = mapped_column(Json, server_default=text(\"'{}'::jsonb\"))", "a Postgres cast"),
    ],
)
def test_postgres_only_code_outside_the_seam_found(tmp_path: Path, line: str, what: str) -> None:
    problems = _services_problems(tmp_path, files={"src/labra/patients/service.py": line + "\n"})
    assert problems == [f"src/labra/patients/service.py:1: {what}; use labra.core.dialect instead"]


@pytest.mark.item("W20")
def test_new_compose_service_needs_a_row(tmp_path: Path) -> None:
    compose = SAMPLE_REPO["compose.yaml"].replace(
        "volumes:", "  cache:\n    image: docker.io/library/valkey:9\nvolumes:"
    )
    problems = _services_problems(tmp_path, files={"compose.yaml": compose})
    assert problems == [
        "compose.yaml:12: Compose service 'cache' has no row in docs/dev/services.md",
        "compose.yaml:13: image 'valkey' has no row in docs/dev/services.md",
    ]


@pytest.mark.item("W20")
def test_compose_read_in_any_block_layout() -> None:
    mod = _script("check_services")
    facts = mod.Facts()
    text = (
        "services:\n"
        "    # the database\n"
        '    "db":\n'
        '        image: "docker.io/library/postgres:18"  # pinned in the real file\n'
        "        profiles:\n"
        "        - extra\n"
        "        - 'more'\n"
        "    cache:\n"
        "        image: ${CACHE_IMAGE:-docker.io/library/valkey:9}\n"
        "        profiles: [ 'warm', cold ]\n"
        "volumes:\n"
        "    pgdata:\n"
    )
    mod.compose_facts(text, "compose.yaml", facts)
    assert [(f.name, f.where) for f in facts.services] == [
        ("db", "compose.yaml:3"),
        ("cache", "compose.yaml:8"),
    ]
    assert [f.name for f in facts.images] == ["postgres", "valkey"]
    assert [f.name for f in facts.profiles] == ["extra", "more", "warm", "cold"]
    assert facts.problems == []


@pytest.mark.item("W20")
@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("services: {db: {image: postgres}}\n", 1),
        ("services:\n  db: {image: postgres}\n", 2),
    ],
)
def test_compose_flow_style_services_refused(text: str, line: int) -> None:
    mod = _script("check_services")
    facts = mod.Facts()
    mod.compose_facts(text, "compose.yaml", facts)
    assert facts.problems == [f"compose.yaml:{line}: {mod.FLOW_STYLE}"]


def _gate(logs: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LABRA_CI_LOGS": str(logs)}
    return subprocess.run(  # noqa: S603
        [str(ROOT / "scripts" / "ci_local.sh"), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.item("W08")
def test_ci_local_keeps_run_logs(tmp_path: Path) -> None:
    done = _gate(tmp_path, "--only", "services", "--quiet")
    assert done.returncode == 0, done.stdout + done.stderr
    (run,) = tmp_path.iterdir()
    assert {p.name for p in run.iterdir()} == {"services.log", "summary.txt"}
    assert "services   PASS" in (run / "summary.txt").read_text()
    assert f"Logs: {run}" in done.stdout


@pytest.mark.item("W08")
def test_ci_local_prunes_old_runs_but_keeps_the_newest_failed(tmp_path: Path) -> None:
    old_failed, older_failed = tmp_path / "20200101T000002Z", tmp_path / "20200101T000001Z"
    for run in (older_failed, old_failed):
        run.mkdir()
        (run / "failed").touch()
    old = [tmp_path / f"202001{day:02}T000000Z" for day in range(2, 13)]
    for run in old:
        run.mkdir()
    (tmp_path / "history.tsv").touch()
    done = _gate(tmp_path, "--only", "services", "--quiet")
    assert done.returncode == 0, done.stdout + done.stderr
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left[0] == old_failed.name
    assert left[1:10] == [p.name for p in old[-9:]]
    assert left[10] > "2026"
    assert left[11:] == ["history.tsv"]


PYTEST_CLEAN = """\
..........                                                               [100%]
10 passed in 0.50s
"""
PYTEST_RERUNS = """\
..R..R.F.RE                                                              [100%]
=================================== FAILURES ===================================
_________________________________ test_broken __________________________________
E       assert 1 == 2
=========================== rerun test summary info ============================
RERUN tests/test_a.py::test_flaky
PASSED tests/test_a.py::test_flaky
RERUN tests/test_a.py::test_broken
FAILED tests/test_a.py::test_broken
RERUN tests/test_b.py::test_setup[one - two]
ERROR tests/test_b.py::test_setup[one - two]
=========================== short test summary info ============================
FAILED tests/test_a.py::test_broken - assert 1 == 2
ERROR tests/test_b.py::test_setup[one - two]
SKIPPED [1] tests/test_c.py:4: no Postgres for tests
2 failed, 6 passed, 1 skipped, 3 rerun in 0.90s
"""
PYTEST_FLAKY = """\
..R.                                                                     [100%]
=========================== rerun test summary info ============================
RERUN tests/test_a.py::test_flaky
PASSED tests/test_a.py::test_flaky
4 passed, 1 rerun in 0.30s
"""


@pytest.mark.item("W08")
@pytest.mark.parametrize(
    ("output", "rc", "lines", "flaky"),
    [
        (PYTEST_CLEAN, 0, [], None),
        (
            PYTEST_RERUNS,
            1,
            [
                "failed: tests/test_a.py::test_broken",
                "failed: tests/test_b.py::test_setup[one - two]",
                "flaky (passed on re-run): tests/test_a.py::test_flaky",
            ],
            "tests/test_a.py::test_flaky\n",
        ),
        (
            PYTEST_FLAKY,
            1,
            ["flaky (passed on re-run): tests/test_a.py::test_flaky"],
            "tests/test_a.py::test_flaky\n",
        ),
    ],
)
def test_pytest_summary_names_failed_and_flaky_tests(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output: str,
    rc: int,
    lines: list[str],
    flaky: str | None,
) -> None:
    (tmp_path / "pytest.txt").write_text(output)
    assert _script("pytest_summary").main([str(tmp_path / "pytest.txt"), str(tmp_path)]) == rc
    assert capsys.readouterr().out.splitlines() == lines
    flaky_txt = tmp_path / "flaky.txt"
    assert (flaky_txt.read_text() if flaky_txt.exists() else None) == flaky


HISTORY = """\
run\tcommit\ttest\toutcome
20261001T090000Z\taaa1111\t*\trun
20261001T090000Z\taaa1111\ttests/test_a.py::test_slow\tfailed
20261002T090000Z\tbbb2222\t*\trun
20261002T090000Z\tbbb2222\ttests/test_a.py::test_clock\tflaky
20261003T090000Z\tccc3333-dirty\t*\trun
20261003T090000Z\tccc3333-dirty\ttests/test_a.py::test_clock\tflaky
20261003T090000Z\tccc3333-dirty\ttests/test_b.py::test_order\tflaky
20261004T090000Z\tddd4444\t*\trun
"""


@pytest.mark.item("W08")
@pytest.mark.parametrize(
    ("history", "args", "lines"),
    [
        (
            HISTORY,
            [],
            [
                "4 runs, 20261001T090000Z to 20261004T090000Z",
                "2 flaky / 0 failed / 4 runs  tests/test_a.py::test_clock"
                "  last: 20261003T090000Z ccc3333-dirty",
                "1 flaky / 0 failed / 4 runs  tests/test_b.py::test_order"
                "  last: 20261003T090000Z ccc3333-dirty",
                "0 flaky / 1 failed / 4 runs  tests/test_a.py::test_slow"
                "  last: 20261001T090000Z aaa1111",
            ],
        ),
        (
            HISTORY,
            ["--last", "2"],
            [
                "2 runs, 20261003T090000Z to 20261004T090000Z",
                "1 flaky / 0 failed / 2 runs  tests/test_a.py::test_clock"
                "  last: 20261003T090000Z ccc3333-dirty",
                "1 flaky / 0 failed / 2 runs  tests/test_b.py::test_order"
                "  last: 20261003T090000Z ccc3333-dirty",
            ],
        ),
        (
            HISTORY.split("20261002")[0],
            ["--last", "1"],
            [
                "1 run, 20261001T090000Z to 20261001T090000Z",
                "0 flaky / 1 failed / 1 run  tests/test_a.py::test_slow"
                "  last: 20261001T090000Z aaa1111",
            ],
        ),
        (
            HISTORY.split("20261001T090000Z\taaa1111\ttests")[0],
            [],
            ["1 run, 20261001T090000Z to 20261001T090000Z", "no test was flaky or failed"],
        ),
        ("", [], ["no runs recorded"]),
        (None, [], ["no runs recorded"]),
    ],
)
def test_flaky_report_counts_per_test(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    history: str | None,
    args: list[str],
    lines: list[str],
) -> None:
    path = tmp_path / "history.tsv"
    if history is not None:
        path.write_text(history)
    assert _script("flaky_report").main(["--history", str(path), *args]) == 0
    assert capsys.readouterr().out.splitlines() == lines


@pytest.mark.item("W08")
def test_pytest_summary_appends_to_the_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _script("pytest_summary")
    history = tmp_path / "history.tsv"
    history.write_text(HISTORY)
    (tmp_path / "pytest.txt").write_text(PYTEST_CLEAN)
    pytest_txt = tmp_path / "pytest.txt"
    common = [str(pytest_txt), str(tmp_path), "--history", str(history), "--commit", "eee5555"]
    pytest_txt.write_text(PYTEST_CLEAN)
    assert mod.main([*common, "--run", "20261005T090000Z"]) == 0
    pytest_txt.write_text(PYTEST_RERUNS.replace("test_flaky", "test_clock"))
    assert mod.main([*common, "--run", "20261006T090000Z"]) == 1
    assert history.read_text().splitlines()[-5:] == [
        "20261005T090000Z\teee5555\t*\trun",
        "20261006T090000Z\teee5555\t*\trun",
        "20261006T090000Z\teee5555\ttests/test_a.py::test_broken\tfailed",
        "20261006T090000Z\teee5555\ttests/test_b.py::test_setup[one - two]\tfailed",
        "20261006T090000Z\teee5555\ttests/test_a.py::test_clock\tflaky",
    ]
    assert "  flaky 3 times in the last 6 runs; see scripts/flaky_report.py" in (
        capsys.readouterr().out.splitlines()
    )


@pytest.mark.item("W08")
def test_pytest_summary_starts_a_history(tmp_path: Path) -> None:
    (tmp_path / "pytest.txt").write_text(PYTEST_CLEAN)
    run_dir, history = tmp_path / "20261007T090000Z", tmp_path / "history.tsv"
    run_dir.mkdir()
    _script("pytest_summary").main(
        [str(tmp_path / "pytest.txt"), str(run_dir), "--history", str(history)]
    )
    assert history.read_text().splitlines() == [
        "run\tcommit\ttest\toutcome",
        "20261007T090000Z\tunknown\t*\trun",
    ]


@pytest.mark.item("W08")
def test_ci_local_prunes_same_second_runs_in_start_order(tmp_path: Path) -> None:
    same = [
        tmp_path / "20200101T000000Z",
        *(tmp_path / f"20200101T000000Z-{n}" for n in range(2, 13)),
    ]
    for run in same:
        run.mkdir()
    done = _gate(tmp_path, "--only", "services", "--quiet")
    assert done.returncode == 0, done.stdout + done.stderr
    left = {p.name for p in tmp_path.iterdir()}
    assert len(left) == 10
    assert {p.name for p in same[-9:]} <= left


@pytest.mark.item("W08")
def test_flaky_report_orders_same_second_runs_by_suffix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs = ["20261001T090000Z", *(f"20261001T090000Z-{n}" for n in range(2, 11))]
    rows = [f"{run}\taaa1111\t*\trun" for run in runs]
    rows += [f"{run}\taaa1111\ttests/test_a.py::test_clock\tflaky" for run in runs[-2:]]
    history = tmp_path / "history.tsv"
    history.write_text("run\tcommit\ttest\toutcome\n" + "\n".join(rows) + "\n")
    assert _script("flaky_report").main(["--history", str(history), "--last", "2"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "2 runs, 20261001T090000Z-9 to 20261001T090000Z-10",
        "2 flaky / 0 failed / 2 runs  tests/test_a.py::test_clock"
        "  last: 20261001T090000Z-10 aaa1111",
    ]
    assert _script("pytest_summary").recent_flaky(history, "tests/test_a.py::test_clock", 2) == (
        2,
        2,
    )
