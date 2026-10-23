"""scripts/compose_run.sh: a one-off job container on every Compose, with its own exit status.

nerdctl compose has no -T, and without a terminal its `run` exits 0 whatever the container did,
so there the job runs detached and its status is read back with `nerdctl wait`.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# nerdctl 2.4 as far as the job runner sees it. The job prints on both streams and exits with
# the status in the file `status`; with a WAIT_FAILS file, `wait` fails as it can when the
# container's shim has already gone, and the status is read with `inspect`.
NERDCTL = """#!/usr/bin/env bash
echo "$*" >>"$STUBS/calls.log"
if [[ -e /proc/$$/fd/9 ]]; then echo "$*" >>"$STUBS/leaks.log"; fi
case "$*" in
  "compose "*" -T "*) echo "unknown shorthand flag: 'T' in -T" >&2; exit 1 ;;
  "compose "*" run -d "*) ;;
  "logs "*) echo "the job's output"; echo "the job's warning" >&2 ;;
  "wait "*) if [[ -f $STUBS/WAIT_FAILS ]]; then echo "ttrpc: closed" >&2; exit 1; fi
    cat "$STUBS/status" ;;
  "inspect --format {{.State.ExitCode}} "*) cat "$STUBS/status" ;;
esac
"""


def backup_sh(
    tmp_path: Path, status: int, *, wait_fails: bool = False
) -> subprocess.CompletedProcess[str]:
    stub = tmp_path / "nerdctl"
    stub.write_text(NERDCTL)
    stub.chmod(0o755)
    (tmp_path / "status").write_text(f"{status}\n")
    if wait_fails:
        (tmp_path / "WAIT_FAILS").touch()
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "scripts" / "backup.sh"), "snapshots"],
        env={
            "PATH": os.environ["PATH"],
            "STUBS": str(tmp_path),
            "LABRA_COMPOSE": f"{stub} compose -p lab",
            "LABRA_JOB_WAIT": "30",
        },
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.item("W30")
@pytest.mark.parametrize("status", [0, 3])
@pytest.mark.parametrize("wait_fails", [False, True])
def test_on_nerdctl_a_job_exits_with_its_own_status(
    tmp_path: Path, status: int, wait_fails: bool
) -> None:
    result = backup_sh(tmp_path, status, wait_fails=wait_fails)
    assert result.returncode == status, result.stderr
    assert result.stdout == "the job's output\n"
    assert result.stderr == "the job's warning\n"


@pytest.mark.item("W30")
def test_on_nerdctl_the_job_runs_detached_and_is_removed_after(tmp_path: Path) -> None:
    backup_sh(tmp_path, 0)
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert len(calls) == 4
    run, wait, logs, rm = calls
    name = run.split("--name ")[1].split()[0]
    assert run == f"compose -p lab --profile jobs run -d --name {name} backup snapshots"
    # The output is read once the job has ended, so none of it is cut off.
    assert (wait, logs, rm) == (f"wait {name}", f"logs {name}", f"rm -f {name}")
    assert not (tmp_path / "leaks.log").exists()
