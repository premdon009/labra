"""The backup job's shell scripts, run against stand-in tools (ADR-0013).

The real tools run in `scripts/stack_smoke.sh`: a backup into a restic repository on disk and
one through rclone, against the stack's own Postgres. Here pg_dump, restic, psql and curl are
small scripts that log how they were called, so each failure path can be forced.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JOB = ROOT / "deploy" / "backup" / "labra-backup.sh"
TIMERS = ROOT / "scripts" / "install_timers.sh"

# Each stand-in appends "<tool> <args>" to calls.log; a FAIL_<TOOL> file makes it fail.
STUB = """#!/usr/bin/env bash
tool=$(basename "$0")
printf '%s %s\\n' "$tool" "$*" >>"$STUBS/calls.log"
[[ -f $STUBS/FAIL_${tool^^} ]] && { echo "$tool failed on purpose" >&2; exit 1; }
case $tool in
  pg_dump) printf 'PGPASSWORD=%s PGHOST=%s PGUSER=%s PGDATABASE=%s\\n' \\
             "$PGPASSWORD" "$PGHOST" "$PGUSER" "$PGDATABASE" >>"$STUBS/env.log"
           file=${1#--file=}; echo "-- dump" >"$file" ;;
  restic) if [[ " $* " == *" cat config "* && $2 != *:* && ! -f $2/config ]]; then exit 1; fi
          if [[ " $* " == *" backup "* ]]; then
            n=$(wc -l <"$STUBS/calls.log")
            echo '{"message_type":"status","percent_done":1}'
            printf '{"message_type":"summary","data_added":%d,"snapshot_id":"%08d%s"}\\n' \\
              $((n * 100)) "$n" deadbeefdeadbeef
          fi ;;
  psql) cat >>"$STUBS/sql.log"; printf '%s\\n' "$@" >>"$STUBS/sql.log" ;;
  curl) cat >"$STUBS/ping.body"; printf '%s\\n' "${@: -1}" >>"$STUBS/pings.log" ;;
