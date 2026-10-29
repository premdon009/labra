"""The command line and the repository gate scripts."""

import fnmatch
import gc
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy.exc import SADeprecationWarning

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


DEV_IMAGE_REGISTER = """\
| Component | Kind | Gate | Licence | Pinned | Latest · date | Rel. 12m | Status |
|---|---|---|---|---|---|---|---|
| `ubuntu` | dev-image | P | GPL-2.0-only | 26.04 · 2026-01-01 | 26.04 | — | Active |
| `debian` | dev-image | P | GPL-2.0-only | 13 · 2026-01-01 | 13 | — | Active |
| `ghcr.io/astral-sh/uv` | image | P | MIT | 1.0 · 2026-01-01 | 1.0 | — | Active |
| `busybox` | image | P | GPL-2.0-only | 1.0 · 2026-01-01 | 1.0 | — | Active |
| `docker/dockerfile` | dev-image | P | Apache-2.0 | 1.0 · 2026-01-01 | 1.0 | — | Active |
| `ghcr.io/example/builder` | dev-image | P | Apache-2.0 | 1.0 · 2026-01-01 | 1.0 | — | Active |
"""


@pytest.mark.item("W31")
def test_gpl_only_for_an_image_that_is_never_shipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = _script("audit_deps")
    rows = audit.parse_register(DEV_IMAGE_REGISTER)
    assert {r.name for r in rows if audit.licence_problem(r)} == {"busybox"}

    digest = "@sha256:" + "0" * 64
    shipped, lab = tmp_path / "Dockerfile", tmp_path / "Containerfile"
    script = tmp_path / "build.sh"
    # The frontend of a shipped image's build runs in the build only.
    shipped.write_text(
        f"# syntax=docker.io/docker/dockerfile:1.0{digest}\n"
        f"FROM docker.io/library/debian:13{digest}\nFROM docker.io/library/busybox:1{digest}\n",
        encoding="utf-8",
    )
    uv = f"FROM ghcr.io/astral-sh/uv:1.0{digest} AS uv\n"
    lab.write_text(f"{uv}FROM docker.io/library/ubuntu:26.04{digest}\n", encoding="utf-8")
    script.write_text(f"BUILDER_IMAGE=ghcr.io/example/builder:1.0{digest}\n", encoding="utf-8")
    monkeypatch.setattr(audit, "IMAGE_FILES", (shipped,))
    monkeypatch.setattr(audit, "DEV_IMAGE_FILES", (lab, script))
    assert audit.check_images(rows) == [
        "Dockerfile:2: image debian is shipped; its row's kind is image"
    ]
    shipped.write_text(
        "# syntax=docker/dockerfile:1\n"
        f"FROM docker.io/library/debian:13{digest}\nFROM docker.io/library/busybox:1{digest}\n",
        encoding="utf-8",
    )
    script.write_text("BUILDER_IMAGE=ghcr.io/example/builder:1.0\n", encoding="utf-8")
    assert audit.check_images(rows) == [
        "Dockerfile:1: image docker/dockerfile:1 has no @sha256 digest",
        "Dockerfile:1: image docker/dockerfile:1 needs its registry, e.g. docker.io/library/…",
        "Dockerfile:2: image debian is shipped; its row's kind is image",
        "build.sh:1: image ghcr.io/example/builder:1.0 has no @sha256 digest",
    ]
    script.write_text(f"BUILDER_IMAGE=ghcr.io/example/builder:1.0{digest}\n", encoding="utf-8")
    lab.write_text(f"{uv}FROM scratch\n", encoding="utf-8")
    assert audit.check_images(rows) == [
        "Dockerfile:1: image docker/dockerfile:1 has no @sha256 digest",
        "Dockerfile:1: image docker/dockerfile:1 needs its registry, e.g. docker.io/library/…",
        "Dockerfile:2: image debian is shipped; its row's kind is image",
        "Containerfile:2: image scratch has no @sha256 digest",
        "Containerfile:2: image scratch needs its registry, e.g. docker.io/library/…",
        "Containerfile:2: image scratch has no row in docs/DEPENDENCIES.md",
        "DEPENDENCIES.md:3: image ubuntu isn't used; drop the row",
    ]


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


