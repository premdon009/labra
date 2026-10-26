"""scripts/ci_portability.sh and scripts/portability_job.sh: the portability rows, run locally.

The runner is tried in a throwaway git repository with a stub `docker` that records its calls
and plays a lab: `exec` of a row exits with the status in the file `exit-<row>` (0 without one).
The job script is tried with stub engines and stub stack scripts, so no container starts.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "portability.yml"
JOB = ROOT / "scripts" / "portability_job.sh"

pytestmark = pytest.mark.item("W31")

DOCKER = r"""#!/usr/bin/env bash
echo "$*" >>"$STUBS/calls.log"
case $1 in
  info) [[ ! -f $STUBS/NO_DOCKER ]]; exit ;;
  run) [[ -f $STUBS/NO_LAB ]] && exit 1; echo lab-id ;;
  save) while [[ $1 != -o ]]; do shift; done; touch "$2" ;;
  ps) echo leftover-lab ;;
  exec)
    shift
    while [[ $1 != labra-ci-* ]]; do shift; done
    shift
    case "$*" in
      "id -u runner") echo 1001 ;;
      "tar -xzf -" | "tar -xf -" | "tar -C results -xf -") cat >/dev/null ;;
      "./scripts/portability_job.sh --install "*)
        exit "$(cat "$STUBS/install-exit-${!#}" 2>/dev/null || echo 0)"
        ;;
      "timeout 45m ./scripts/portability_job.sh "*)
        row=${!#}
        echo "ran $row" >>"$STUBS/calls.log"
        rc=$(cat "$STUBS/exit-$row" 2>/dev/null || echo 0)
        ((rc == 2)) && echo "UNCHECKED: rootless containerd won't start here."
        exit "$rc"
        ;;
      "tar -C results"* | "sh -c"*) tar -cf - -T /dev/null ;;
    esac
    ;;
