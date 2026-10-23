"""scripts/stack_smoke.sh, run against a stand-in Compose and container engine.

The whole smoke test runs on real runtimes in `scripts/ci_local.sh --only stack` and the
portability workflow. Here the stack is made to fail, to check what the script reports.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SMOKE = ROOT / "scripts" / "stack_smoke.sh"

# Both stand-ins append "<tool> <args>" to calls.log, one line a call; `up` fails the way
# Compose does when a container's health check never passes.
STUB = """#!/usr/bin/env bash
tool=$(basename "$0")
printf '%s %s\\n' "$tool" "${*//$'\\n'/\\\\n}" >>"$STUBS/calls.log"
case "$tool $*" in
  "fake-compose "*" up -d --no-build")
    echo "dependency failed to start: container web-1 is unhealthy"; exit 1 ;;
  "fake-compose "*" logs "*) echo "web-1  | Application startup complete." ;;
  "fake ps -aq --filter label=com.docker.compose.project="*) printf 'c0ffee\\nbada55\\n' ;;
  "fake inspect "*)
    echo "/web-1: running, exit 0, unhealthy"
    echo "  check exit 1: readyz answered 503" ;;
esac
"""


@pytest.mark.item("W30")
def test_a_stack_that_does_not_start_shows_each_containers_health_checks(tmp_path: Path) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for tool in ("fake-compose", "fake"):
        (stubs / tool).write_text(STUB)
        (stubs / tool).chmod(0o755)
    env = {"PATH": os.environ["PATH"], "STUBS": str(stubs), "TMPDIR": str(tmp_path)}
    r = subprocess.run(  # noqa: S603
        ["/bin/bash", str(SMOKE), "--compose", str(stubs / "fake-compose")],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 1, r.stdout + r.stderr
    out = r.stdout
    assert "container web-1 is unhealthy" in out
    assert "Application startup complete." in out
    assert out.count("check exit 1: readyz answered 503") == 2
    assert out.rstrip().endswith("FAIL  stack did not start")
    calls = (stubs / "calls.log").read_text().splitlines()
    listed = [c for c in calls if c.startswith("fake ps -aq ")]
    assert len(listed) == 1
    assert "label=com.docker.compose.project=labra-smoke-" in listed[0]
    inspected = [c for c in calls if c.startswith("fake inspect ")]
    assert [c.split()[-1] for c in inspected] == ["c0ffee", "bada55"]
    assert all(".State.Health.Log" in c for c in inspected)