def _apt_packages(text: str) -> set[str]:
    """The packages named by the first `apt-get install` in a Dockerfile or a workflow job."""
    text = text.replace("\\\n", " ")
    m = re.search(r"apt-get install (.*?)(?:&&|\n\s*- |\Z)", text, re.S)
    return {w for w in m.group(1).split() if not w.startswith("-")} if m else set()


def _job(workflow: str, name: str) -> str:
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    m = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", text, re.M | re.S)
    assert m is not None, f"{workflow} has no job {name}"
    return m.group(1)


def _row_packages(row: str) -> set[str]:
    """The packages scripts/portability_job.sh --install puts on the runner for a row."""
    text = (ROOT / "scripts" / "portability_job.sh").read_text(encoding="utf-8")
    m = re.search(rf'^  \[{row}\]="([^"]*)"$', text, re.MULTILINE)
    assert m is not None, f"portability_job.sh installs nothing for {row}"
    return set(m.group(1).split())


@pytest.mark.item("W23")
@pytest.mark.parametrize(
    ("workflow", "job"), [("ci.yml", "gate"), ("portability.yml", "outside-postgres")]
)
def test_ci_test_jobs_get_the_images_pdf_libraries_on_the_snapshot_os(
    workflow: str, job: str
) -> None:
    image = _apt_packages((ROOT / "Dockerfile").read_text(encoding="utf-8"))
    assert {"libpango-1.0-0", "libharfbuzz-subset0", "fontconfig"} <= image
    text = _job(workflow, job)
    if f"scripts/portability_job.sh --install {job}" in text:
        assert _row_packages(job) == image
    else:
        assert _apt_packages(text) == image
    assert "runs-on: ubuntu-26.04" in text


@pytest.mark.item("W30")
def test_nginx_looks_web_up_again_after_it_is_recreated() -> None:
    # A fixed address breaks when a restore or an upgrade recreates web: nginx answers 502.
    nginx = ROOT / "deploy" / "nginx"
    compose = (nginx / "compose.nginx.yaml").read_text(encoding="utf-8")
    assert "/deploy/nginx/labra.conf:/etc/nginx/templates/default.conf.template:ro" in compose
    assert 'NGINX_ENTRYPOINT_LOCAL_RESOLVERS: "1"' in compose
    conf = (nginx / "labra.conf").read_text(encoding="utf-8")
    assert "resolver ${NGINX_LOCAL_RESOLVERS} valid=10s" in conf
    assert "server web:8000 resolve;" in conf
    proxy = (nginx / "labra-proxy.conf").read_text(encoding="utf-8")
    assert re.findall(r"proxy_pass (\S+);", proxy) == ["http://labra_web"]


@pytest.mark.item("W30")
def test_no_health_check_argument_holds_a_space() -> None:
    # Podman 5 splits a Compose health check's arguments at spaces.
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    checks = [json.loads(m) for m in re.findall(r"^ +test: (\[.*\])$", compose, re.MULTILINE)]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    checks += [json.loads(m) for m in re.findall(r"^ +CMD (\[.*\])$", dockerfile, re.MULTILINE)]
    assert len(checks) >= 3
    assert all(" " not in arg for check in checks for arg in check), checks
    assert ["CMD", "python", "-m", "labra.probe", "/readyz"] in checks
    assert ["python", "-m", "labra.probe", "/healthz"] in checks
    assert "test:\n" not in compose


@pytest.mark.item("W30")
def test_the_nerdctl_job_gives_rootlesskit_an_apparmor_profile_before_setup() -> None:
    text = (ROOT / "scripts" / "portability_job.sh").read_text(encoding="utf-8")
    install = re.search(r"^install_nerdctl\(\) \{\n(.*?)^\}\n\n", text, re.MULTILINE | re.DOTALL)
    row = re.search(r"^  nerdctl\)\n(.*?)^    ;;", text, re.MULTILINE | re.DOTALL)
    assert install is not None and row is not None
    assert "/usr/local/bin/rootlesskit flags=(unconfined) {" in install.group(1)
    assert "userns," in install.group(1)
    profile = install.group(1).index("tee /etc/apparmor.d/usr.local.bin.rootlesskit")
    assert install.group(1).index("systemctl restart apparmor.service") > profile
    # The workflow runs --install, then the row.
    steps = _job("portability.yml", "runtime")
    install_step = "run: scripts/portability_job.sh --install ${{ matrix.row }}"
    assert steps.index(install_step) < steps.index(
        "run: scripts/portability_job.sh ${{ matrix.row }}"
    )
    assert row.group(1).index("containerd-rootless-setuptool.sh install;") < row.group(1).index(
        "compare --runtimes nerdctl"
    )