esac
exit 0
"""

COPIED = [
    "scripts/ci_portability.sh",
    "scripts/portability_job.sh",
    "scripts/build_image.sh",
    ".github/workflows/portability.yml",
    "deploy/ci-lab/Containerfile",
    "deploy/nginx/compose.nginx.yaml",
    "compose.yaml",
    "Dockerfile",
]


GIT = shutil.which("git") or "git"


def git(repo: Path, *args: str) -> None:
    config = ["user.name=Test", "user.email=test@example.invalid", "commit.gpgsign=false"]
    subprocess.run(  # noqa: S603
        [GIT, "-C", str(repo), *(arg for c in config for arg in ("-c", c)), *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with the runner's files on master, checked out on a feature branch."""
    repo = tmp_path / "repo"
    for name in COPIED:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, repo / name)
    (repo / "README.md").write_text("A lab.\n")
    git(repo, "init", "-q", "-b", "master")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "start")
    git(repo, "checkout", "-q", "-b", "feat/x")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "docker").write_text(DOCKER)
    (stubs / "docker").chmod(0o755)
    return repo


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    stubs = repo.parent / "stubs"
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(repo / "scripts" / "ci_portability.sh"), *args],
        env={"PATH": f"{stubs}:{os.environ['PATH']}", "STUBS": str(stubs), "HOME": str(repo)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def calls(repo: Path) -> str:
    log = repo.parent / "stubs" / "calls.log"
    return log.read_text() if log.exists() else ""


def table(result: subprocess.CompletedProcess[str]) -> dict[str, list[str]]:
    rows = re.findall(r"^\| ([a-z-]+) \| (.*) \|$", result.stdout, re.MULTILINE)
    return {row: [cell.strip() for cell in rest.split("|")] for row, rest in rows if row != "Row"}


def test_each_row_runs_in_a_lab_and_the_table_shows_its_result(repo: Path) -> None:
    stubs = repo.parent / "stubs"
    (stubs / "exit-podman").write_text("1\n")
    (stubs / "exit-nerdctl").write_text("2\n")
    (stubs / "install-exit-builders").write_text("100\n")
    result = run(repo, "docker-caddy", "podman", "nerdctl", "incus", "builders", "--jobs", "3")
    assert result.returncode == 1, result.stdout + result.stderr
    rows = table(result)
    assert list(rows) == ["docker-caddy", "podman", "nerdctl", "incus", "builders"]
    assert rows["builders"][0] == "FAIL"
    assert rows["builders"][2] == "exit 100 in --install; see install.log"
    assert rows["docker-caddy"][0] == "PASS"
    assert rows["podman"][0] == "FAIL"
    assert rows["podman"][2] == "exit 1; see job.log"
    assert rows["nerdctl"][0] == "SKIP"
    assert rows["nerdctl"][2] == "rootless containerd won't start here."
    assert rows["incus"][0] == "SKIP"
    log = calls(repo)
    # Only the rows asked for, incus not at all; every lab removed with its volumes.
    assert sorted(re.findall(r"^ran (\S+)$", log, re.MULTILINE)) == [
        "docker-caddy",
        "nerdctl",
        "podman",
    ]
    assert len(re.findall(r"^run -d .*--privileged --cgroupns=private", log, re.MULTILINE)) == 4
    assert not re.search(r"^run -d .*--network", log, re.MULTILINE)  # the default bridge's DNS
    for row in ("docker-caddy", "podman", "nerdctl", "builders"):
        assert re.search(rf"^rm -f -v labra-ci-\S+-{row}$", log, re.MULTILINE)
    assert "portability_job.sh --install podman" in log
    summary = next((repo / ".ci" / "portability").glob("*/summary.md"))
    assert "| podman | FAIL |" in summary.read_text()


def test_every_row_passing_exits_0(repo: Path) -> None:
    result = run(repo, "docker-nginx")
    assert result.returncode == 0, result.stdout + result.stderr
    assert table(result)["docker-nginx"][0] == "PASS"


def test_without_a_row_every_row_runs(repo: Path) -> None:
    result = run(repo, "--jobs", "4")
    assert result.returncode == 0, result.stdout + result.stderr
    rows = subprocess.run(  # noqa: S603
        [str(JOB), "--rows"], capture_output=True, text=True, check=True
    ).stdout.split()
    assert list(table(result)) == rows


def test_an_unknown_row_is_refused_before_anything_starts(repo: Path) -> None:
    result = run(repo, "docker-caddy", "kubernetes")
    assert result.returncode == 1
    assert "unknown row: kubernetes" in result.stderr
    assert calls(repo) == ""


def test_without_docker_nothing_is_checked(repo: Path) -> None:
    (repo.parent / "stubs" / "NO_DOCKER").touch()
    result = run(repo, "docker-caddy")
    assert result.returncode == 2
    assert "UNCHECKED" in result.stderr


def test_the_app_images_are_built_once_unless_each_row_builds_them(repo: Path) -> None:
    run(repo, "podman", "docker-nginx")
    log = calls(repo)
    assert len(re.findall(r"^build ", log, re.MULTILINE)) == 2  # the app and backup images
    assert re.search(r"^save -o \S+/labra-image.tar localhost/labra:dev", log, re.MULTILINE)
    assert "-e LABRA_PREBUILT=1 " in log
    # Each pinned image is saved on its own under a tag a lab's engines keep, and the tag
    # stays: removing it would remove an image pulled by digest from this machine.
    assert not re.search(r"^rmi ", log, re.MULTILINE)
    assert re.search(
        r"^tag docker\.io/library/postgres:18@sha256:[0-9a-f]{64} "
        r"docker\.io/library/postgres:labra-pinned$",
        log,
        re.MULTILINE,
    )
    # The builders' base images too, so the builders row pulls nothing but Kaniko's.
    for name in ("docker.io/library/python", "ghcr.io/astral-sh/uv"):
        assert re.search(rf"^tag {name}:\S+@sha256:[0-9a-f]{{64}} {name}:labra-pinned$", log, re.M)
    (repo.parent / "stubs" / "calls.log").unlink()
    run(repo, "podman", "--build")
    log = calls(repo)
    assert not re.search(r"^build ", log, re.MULTILINE)
    assert "labra-image.tar" not in log
    assert "-e LABRA_PREBUILT=0 " in log


def test_labs_are_removed_when_one_fails_to_start_but_kept_on_request(repo: Path) -> None:
    (repo.parent / "stubs" / "NO_LAB").touch()
    result = run(repo, "docker-caddy")
    assert result.returncode == 1
    assert table(result)["docker-caddy"][:1] == ["FAIL"]
    log = calls(repo)
    assert re.search(r"^rm -f -v labra-ci-\S+-docker-caddy$", log, re.MULTILINE)
    assert "rm -f -v leftover-lab" in log  # the exit trap, by label
    assert not list((repo / ".ci" / "portability").glob("*/images"))
    (repo.parent / "stubs" / "calls.log").unlink()
    run(repo, "docker-caddy", "--keep")
    assert " rm " not in f" {calls(repo)}"
    assert "rm -f" not in calls(repo)


@pytest.mark.parametrize(
    ("change", "runs"),
    [
        ("README.md", False),
        ("scripts/upgrade.sh", True),  # watched, and not run by the workflow itself
        ("deploy/ci-lab/Containerfile", True),
    ],
)
@pytest.mark.parametrize("committed", [True, False])
def test_if_needed_runs_only_when_a_watched_path_changed(
    repo: Path, change: str, runs: bool, committed: bool
) -> None:
    path = repo / change
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write("# changed\n")
    if committed:
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "change")
    result = run(repo, "docker-caddy", "--if-needed")
    assert result.returncode == 0, result.stdout + result.stderr
    assert ("ran docker-caddy" in calls(repo)) is runs
    if not runs:
        assert "no row to run" in result.stdout
        assert calls(repo) == ""


