"""scripts/drill.sh against a Compose stand-in: what it reports for each repository."""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Each call prints its result on stdout, then a warning on stderr, as Podman 5 can.
# A FAIL_RESTORE file makes the restore fail.
STUB = """#!/usr/bin/env bash
echo "$*" >>"$STUBS/calls"
case "$*" in
  *" backup repos") echo usb ;;
  *" restore restore "*)
    if [[ -f $STUBS/FAIL_RESTORE ]]; then echo "Fatal: repository damaged" >&2; exit 1; fi
    echo "usb: every table matches the dump" ;;
  *" migrate labra audit verify "*) echo "Audit log intact: 3 rows checked." ;;
esac
echo "WARN[0001] container cleanup took a while" >&2
"""


def drill(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    stub = tmp_path / "compose"
    stub.write_text(STUB)
    stub.chmod(0o755)
    env = {
        "PATH": os.environ["PATH"],
        "STUBS": str(tmp_path),
        "LABRA_COMPOSE": str(stub),
        "LABRA_JOB_WAIT": "30",
    }
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "scripts" / "drill.sh")],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.item("W30")
def test_the_drill_reports_the_results_not_the_warnings_after_them(tmp_path: Path) -> None:
    result = drill(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "usb: usb: every table matches the dump",
        "usb: Audit log intact: 3 rows checked.",
    ]


@pytest.mark.item("W30")
def test_a_failed_restore_is_reported_with_its_error(tmp_path: Path) -> None:
    (tmp_path / "FAIL_RESTORE").touch()
    result = drill(tmp_path)
    assert result.returncode == 1
    assert result.stdout.splitlines() == ["usb: restore failed: Fatal: repository damaged "]


@pytest.mark.item("W41")
def test_the_scratch_copy_is_loaded_read_and_dropped_with_the_owners_login(
    tmp_path: Path,
) -> None:
    # The app's login has no rights on a database the restore just made, and may not create one.
    assert drill(tmp_path).returncode == 0
    calls = (tmp_path / "calls").read_text().splitlines()
    owner = [c for c in calls if " restore " in c or "audit verify" in c or "drop-database" in c]
    assert len(owner) == 3, calls
    assert all(re.search(r" (restore|migrate) (restore|labra|drop-database) ", c) for c in owner)
    assert not any(" web " in c for c in calls)