@pytest.mark.item("W08")
def test_every_job_names_its_runner() -> None:
    # ubuntu-latest moves to a new release on GitHub's schedule, not ours.
    runners = {
        (path.name, m)
        for path in (ROOT / ".github" / "workflows").glob("*.yml")
        for m in re.findall(r"^ *runs-on: (\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
    }
    assert len(runners) >= 4
    assert {runner for _, runner in runners} == {"ubuntu-26.04"}, sorted(runners)


CONCURRENCY = (
    "concurrency:\n"
    "  group: ${{ github.workflow }}-"
    "${{ github.event_name == 'pull_request' && github.ref || github.run_id }}\n"
    "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n"
)


@pytest.mark.item("W08")
@pytest.mark.parametrize("workflow", ["ci.yml", "portability.yml"])
def test_a_new_push_cancels_only_the_pull_requests_older_run(workflow: str) -> None:
    # A group keeps one running and one pending run, so master and scheduled runs each get a
    # group of their own (the run ID), or a newer pending run would replace an older one.
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    assert CONCURRENCY in text
    assert text.index(CONCURRENCY) < text.index("\njobs:\n")


@pytest.mark.item("W01")
@pytest.mark.parametrize(
    ("message", "category"),
    [
        ("The Result.tuples() method is deprecated.", SADeprecationWarning),
        ("add_js is deprecated and will be removed in pypdf 7.0.0.", DeprecationWarning),
    ],
)
def test_a_sqlalchemy_or_pypdf_deprecation_fails_the_test_that_hits_it(
    message: str, category: type[Warning]
) -> None:
    with pytest.raises(category, match="deprecated"):
        warnings.warn(message, category, stacklevel=1)


def _check_shell(script: Path, path: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ | ({"PATH": path} if path is not None else {})
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "scripts" / "check_shell.sh"), str(script)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.item("W25")
def test_shellcheck_findings_fail_the_shell_check(tmp_path: Path) -> None:
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck is not installed")
    script = tmp_path / "greet.sh"
    script.write_text("#!/usr/bin/env bash\necho $1\n", encoding="utf-8")
    loose = _check_shell(script)
    assert loose.returncode == 1
    assert "SC2086" in loose.stdout
    script.write_text('#!/usr/bin/env bash\necho "$1"\n', encoding="utf-8")
    assert _check_shell(script).returncode == 0


@pytest.mark.item("W25")
def test_the_shell_check_is_unchecked_without_shellcheck(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    dirname = shutil.which("dirname")
    assert dirname is not None
    (bin_dir / "dirname").symlink_to(dirname)
    script = tmp_path / "greet.sh"
    script.write_text('#!/usr/bin/env bash\necho "$1"\n', encoding="utf-8")
    result = _check_shell(script, path=str(bin_dir))
    assert result.returncode == 2
    assert "shellcheck not installed" in result.stderr


@pytest.mark.item("W25")
def test_the_gate_and_pre_commit_run_the_shell_check() -> None:
    assert "scripts/check_shell.sh" in (ROOT / "scripts" / "ci_local.sh").read_text("utf-8")
    hooks = (ROOT / ".pre-commit-config.yaml").read_text("utf-8")
    assert "entry: scripts/warn_ok.sh scripts/check_shell.sh" in hooks


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


BINARY_DOCKERFILE = """\
FROM docker.io/library/debian:13@sha256:abc AS fetch
ARG TOOL_VERSION=1.2.0
ARG TOOL_SHA256_AMD64={amd}
ARG TOOL_SHA256_ARM64={arm}
"""


@pytest.mark.item("M16")
@pytest.mark.parametrize(
    ("pinned", "arm", "want"),
    [
        ("1.2.0 · 2026-09-01", "b" * 64, []),
        ("1.1.0 · 2026-09-01", "b" * 64,
         ["DEPENDENCIES.md:1: tool pinned 1.1.0, deploy/x/Dockerfile downloads 1.2.0"]),
        ("1.2.0 · 2026-09-01", "",
         ["deploy/x/Dockerfile:2: tool needs ARG TOOL_SHA256_ARM64=<sha256>"]),
        (None, "b" * 64, ["deploy/x/Dockerfile:2: binary tool has no row in docs/DEPENDENCIES.md"]),
    ],
)  # fmt: skip
def test_a_downloaded_binary_matches_its_row_and_has_a_checksum_per_arch(
    pinned: str | None, arm: str, want: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = _script("audit_deps")
    dockerfile = tmp_path / "deploy" / "x" / "Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text(BINARY_DOCKERFILE.format(amd="a" * 64, arm=arm))
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "BINARY_FILES", {dockerfile: ("AMD64", "ARM64")})
    register = f"| `tool` | binary | P | MIT | {pinned} | — |\n" if pinned else ""
    assert audit.check_binaries(audit.parse_register(register)) == want


@pytest.mark.item("W33")
def test_a_binary_a_script_downloads_needs_a_checksum_for_each_arch_it_fetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = _script("audit_deps")
    script = tmp_path / "scripts" / "job.sh"
    script.parent.mkdir()
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "BINARY_FILES", {script: ("AMD64",)})
    rows = audit.parse_register("| `tool` | binary | P | MIT | 1.2.0 · 2026-09-01 | — |\n")
    script.write_text(f"TOOL_VERSION=1.2.0\nTOOL_SHA256_AMD64={'a' * 64}\n")
    assert audit.check_binaries(rows) == []
    script.write_text(f"TOOL_VERSION=1.3.0\nTOOL_SHA256={'a' * 64}\n")
    assert audit.check_binaries(rows) == [
        "scripts/job.sh:1: tool needs TOOL_SHA256_AMD64=<sha256>",
        "DEPENDENCIES.md:1: tool pinned 1.2.0, scripts/job.sh downloads 1.3.0",
    ]


@pytest.mark.item("W33")
def test_the_real_register_checks_kaniko_nerdctl_and_the_dockerfile_frontend() -> None:
    audit = _script("audit_deps")
    rows = {r.name: r for r in audit.parse_register(audit.REGISTER.read_text(encoding="utf-8"))}
    assert rows["ghcr.io/osscontainertools/kaniko"].kind == "dev-image"
    assert rows["docker/dockerfile"].kind == "dev-image"
    assert rows["nerdctl"].kind == "binary"
    assert audit.check_images(list(rows.values())) == []
    assert audit.check_binaries(list(rows.values())) == []


@pytest.mark.item("W33")
@pytest.mark.parametrize(
    ("latest", "age_days", "hint"),
    [("0.0.73", 1, "Watch"), ("1.4.0", 1, "Active"), ("2.0", 400, "Stable or Watch")],
)
def test_refresh_never_suggests_active_for_a_pre_1_0_package(
    latest: str, age_days: int, hint: str
) -> None:
    # The register's own rule: a pre-1.0 API is a risk to its future, so Watch.
    when = (NOW - timedelta(days=age_days)).date().isoformat()
    assert _script("audit_deps").suggested_status(when, NOW, latest) == hint


@pytest.mark.item("M16")
def test_a_binary_row_with_nothing_downloading_it_is_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = _script("audit_deps")
    monkeypatch.setattr(audit, "BINARY_FILES", {tmp_path / "missing": ("AMD64",)})
    rows = audit.parse_register("| `gone` | binary | P | MIT | 1.0 · 2026-09-01 | — |\n")
    assert audit.check_binaries(rows) == [
        "DEPENDENCIES.md:1: binary gone isn't downloaded anywhere; drop the row"
    ]
    assert audit.check_age(rows, [], {}, set(), NOW) == []
    undated = audit.parse_register("| `gone` | binary | P | MIT | 1.0 | — |\n")
    assert audit.check_age(undated, [], {}, set(), NOW) == [
        "DEPENDENCIES.md:1: gone: Pinned needs the release date, as `1.0 · YYYY-MM-DD`"
    ]


@pytest.mark.item("W29")
def test_the_backup_image_owns_the_files_folder_it_restores_into() -> None:
    # On a new server the restore is the first to mount the files volume, which takes the
    # owner of the image's folder; without one it is root's, and the restore can't write.
    dockerfile = (ROOT / "deploy" / "backup" / "Dockerfile").read_text()
    run = dockerfile[dockerfile.index("RUN useradd ") :]
    run = run[: run.index("\nENV ")]
    assert re.search(r"mkdir -p [^&]*/data/files", run), run
    assert re.search(r"chown -R labra [^&]*/data/files", run), run
    assert "--uid 10001" in run


@pytest.mark.item("W27")
def test_every_service_rotates_its_logs() -> None:
    # The engine's default keeps logs forever; each service caps its own (five 10 MB files).
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    m = re.search(r"^x-logging: &logging\n(.*?)(?=^\S)", compose, re.M | re.S)
    assert m is not None
    assert [line.strip() for line in m.group(1).splitlines() if line.strip()] == [
        "driver: json-file",
        "options:",
        'max-size: "10m"',
        'max-file: "5"',
    ]
    m = re.search(r"^x-labra: &labra\n(.*?)(?=^\S)", compose, re.M | re.S)
    assert m is not None
    assert re.search(r"^  logging: \*logging$", m.group(1), re.M)
    services = compose[compose.index("\nservices:\n") : compose.index("\nnetworks:\n")]
    blocks = re.findall(r"^  (\w+):[^\n]*\n(.*?)(?=^  \w|\Z)", services, re.M | re.S)
    assert len(blocks) >= 9
    for name, body in blocks:
        assert re.search(r"^    (logging: \*logging|<<: \*labra|<<: \*backup)$", body, re.M), name


@pytest.mark.item("M16")
def test_the_backup_job_is_never_started_by_a_plain_up() -> None:
    # Backups run only when a host timer asks (ADR-0013); `up -d` must not start the job.
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    m = re.search(r"^  backup: &backup\n(.*?)(?=^  \S|^\S)", compose, re.M | re.S)
    assert m is not None
    service = m.group(1)
    assert "profiles: [jobs]" in service
    assert 'restart: "no"' in service
    assert "files:/data/files:ro" in service
    assert "edge" not in service
    assert re.search(r"^  egress:\n(?!    internal: true)", compose, re.M)
    # The restore job is the same service with the files writable and the owner's login, and
    # nothing else changed.
    m = re.search(r"^  restore:\n(.*?)(?=^  \S|^\S)", compose, re.M | re.S)
    assert m is not None
    restore = [line.strip() for line in m.group(1).splitlines() if line.strip()]
    assert restore[0] == "<<: *backup"
    assert "- files:/data/files" in restore
    assert [line for line in restore if not line.startswith(("#", "-"))] == [
        "<<: *backup",
        "environment:",
        "<<: *backup-env",
        "LABRA_DATABASE_URL_FILE: /run/secrets/owner_database_url",
        "secrets: [owner_database_url, restic_password, rclone_conf]",
        "volumes:",
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


def _gate(logs: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LABRA_CI_LOGS": str(logs), **env}
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


# Real output of `pytest -q -rfEsR --reruns 1 -n 2 --dist loadfile`: the workers' lines
# arrive interleaved, and each failure names its worker.
PYTEST_XDIST = """\
bringing up nodes...
bringing up nodes...

RER.sRF..                                                                [100%]
==================================== ERRORS ====================================
___________________ ERROR at setup of test_setup[one - two] ____________________
[gw1] linux -- Python 3.14.7 /usr/bin/python3

    @pytest.fixture
    def boom():
>       raise RuntimeError("setup")
E       RuntimeError: setup

tests/test_b.py:4: RuntimeError
=================================== FAILURES ===================================
_________________________________ test_broken __________________________________
[gw0] linux -- Python 3.14.7 /usr/bin/python3

    def test_broken():
>       assert 1 == 2
E       assert 1 == 2

tests/test_a.py:10: AssertionError
=========================== rerun test summary info ============================
RERUN tests/test_a.py::test_flaky
PASSED tests/test_a.py::test_flaky
RERUN tests/test_b.py::test_setup[one - two]
ERROR tests/test_b.py::test_setup[one - two]
RERUN tests/test_a.py::test_broken
FAILED tests/test_a.py::test_broken
=========================== short test summary info ============================
FAILED tests/test_a.py::test_broken - assert 1 == 2
ERROR tests/test_b.py::test_setup[one - two] - RuntimeError: setup
SKIPPED [1] tests/test_b.py:8: no Postgres for tests
1 failed, 3 passed, 1 skipped, 1 error, 3 rerun in 0.68s
"""


@pytest.mark.item("W32")
def test_pytest_summary_reads_parallel_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pytest.txt").write_text(PYTEST_XDIST)
    assert _script("pytest_summary").main([str(tmp_path / "pytest.txt"), str(tmp_path)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "failed: tests/test_a.py::test_broken",
        "failed: tests/test_b.py::test_setup[one - two]",
        "flaky (passed on re-run): tests/test_a.py::test_flaky",
    ]
    # The gate greps the same output for skipped database tests.
    assert re.search("SKIPPED.*no Postgres for tests", PYTEST_XDIST)


@pytest.mark.item("W32")
def test_the_gate_runs_the_tests_in_parallel_then_the_time_budgets_alone() -> None:
    gate = (ROOT / "scripts" / "ci_local.sh").read_text(encoding="utf-8")
    stage = gate.split("stage_tests() {", 1)[1].split("\n}\n", 1)[0]
    common = re.search(r"local pytest=\((.*)\)", stage)
    assert common is not None
    assert "--reruns 1" in common[1]
    assert "--cov " in common[1]
    parallel, serial = (call.split("| tee", 1)[0] for call in stage.split('"${pytest[@]}" ')[1:3])
    assert parallel.startswith('-m "not serial"')
    assert '-n "${LABRA_TEST_WORKERS:-auto}" --maxprocesses 8 --dist loadfile' in parallel
    assert serial.startswith("-m serial")
    assert "--cov-append" in serial
    assert '| tee -a "$out"' in stage
    assert "-n " not in serial


@pytest.mark.item("W32")
def test_the_time_budget_tests_run_serially() -> None:
    marked = {
        path.name
        for path in (ROOT / "tests").glob("test_*.py")
        if "@pytest.mark.serial\n" in path.read_text(encoding="utf-8")
    }
    assert marked == {
        "test_db_laptop_budget.py",
        "test_db_lab_worklist.py",
        "test_db_pdf_snapshots.py",
    }


@pytest.mark.item("W32")
def test_each_worker_gets_its_own_test_database() -> None:
    from tests.conftest import worker_database_url

    server = "postgresql://postgres@localhost:5432/labra_test"
    urls = {worker: worker_database_url(server, worker) for worker in ("", "gw0", "gw1")}
    assert urls[""].endswith("/labra_test")
    assert urls["gw0"].endswith("/labra_gw0_test")
    assert urls["gw1"].endswith("/labra_gw1_test")
    assert all(url.startswith("postgresql+psycopg://") for url in urls.values())
    with pytest.raises(pytest.UsageError):
        worker_database_url("postgresql://postgres@localhost:5432/labra", "gw0")


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


def _path_without(tool: str, tmp_path: Path) -> str:
    """PATH without the directories that hold `tool`, with uv and git still on it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("uv", "git"):
        found = shutil.which(name)
        assert found is not None, f"{name} is not installed"
        (bin_dir / name).symlink_to(found)
    dirs = [d for d in os.environ["PATH"].split(os.pathsep) if d and not (Path(d) / tool).exists()]
    return os.pathsep.join([str(bin_dir), *dirs])


@pytest.mark.item("W37")
def test_strict_counts_a_stage_that_could_not_be_checked_as_failed(tmp_path: Path) -> None:
    path = _path_without("gitleaks", tmp_path)
    loose = _gate(tmp_path / "loose", "--only", "preflight", "--quiet", PATH=path)
    assert loose.returncode == 0, loose.stdout + loose.stderr
    assert "preflight  WARN" in loose.stdout
    strict = _gate(tmp_path / "strict", "--only", "preflight", "--quiet", "--strict", PATH=path)
    assert strict.returncode == 1, strict.stdout + strict.stderr
    assert "preflight  FAIL" in strict.stdout
    assert "WARN counted as FAIL (--strict)" in strict.stdout


@pytest.mark.item("W37")
@pytest.mark.parametrize("workflow", ["ci.yml", "release.yml"])
def test_the_gate_jobs_install_the_tools_and_count_a_warn_as_failed(workflow: str) -> None:
    steps = _job(workflow, "gate")
    gates = re.findall(r"^ +- run: (scripts/ci_local\.sh.*)$", steps, re.MULTILINE)
    assert gates, f"{workflow} runs no gate"
    assert all(gate.startswith("scripts/ci_local.sh --strict") for gate in gates), gates
    install = steps.index("- run: scripts/install_ci_tools.sh")
    assert install < steps.index("- run: scripts/ci_local.sh")


@pytest.mark.item("W37")
def test_the_ci_runner_gets_every_tool_the_gate_can_warn_about() -> None:
    tools = (ROOT / "scripts" / "check_tools.sh").read_text(encoding="utf-8")
    m = re.search(r"^optional=\((.*)\)$", tools, re.MULTILINE)
    assert m is not None
    install = (ROOT / "scripts" / "install_ci_tools.sh").read_text(encoding="utf-8")
    missing = [t for t in m.group(1).split() if f"if ! command -v {t} " not in install]
    assert missing == []
    audit = _script("audit_deps")
    assert ROOT / "scripts" / "install_ci_tools.sh" in audit.BINARY_FILES
    rows = {r.name: r for r in audit.parse_register(audit.REGISTER.read_text(encoding="utf-8"))}
    assert rows["gitleaks"].kind == rows["osv-scanner"].kind == "binary"
    assert audit.check_binaries(list(rows.values())) == []


@pytest.mark.item("W37")
def test_a_binary_variable_with_an_underscore_names_a_hyphenated_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = _script("audit_deps")
    script = tmp_path / "scripts" / "tools.sh"
    script.parent.mkdir()
    script.write_text(f"SOME_TOOL_VERSION=1.2.0\nSOME_TOOL_SHA256_AMD64={'a' * 64}\n")
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "BINARY_FILES", {script: ("AMD64",)})
    rows = audit.parse_register("| `some-tool` | binary | P | MIT | 1.2.0 · 2026-09-01 | — |\n")
    assert audit.check_binaries(rows) == []


def _banned_terms(*files: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "scripts" / "check_banned_terms.sh"), *map(str, files)],
        env={k: v for k, v in os.environ.items() if not k.startswith("LABRA_BANNED")} | env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.item("W46")
def test_the_banned_terms_check_names_the_file_but_never_the_term(tmp_path: Path) -> None:
    terms = tmp_path / "terms.txt"
    terms.write_text("# made up for the test\nZorblax Pathware\n", encoding="utf-8")
    page = tmp_path / "page.md"
    page.write_text("Fine.\nSee zorblax pathware here.\n", encoding="utf-8")
    found = _banned_terms(page, LABRA_BANNED_TERMS=str(terms))
    assert found.returncode == 1, found.stdout + found.stderr
    assert found.stdout.splitlines()[1:] == [str(page)]
    assert "zorblax" not in (found.stdout + found.stderr).lower()


@pytest.mark.item("W46")
def test_a_missing_banned_terms_list_is_skipped_only_where_the_run_allows_it(
    tmp_path: Path,
) -> None:
    missing = str(tmp_path / "none.txt")
    unchecked = _banned_terms(LABRA_BANNED_TERMS=missing)
    assert unchecked.returncode == 2
    assert "WARN: no banned-terms list" in unchecked.stderr
    skipped = _banned_terms(LABRA_BANNED_TERMS=missing, LABRA_BANNED_TERMS_OPTIONAL="1")
    assert skipped.returncode == 0, skipped.stdout + skipped.stderr
    assert "check skipped" in skipped.stdout


@pytest.mark.item("W46")
@pytest.mark.parametrize(("workflow", "optional"), [("ci.yml", True), ("release.yml", False)])
def test_the_gate_jobs_get_the_banned_terms_list_from_a_secret(
    workflow: str, *, optional: bool
) -> None:
    steps = _job(workflow, "gate")
    write = steps.index('- run: printf \'%s\' "$TERMS" >"$RUNNER_TEMP/banned-terms.txt"')
    assert "TERMS: ${{ secrets.BANNED_TERMS }}" in steps[write:]
    gate = steps.index("- run: scripts/ci_local.sh --strict\n")
    assert write < gate
    gate_step = steps[gate:].split("\n      - ", 1)[0]
    assert "LABRA_BANNED_TERMS: ${{ runner.temp }}/banned-terms.txt" in gate_step
    assert ('LABRA_BANNED_TERMS_OPTIONAL: "1"' in gate_step) is optional


@pytest.mark.item("W45")
def test_pip_audit_checks_the_locked_packages_by_their_hashes(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv is not installed"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # The real uv exports the lock; the pip-audit run only records what it was given.
    stub = bin_dir / "uv"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'[[ $1 == export ]] && exec {uv} "$@"\n'
        f'printf "%s\\n" "$@" >{tmp_path}/args\n'
        f'while (($#)); do [[ $1 == -r ]] && cp "$2" {tmp_path}/requirements.txt; shift; done\n'
        "echo 'No known vulnerabilities found'\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    done = subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "scripts" / "audit_python.sh")],
        env=os.environ | {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    args = (tmp_path / "args").read_text(encoding="utf-8").split()
    assert "--require-hashes" in args
    assert "--no-deps" not in args
    requirements = (tmp_path / "requirements.txt").read_text(encoding="utf-8")
    pins = [p for p in requirements.replace("\\\n", "").splitlines() if p[:1].isalnum()]
    assert len(pins) > 50
    assert [p for p in pins if "--hash=sha256:" not in p] == []


@pytest.mark.item("W38")
def test_the_release_gate_runs_the_stack_smoke_after_the_full_gate() -> None:
    steps = _job("release.yml", "gate")
    full = steps.index("- run: scripts/ci_local.sh --strict\n")
    assert full < steps.index("- run: scripts/ci_local.sh --strict --only stack\n")
    assert "needs: gate" in _job("release.yml", "images")


def _referenced_scripts(start: list[str]) -> set[str]:
    """The repository scripts the files in `start` name, and the scripts those name, and so on."""
    seen: set[str] = set()
    todo = list(start)
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        text = (ROOT / path).read_text(encoding="utf-8")
        todo += [m for m in re.findall(r"scripts/[\w-]+\.(?:sh|py)", text) if (ROOT / m).is_file()]
    return seen


@pytest.mark.item("W39")
def test_the_portability_workflow_watches_every_script_its_rows_reach() -> None:
    workflow = ".github/workflows/portability.yml"
    text = (ROOT / workflow).read_text(encoding="utf-8")
    m = re.search(r"^    paths:\n((?:      - .*\n)+)", text, re.MULTILINE)
    assert m is not None
    patterns = [line.strip().removeprefix("- ") for line in m.group(1).splitlines()]
    # Matched the way scripts/ci_portability.sh --if-needed does: ** and * both cross a /.
    reached = _referenced_scripts([workflow, "scripts/stack_smoke.sh"])
    reached -= {workflow, "scripts/ci_portability.sh"}  # the local runner of these same rows
    assert "scripts/backup.sh" in reached  # upgrade, restore and the drill wait on its lock
    unwatched = sorted(
        path
        for path in reached
        if not any(fnmatch.fnmatchcase(path, p.replace("**", "*")) for p in patterns)
    )
    assert unwatched == []


@pytest.mark.item("W40")
def test_an_unreachable_runtime_leaves_no_socket_for_a_later_test_to_trip_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # docker-py leaves its socket open when the connection fails; under the ResourceWarning
    # filter that failed whichever test the garbage collector next ran in.
    from tests import conftest

    monkeypatch.setattr(conftest, "TEST_DATABASE_URL", None)
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/missing.sock")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert conftest.postgres_available.__wrapped__() is False
        gc.collect()
    assert [w.message for w in caught if issubclass(w.category, ResourceWarning)] == []
