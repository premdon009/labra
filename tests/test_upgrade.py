"""scripts/upgrade.sh, run against stand-in Compose and container engine commands.

The real upgrade, and the rollback from an image whose migration fails, run in
`scripts/stack_smoke.sh`. Here each step can be forced to fail, to check what the script
does next.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UPGRADE = ROOT / "scripts" / "upgrade.sh"
OLD = "ghcr.io/premdon009/labra:0.1.0"
NEW = "ghcr.io/premdon009/labra:0.2.0"

# Both stand-ins append "<tool> LABRA_IMAGE=<image> <args>" to calls.log. A FAIL_<STEP> file
# makes a step fail: PULL, DISK, BACKUP, UP_<image tag>, READY_<image tag>, RESTORE.
STUB = """#!/usr/bin/env bash
tool=$(basename "$0")
printf '%s LABRA_IMAGE=%s %s\\n' "$tool" "${LABRA_IMAGE-}" "$*" >>"$STUBS/calls.log"
fails() { [[ -f $STUBS/FAIL_$1 ]]; }
tag=${LABRA_IMAGE##*:}
case "$tool $*" in
  "engine inspect --format {{.Config.Image}} "*) cat "$STUBS/running" ;;
  "engine inspect --format {{.Image}} "*) echo sha256:0ld ;;
  "engine image inspect "*) grep -qxF "$3" "$STUBS/local" ;;
  "engine pull "*) ! fails PULL ;;
  "compose ps -q web") cat "$STUBS/web" ;;
  "compose exec -T web labra check-disk") ! fails DISK ;;
  "compose exec -T web python -m labra.probe /readyz") ! fails "READY_$tag" ;;
  "compose exec -T db psql "*) cat "$STUBS/snapshots" ;;
  *" backup backup --tag pre-upgrade") ! fails BACKUP ;;
  *" restore restore --replace "*) ! fails RESTORE ;;
  "compose up -d --no-build") ! fails "UP_$tag" ;;
