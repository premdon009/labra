#!/usr/bin/env bash
# The watchdog (ADR-0013): every 5 minutes, fetch LABRA_WATCHDOG_URL (the public address's
# /healthz through the tunnel; default the app's own /healthz) and ping
# LABRA_HEARTBEAT_URL_WATCHDOG only when it answers. A dead server, internet line or tunnel
# sends no ping, and the monitor raises the alert.
#
#   scripts/watchdog.sh
#
# It takes no lock, so a long backup or drill never delays its ping. LABRA_COMPOSE picks the
# Compose command (default "docker compose").
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
read -ra compose <<<"${LABRA_COMPOSE:-docker compose}"
case ${1:-} in -h | --help) sed -n '2,10p' "$0"; exit 0 ;; esac
cd "$ROOT"
exec "${compose[@]}" --profile jobs run --rm --no-deps -T backup watchdog