esac
"""


@pytest.fixture
def job(tmp_path: Path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for tool in ("pg_dump", "restic", "psql", "curl"):
        (stubs / tool).write_text(STUB)
        (stubs / tool).chmod(0o755)
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "database_url").write_text(
        "postgresql+psycopg://labra:s3cret%2Fpa\\ss@db:5432/labra"
    )
    (secrets / "rclone_conf").write_text("[drive]\ntype = local\n")
    usb = tmp_path / "usb" / "labra"
    usb.mkdir(parents=True)
    (usb / "config").write_text("restic repository")
    (tmp_path / "files").mkdir()
    env = {
        "PATH": f"{stubs}:{os.environ['PATH']}",
        "STUBS": str(stubs),
        "LABRA_SECRETS": str(secrets),
        "LABRA_BACKUP_WORK": str(tmp_path / "work"),
        "LABRA_FILES_DIR": str(tmp_path / "files"),
        "LABRA_BACKUP_REPO_DRIVE": "rclone:drive:labra-backup",
        "LABRA_BACKUP_REPO_USB": str(usb),
        "LABRA_HEARTBEAT_URL_BACKUP": "https://hc.example.test/ping/abc",
    }

    def run(*args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            ["/bin/bash", str(JOB), *args],
            env={**env, **extra},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    run.stubs = stubs  # type: ignore[attr-defined]
    run.usb = usb  # type: ignore[attr-defined]
    return run


def _log(stubs: Path, name: str) -> str:
    path = stubs / name
    return path.read_text() if path.exists() else ""


@pytest.mark.item("M16")
def test_a_backup_snapshots_one_dump_into_both_repositories_and_logs_the_run(job) -> None:
    result = job("backup")
    assert result.returncode == 0, result.stderr
    calls = _log(job.stubs, "calls.log").splitlines()
    assert sum(c.startswith("pg_dump") for c in calls) == 1
    backups = [c for c in calls if c.startswith("restic") and " backup " in c]
    assert [b.split()[2] for b in backups] == ["rclone:drive:labra-backup", str(job.usb)]
    assert all("--host labra" in b and "--tag scheduled" in b for b in backups)
    assert not any(" forget " in c for c in calls)
    sql = _log(job.stubs, "sql.log")
    assert "insert into ops_run" in sql
    assert "kind=backup" in sql and "ok=true" in sql
    assert "snapshot=drive:" in sql and " usb:" in sql
    assert _log(job.stubs, "pings.log").strip() == "https://hc.example.test/ping/abc"


@pytest.mark.item("M16")
def test_the_database_password_reaches_pg_dump_only_through_its_environment(job) -> None:
    assert job("backup").returncode == 0
    env = _log(job.stubs, "env.log")
    assert "PGPASSWORD=s3cret/pa\\ss PGHOST=db PGUSER=labra PGDATABASE=labra" in env
    assert "s3cret" not in _log(job.stubs, "calls.log")


@pytest.mark.item("EC-D01")
def test_a_missing_usb_disk_fails_the_run_but_the_drive_copy_still_happens(job) -> None:
    (job.usb / "config").unlink()  # the mount point is empty when the disk isn't there
    result = job("backup")
    assert result.returncode == 1
    calls = _log(job.stubs, "calls.log")
    assert "backup --json --host labra --tag scheduled" in calls
    assert not any(str(job.usb) in c and " backup " in c for c in calls.splitlines())
    sql = _log(job.stubs, "sql.log")
    assert "ok=false" in sql and "snapshot=drive:" in sql
    assert "usb: no repository" in sql
    assert _log(job.stubs, "pings.log").strip() == "https://hc.example.test/ping/abc/fail"
    assert "usb: no repository" in _log(job.stubs, "ping.body")


@pytest.mark.item("M16")
def test_a_failed_dump_sends_nothing_to_restic_and_alerts(job) -> None:
    (job.stubs / "FAIL_PG_DUMP").touch()
    assert job("backup").returncode == 1
    assert "restic" not in _log(job.stubs, "calls.log")
    assert "pg_dump failed" in _log(job.stubs, "sql.log")
    assert _log(job.stubs, "pings.log").strip().endswith("/fail")


@pytest.mark.item("M16")
def test_the_nightly_run_applies_the_retention_to_each_repository(job) -> None:
    assert job("backup", "--prune", "--tag", "nightly").returncode == 0
    forgets = [c for c in _log(job.stubs, "calls.log").splitlines() if " forget " in c]
    assert len(forgets) == 2
    for f in forgets:
        assert (
            "--host labra --keep-within 2d --keep-within-hourly 7d --keep-within-daily 30d "
            "--keep-within-monthly 24m --prune" in f
        )


@pytest.mark.item("W16")
@pytest.mark.parametrize("url", ["http://hc.example.test/ping/abc", ""])
def test_a_heartbeat_goes_only_to_an_https_url(job, url: str) -> None:
    assert job("backup", LABRA_HEARTBEAT_URL_BACKUP=url).returncode == 0
    assert _log(job.stubs, "pings.log") == ""


@pytest.mark.item("W16")
def test_an_unreachable_monitor_never_fails_the_backup(job) -> None:
    (job.stubs / "FAIL_CURL").touch()
    result = job("backup")
    assert result.returncode == 0
    assert "heartbeat for backup not delivered" in result.stderr


@pytest.mark.item("M16")
def test_no_repository_configured_is_a_failure_not_a_quiet_pass(job) -> None:
    result = job("backup", LABRA_BACKUP_REPO_DRIVE="", LABRA_BACKUP_REPO_USB="")
    assert result.returncode == 1
    assert "no repository configured" in _log(job.stubs, "sql.log")


@pytest.mark.item("M16")
def test_init_never_creates_a_repository_in_an_empty_mount_point(job, tmp_path: Path) -> None:
    unmounted = tmp_path / "mnt"
    unmounted.mkdir(mode=0o555)
    result = job("init", LABRA_BACKUP_REPO_DRIVE="", LABRA_BACKUP_REPO_USB=f"{unmounted}/labra")
    unmounted.chmod(0o755)
    assert result.returncode == 1
    assert "is the disk mounted" in result.stderr
    assert " init" not in _log(job.stubs, "calls.log")


# Timers


def _timers(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(TIMERS), "--dry-run", *args],
        env={**os.environ, "LABRA_BACKUP_INTERVAL": "", "LABRA_BACKUP_LAB_HOURS": ""},
        capture_output=True,
        text=True,
        check=False,
    )


def _calendars(out: str, unit: str) -> list[str]:
    section = out.split(f"# {unit}\n", 1)[1].split("\n# ", 1)[0]
    return [
        line.removeprefix("OnCalendar=")
        for line in section.splitlines()
        if line.startswith("OnCalendar=")
    ]


@pytest.mark.item("EC-D01")
def test_every_15_minutes_in_lab_hours_plus_a_nightly_run_with_retention() -> None:
    result = _timers("--interval", "15m", "--lab-hours", "07:00-21:00")
    assert result.returncode == 0, result.stderr
    hours = ",".join(str(h) for h in range(7, 21))
    assert _calendars(result.stdout, "labra-backup.timer") == [
        f"*-*-* {hours},21:00:00 Asia/Kolkata",
        f"*-*-* {hours}:15:00 Asia/Kolkata",
        f"*-*-* {hours}:30:00 Asia/Kolkata",
        f"*-*-* {hours}:45:00 Asia/Kolkata",
    ]
    assert _calendars(result.stdout, "labra-backup-nightly.timer") == [
        "*-*-* 23:30:00 Asia/Kolkata"
    ]
    assert "backup.sh backup --prune --tag nightly" in result.stdout
    if analyze := shutil.which("systemd-analyze"):
        for spec in _calendars(result.stdout, "labra-backup.timer"):
            check = subprocess.run([analyze, "calendar", spec], capture_output=True, check=False)  # noqa: S603
            assert check.returncode == 0, spec


@pytest.mark.item("EC-D01")
def test_daily_means_the_nightly_run_only() -> None:
    result = _timers("--interval", "24h")
    assert result.returncode == 0
    assert "# labra-backup.timer" not in result.stdout
    assert "# labra-backup-nightly.timer" in result.stdout


@pytest.mark.item("EC-D01")
@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--interval", "10m"), "interval must be one of"),
        (("--lab-hours", "21:00-07:00"), "must start before they end"),
        (("--lab-hours", "7am-9pm"), "not a time of day"),
    ],
)
def test_a_schedule_that_makes_no_sense_is_refused(args: tuple[str, ...], message: str) -> None:
    result = _timers(*args)
    assert result.returncode == 2
    assert message in result.stderr
