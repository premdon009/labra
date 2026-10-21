"""The host's job scripts take the backup lock, and nothing Compose starts inherits it.

Under podman-compose a detached container's monitor is a child of the Compose command; with
the lock's descriptor it would hold the lock after the script ends, and the next job would wait.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Succeeds at everything and notes each call that was handed the lock's descriptor.
STUB = """#!/usr/bin/env bash
echo "$*" >>"$STUBS/calls.log"
if [[ -e /proc/$$/fd/9 ]]; then echo "$*" >>"$STUBS/leaks.log"; fi
"""


@pytest.mark.item("W30")
@pytest.mark.parametrize(
    "command", [["backup.sh", "snapshots"], ["restore.sh", "--replace"], ["drill.sh"]]
)
def test_no_compose_command_inherits_the_job_lock(tmp_path: Path, command: list[str]) -> None:
    stub = tmp_path / "compose"
    stub.write_text(STUB)
    stub.chmod(0o755)
    env = {
        "PATH": os.environ["PATH"],
        "STUBS": str(tmp_path),
        "LABRA_COMPOSE": str(stub),
        "LABRA_JOB_WAIT": "30",
    }
    subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "scripts" / command[0]), *command[1:]],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert (tmp_path / "calls.log").read_text()
    leaks = tmp_path / "leaks.log"
    assert not leaks.exists(), leaks.read_text()
