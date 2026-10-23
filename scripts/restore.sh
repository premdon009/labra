#!/usr/bin/env bash
# Put the lab's data back from a backup (ADR-0013, docs/runbooks/restore-from-backup.md).
#
#   scripts/restore.sh [--from usb|drive] [--replace] [SNAPSHOT]
#
# Restores the newest snapshot unless one is named (scripts/backup.sh snapshots lists them),
# from the USB disk when there is one. The web app is stopped first so nothing is written
# meanwhile. The database must have no tables, as on a new server before its first start,
# unless --replace is given. The database loads in one transaction, so a failure there leaves
# it as it was. Then the stored files are put back, the stack starts again (migrate brings an
# older backup up to this version) and the audit log is checked. If the files fail after the
# database loaded, Labra stays stopped and the script exits 4: fix the cause, then run it again
# with --replace and the same snapshot.
# LABRA_COMPOSE picks the Compose command (default "docker compose").
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
read -ra compose <<<"${LABRA_COMPOSE:-docker compose}"
case ${1:-} in -h | --help) sed -n '2,14p' "$0"; exit 0 ;; esac

exec 9<"$ROOT/scripts/backup.sh"
if ! flock -w "${LABRA_JOB_WAIT:-7200}" 9; then
  echo "a backup job is still running; giving up" >&2
  exit 1
fi
cd "$ROOT"
# 9<&-: what Compose starts must not hold the job lock, as podman-compose's container
# monitors outlive this script.
dc() { "${compose[@]}" "$@" 9<&-; }
# shellcheck source=scripts/compose_run.sh
source "$ROOT/scripts/compose_run.sh"

echo "Stopping the web app"
stop_web
status=0
compose_run restore restore "$@" || status=$?
if ((status == 4)); then
  echo "Restore incomplete: the database is restored, but the stored files are not." \
    "Labra stays stopped. Fix the cause above, then run scripts/restore.sh --replace" \
    "again with the same snapshot." >&2
  exit 4
fi
echo "Starting the stack again"
dc up -d --no-build >/dev/null
if ((status == 0)); then
  compose_run --no-deps web labra audit verify || status=1
fi
case $status in
  0) echo "Restore finished." ;;
  3) echo "Nothing restored: the database already has tables." \
    "Add --replace to overwrite them." >&2 ;;
  *) echo "Restore failed; the database is as it was before. See the messages above." >&2 ;;
esac
exit "$status"