esac
"""


class Upgrade:
    def __init__(self, tmp_path: Path) -> None:
        self.stubs = tmp_path / "stubs"
        self.stubs.mkdir()
        for tool in ("compose", "engine"):
            (self.stubs / tool).write_text(STUB)
            (self.stubs / tool).chmod(0o755)
        (self.stubs / "running").write_text(OLD + "\n")
        (self.stubs / "web").write_text("c0ffee\n")
        (self.stubs / "local").write_text("")
        (self.stubs / "snapshots").write_text("drive:aaaa1111 usb:bbbb2222\n")
        self.env_file = tmp_path / "env"

    def fail(self, step: str) -> None:
        (self.stubs / f"FAIL_{step}").touch()

    def __call__(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": os.environ["PATH"],
            "STUBS": str(self.stubs),
            "LABRA_COMPOSE": str(self.stubs / "compose"),
            "LABRA_ENGINE": str(self.stubs / "engine"),
            "LABRA_ENV_FILE": str(self.env_file),
            "LABRA_UPGRADE_WAIT": "0",
            "LABRA_JOB_WAIT": "5",
        }
        return subprocess.run(  # noqa: S603
            ["/bin/bash", str(UPGRADE), *args],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    @property
    def calls(self) -> list[str]:
        log = self.stubs / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def called(self, part: str) -> list[str]:
        return [c for c in self.calls if part in c]

    @property
    def logged(self) -> str:
        """The run log row: "<ok> <detail>"."""
        rows = self.called(" log-run upgrade ")
        assert len(rows) == 1, rows
        return rows[0].split(" log-run upgrade ", 1)[1].split(" ", 1)[1]


@pytest.fixture
def upgrade(tmp_path: Path) -> Upgrade:
    return Upgrade(tmp_path)


@pytest.mark.item("EC-G03")
def test_an_upgrade_backs_up_with_the_app_stopped_then_starts_the_new_image(
    upgrade: Upgrade,
) -> None:
    upgrade.env_file.write_text("LABRA_SITE=labra.lan\nLABRA_IMAGE=old\nLABRA_HEARTBEAT=http\n")
    upgrade.env_file.chmod(0o600)
    result = upgrade("0.2.0")
    assert result.returncode == 0, result.stderr
    assert "Upgraded to ghcr.io/premdon009/labra:0.2.0." in result.stdout

    steps = [c.split(" ", 2)[2] for c in upgrade.calls]
    order = [
        f"pull {NEW}",
        "exec -T web labra check-disk",
        "stop web",
        "--profile jobs run --rm -T backup backup --tag pre-upgrade",
        "up -d --no-build",
    ]
    assert [next(i for i, s in enumerate(steps) if s == o) for o in order] == sorted(
        next(i for i, s in enumerate(steps) if s == o) for o in order
    )
    assert upgrade.called(" up -d --no-build")[0].startswith(f"compose LABRA_IMAGE={NEW} ")
    assert upgrade.logged == f"true upgraded from {OLD} to {NEW}"
    assert not upgrade.called(" restore ")
    # The new image is kept for the next `docker compose up -d`; the other settings stay.
    assert upgrade.env_file.read_text() == (
        f"LABRA_SITE=labra.lan\nLABRA_HEARTBEAT=http\nLABRA_IMAGE={NEW}\n"
    )
    assert stat.S_IMODE(upgrade.env_file.stat().st_mode) == 0o600


@pytest.mark.item("EC-G03")
def test_an_image_reference_is_used_as_given_and_not_pulled_when_already_here(
    upgrade: Upgrade,
) -> None:
    image = "registry.example.test/labra@sha256:" + "ab" * 32
    (upgrade.stubs / "local").write_text(image + "\n")
    result = upgrade(image)
    assert result.returncode == 0, result.stderr
    assert not upgrade.called(" pull ")
    # A new .env file holds secrets' neighbours, so it is private from the start.
    assert upgrade.env_file.read_text() == f"LABRA_IMAGE={image}\n"
    assert stat.S_IMODE(upgrade.env_file.stat().st_mode) == 0o600


@pytest.mark.item("EC-G03")
@pytest.mark.parametrize("failing", ["UP_0.2.0", "READY_0.2.0"])
def test_a_failed_migration_or_an_app_that_never_gets_ready_is_rolled_back(
    upgrade: Upgrade, failing: str
) -> None:
    upgrade.env_file.write_text("LABRA_SITE=labra.lan\n")
    upgrade.fail(failing)
    result = upgrade("0.2.0")
    assert result.returncode == 4, result.stderr
    assert "rolling back" in result.stderr
    # The pre-upgrade backup goes back over the database, from the USB copy, on the old image.
    restore = upgrade.called(" restore restore ")
    assert restore == [
        f"compose LABRA_IMAGE={OLD} --profile jobs run --rm -T restore restore --replace "
        "--from usb bbbb2222"
    ]
    assert upgrade.called(" up -d --no-build")[-1].startswith(f"compose LABRA_IMAGE={OLD} ")
    assert upgrade.called("labra audit verify")
    assert upgrade.logged == f"false not upgraded to {NEW}; rolled back to {OLD}"
    assert upgrade.env_file.read_text() == f"LABRA_SITE=labra.lan\nLABRA_IMAGE={OLD}\n"


@pytest.mark.item("EC-G03")
def test_without_a_usb_copy_the_rollback_restores_from_drive(upgrade: Upgrade) -> None:
    (upgrade.stubs / "snapshots").write_text("drive:aaaa1111\n")
    upgrade.fail("UP_0.2.0")
    assert upgrade("0.2.0").returncode == 4
    assert upgrade.called(" restore restore ")[0].endswith("--from drive aaaa1111")


@pytest.mark.item("EC-G03")
def test_a_failed_rollback_says_so_and_names_the_runbook(upgrade: Upgrade) -> None:
    upgrade.fail("UP_0.2.0")
    upgrade.fail("RESTORE")
    result = upgrade("0.2.0")
    assert result.returncode == 5
    assert "THE ROLLBACK FAILED" in result.stderr
    assert "docs/runbooks/restore-from-backup.md" in result.stderr
    assert "usb:bbbb2222" in result.stderr
    assert upgrade.logged == f"false not upgraded to {NEW}, and the rollback to {OLD} failed"
    assert (ROOT / "docs" / "runbooks" / "restore-from-backup.md").exists()


@pytest.mark.item("EC-G03")
@pytest.mark.parametrize("failing", ["PULL", "DISK"])
def test_nothing_is_stopped_when_the_image_or_the_disk_isnt_ready(
    upgrade: Upgrade, failing: str
) -> None:
    upgrade.fail(failing)
    result = upgrade("0.2.0")
    assert result.returncode == 1
    assert "nothing changed" in result.stderr
    assert not upgrade.called(" stop ")
    assert not upgrade.called(" log-run ")
    assert not upgrade.env_file.exists()


@pytest.mark.item("EC-G03")
def test_a_failed_backup_restarts_the_old_app_and_upgrades_nothing(upgrade: Upgrade) -> None:
    upgrade.fail("BACKUP")
    result = upgrade("0.2.0")
    assert result.returncode == 1
    assert upgrade.called(" up -d --no-build") == ["compose LABRA_IMAGE= up -d --no-build"]
    assert upgrade.logged == f"false not upgraded to {NEW}: the pre-upgrade backup failed"
    assert not upgrade.env_file.exists()


@pytest.mark.item("EC-G03")
def test_the_same_image_again_changes_nothing(upgrade: Upgrade) -> None:
    result = upgrade("0.1.0")
    assert result.returncode == 0
    assert "Already on" in result.stdout
    assert not upgrade.called(" stop ")


@pytest.mark.item("EC-G03")
@pytest.mark.parametrize(
    "args", [(), ("latest",), ("0.2",), ("-x:1",), ("0.2.0", "0.3.0"), ("0.2.0; rm",)]
)
def test_anything_but_one_version_or_image_is_refused(
    upgrade: Upgrade, args: tuple[str, ...]
) -> None:
    assert upgrade(*args).returncode == 2
    assert upgrade.calls == []


@pytest.mark.item("EC-G03")
def test_nothing_happens_when_the_stack_isnt_running(upgrade: Upgrade) -> None:
    (upgrade.stubs / "web").write_text("")
    result = upgrade("0.2.0")
    assert result.returncode == 1
    assert "isn't running" in result.stderr
    assert upgrade.calls == ["compose LABRA_IMAGE= ps -q web"]


@pytest.mark.item("W30")
def test_the_running_image_is_read_from_one_web_container(upgrade: Upgrade) -> None:
    # nerdctl compose can list two containers for the service.
    (upgrade.stubs / "web").write_text("c0ffee\nbada55\n")
    result = upgrade("0.2.0")
    assert result.returncode == 0, result.stderr
    inspected = upgrade.called("engine LABRA_IMAGE= inspect --format ")
    assert inspected
    assert all(c.endswith(" bada55") for c in inspected), inspected