def _watched() -> list[str]:
    on = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))[True]
    return on["pull_request"]["paths"]


@pytest.mark.parametrize(
    "script",
    ["scripts/stack_smoke.sh", "scripts/compare_runtimes.sh", "scripts/portability_job.sh"],
)
def test_the_workflow_watches_every_script_a_row_runs(script: str) -> None:
    # A change to any of them alone must start the workflow, and --if-needed reads the same list.
    text = (ROOT / script).read_text(encoding="utf-8")
    called = set(re.findall(r"\$ROOT/(scripts/[\w.]+)", text))
    assert called
    assert {script, *called} <= set(_watched())


def test_every_workflow_row_is_a_job_script_row() -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    workflow = [*jobs["runtime"]["strategy"]["matrix"]["row"], "outside-postgres"]
    rows = subprocess.run(  # noqa: S603
        [str(JOB), "--rows"], capture_output=True, text=True, check=True
    ).stdout.split()
    assert sorted(workflow) == sorted(rows)
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/portability_job.sh outside-postgres" in text


def test_the_nerdctl_version_and_checksum_are_set_once() -> None:
    files = [*(ROOT / ".github" / "workflows").glob("*.yml"), *(ROOT / "scripts").glob("*")]
    sets = [
        (path.name, m.group(1), m.group(2))
        for path in files
        if path.is_file()
        for m in re.finditer(
            r"^\s*(NERDCTL_VERSION|NERDCTL_SHA256)[=:]\s*(\S+)",
            path.read_text(encoding="utf-8", errors="replace"),
            re.MULTILINE,
        )
    ]
    assert sorted(name for _, name, _ in sets) == ["NERDCTL_SHA256", "NERDCTL_VERSION"]
    assert {path for path, _, _ in sets} == {"portability_job.sh"}
    assert re.fullmatch(r"[0-9a-f]{64}", {n: v for _, n, v in sets}["NERDCTL_SHA256"])


def test_the_lab_has_every_package_a_row_installs() -> None:
    # A row's --install then needs no network in a lab; incus needs a VM and isn't run there.
    lab = (ROOT / "deploy" / "ci-lab" / "Containerfile").read_text(encoding="utf-8")
    m = re.search(r"apt-get install -y (.*?)&& break", lab.replace("\\\n", " "), re.DOTALL)
    assert m is not None
    installed = set(m.group(1).split())
    packages = re.findall(r'^  \[([a-z-]+)\]="([^"]*)"$', JOB.read_text(encoding="utf-8"), re.M)
    assert len(packages) >= 6
    for row, names in packages:
        if row != "incus":
            assert set(names.split()) <= installed, row


def test_the_lab_runs_the_same_uv_as_the_image() -> None:
    uv = re.compile(r"ghcr\.io/astral-sh/uv:[\w.]+@sha256:[0-9a-f]{64}")
    dockerfile = uv.findall((ROOT / "Dockerfile").read_text(encoding="utf-8"))
    lab = uv.findall((ROOT / "deploy" / "ci-lab" / "Containerfile").read_text(encoding="utf-8"))
    assert dockerfile and set(lab) == set(dockerfile)


# Engines and stack scripts as far as portability_job.sh sees them: each logs its call.
STUB = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >>"$STUBS/calls.log"
[[ $(basename "$0") == docker && $1 == image && ! -f $STUBS/IMAGE_LOADED ]] && exit 1
exit 0
"""


@pytest.fixture
def job(tmp_path: Path) -> Path:
    """A checkout with portability_job.sh, stub stack scripts and two pinned images."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    shutil.copy2(JOB, repo / "scripts")
    shutil.copy2(WORKFLOW, repo / ".github" / "workflows")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("compare_runtimes.sh", "stack_smoke.sh", "build_image.sh"):
        (repo / "scripts" / name).write_text(STUB)
        (repo / "scripts" / name).chmod(0o755)
    for name in ("docker", "podman", "nerdctl", "systemctl", "sudo", "uv", "sg", "iptables",
                 "containerd-rootless-setuptool.sh"):  # fmt: skip
        (stubs / name).write_text(STUB)
        (stubs / name).chmod(0o755)
    deps = repo / "results" / "deps"
    deps.mkdir(parents=True)
    (deps / "refs").write_text(
        "1.tar docker.io/library/caddy:labra-pinned docker.io/library/caddy:2@sha256:"
        + "a" * 64
        + "\n2.tar docker.io/library/postgres:labra-pinned docker.io/library/postgres:18@sha256:"
        + "b" * 64
        + "\n"
    )
    return repo


