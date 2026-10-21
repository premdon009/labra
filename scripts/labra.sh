#!/usr/bin/env bash
# Run one `labra` command in the running web container, the way the systemd timers run the
# nightly audit check and the disk check (ADR-0013).
#
#   scripts/labra.sh audit verify
#   scripts/labra.sh check-disk [--percent 80]
#
# If the app isn't running the command fails and sends no ping, so the monitor's missed-ping
# alert still fires. LABRA_COMPOSE picks the Compose command (default "docker compose").
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
read -ra compose <<<"${LABRA_COMPOSE:-docker compose}"
case ${1:-} in "" | -h | --help) sed -n '2,9p' "$0"; exit 0 ;; esac
cd "$ROOT"
exec "${compose[@]}" exec -T web labra "$@"
