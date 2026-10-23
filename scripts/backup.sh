#!/usr/bin/env bash
# Run one backup-image job on the server, the way the systemd timers do (ADR-0013).
#
#   scripts/backup.sh backup [--prune] [--tag TAG]   one backup now
#   scripts/backup.sh init                           create the repositories (once)
#   scripts/backup.sh snapshots                      list what's there
#
# Settings come from the .env file beside compose.yaml. LABRA_COMPOSE picks the Compose
# command (default "docker compose"). Only one job runs at a time; a second one waits.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
read -ra compose <<<"${LABRA_COMPOSE:-docker compose}"

exec 9<"$0"
if ! flock -w "${LABRA_JOB_WAIT:-7200}" 9; then
  echo "another backup job is still running; giving up" >&2
  exit 1
fi
cd "$ROOT"
# shellcheck source=scripts/compose_run.sh
source "$ROOT/scripts/compose_run.sh"
# Not exec, so this script holds the lock until the job ends.
compose_run backup "$@"