def job_sh(repo: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    stubs = repo.parent / "stubs"
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(repo / "scripts" / "portability_job.sh"), *args],
        cwd=repo,
        env={"PATH": f"{stubs}:{os.environ['PATH']}", "STUBS": str(stubs), "USER": "runner", **env},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def job_calls(repo: Path) -> list[str]:
    return (repo.parent / "stubs" / "calls.log").read_text().splitlines()


def test_a_row_loads_the_pinned_images_the_way_each_engine_keeps_their_digest(job: Path) -> None:
    assert job_sh(job, "nerdctl").returncode == 0
    log = job_calls(job)
    assert log[0] == "containerd-rootless-setuptool.sh install"
    assert "nerdctl load -i results/deps/1.tar" in log
    caddy = "docker.io/library/caddy"
    assert f"nerdctl tag {caddy}:labra-pinned {caddy}:2@sha256:{'a' * 64}" in log
    assert log[-1] == "compare_runtimes.sh --runtimes nerdctl --builders  --out results"
    (job.parent / "stubs" / "calls.log").unlink()
    assert job_sh(job, "podman-compose").returncode == 0
    log = job_calls(job)
    assert "podman pull -q oci-archive:results/deps/2.tar" in log
    assert log[-1] == "stack_smoke.sh --compose podman-compose"
    (job.parent / "stubs" / "calls.log").unlink()
    assert job_sh(job, "builders").returncode == 0
    log = job_calls(job)
    assert "docker load -i results/deps/1.tar" in log
    assert "podman pull -q oci-archive:results/deps/1.tar" in log  # Buildah's store


def test_a_prebuilt_image_replaces_the_rows_own_build(job: Path) -> None:
    (job / "results" / "labra-image.tar").write_text("images")
    assert job_sh(job, "docker-nginx").returncode == 0
    assert "build_image.sh --builder docker" in job_calls(job)
    (job.parent / "stubs" / "calls.log").unlink()
    (job.parent / "stubs" / "IMAGE_LOADED").touch()
    result = job_sh(job, "docker-nginx", LABRA_PREBUILT="1")
    assert result.returncode == 0
    log = job_calls(job)
    assert "docker load -i results/labra-image.tar" in log
    assert not [line for line in log if line.startswith("build_image.sh")]
    assert log[-1] == "stack_smoke.sh --compose docker compose --proxy nginx"


def test_rootless_containerd_that_wont_start_is_unchecked(job: Path) -> None:
    (job.parent / "stubs" / "containerd-rootless-setuptool.sh").write_text("#!/bin/sh\nexit 1\n")
    result = job_sh(job, "nerdctl")
    assert result.returncode == 2
    assert "UNCHECKED: rootless containerd won't start here." in result.stdout


def test_the_job_script_refuses_an_unknown_row(job: Path) -> None:
    result = job_sh(job, "kubernetes")
    assert result.returncode == 1
    assert "ROW one of: docker-caddy" in result.stderr


def test_outside_postgres_uses_the_given_server_or_a_throwaway_one(job: Path) -> None:
    url = "postgresql://postgres@db.example.invalid:5432/labra_test"
    assert job_sh(job, "outside-postgres", LABRA_TEST_DATABASE_URL=url).returncode == 0
    # The time-budget tests run after the parallel ones, as the gate runs them.
    assert job_calls(job) == [
        "uv run pytest -q -rs -m db and not e2e and not serial -n auto",
        "uv run pytest -q -rs -m db and not e2e and serial",
    ]
    (job.parent / "stubs" / "calls.log").unlink()
    assert job_sh(job, "outside-postgres").returncode == 0
    log = job_calls(job)
    started = next(line for line in log if line.startswith("docker run"))
    pinned = re.search(r"docker\.io/library/postgres:18@sha256:[0-9a-f]{64}", WORKFLOW.read_text())
    assert pinned is not None and started.endswith(pinned.group(0))
    assert log[-2] == "uv run pytest -q -rs -m db and not e2e and serial"
    assert log[-1].startswith("docker rm -f labra-outside-pg-")
