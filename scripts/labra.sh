#!/usr/bin/env bash
# Run one `labra` command in the running web container, the way the systemd timers run the
# nightly audit check and the disk check (ADR-0013).
#
#   scripts/labra.sh audit verify
#   scripts/labra.sh check-disk [--percent 80]
#
# Web has no way to the internet, so the result of these two is pinged from the backup image
# (`labra-backup ping`). If the app isn't running the check prints nothing and nothing is
# pinged, so the monitor's missed-ping alert still fires. The exit status is the command's.
# LABRA_COMPOSE picks the Compose command (default "docker compose").
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
read -ra compose <<<"${LABRA_COMPOSE:-docker compose}"
case ${1:-} in "" | -h | --help) sed -n '2,11p' "$0"; exit 0 ;; esac
cd "$ROOT"
case "$*" in
  "audit verify") job=audit_verify ;;
  check-disk | "check-disk "*) job=disk ;;
  *) exec "${compose[@]}" exec -T web labra "$@" ;;
esac

status=0
out=$("${compose[@]}" exec -T web labra "$@") || status=$?
[[ -z $out ]] || printf '%s\n' "$out"
# The check's own line, after any log lines: "Audit log intact: …", "DISK SPACE LOW: …".
line=$(grep -E '^(Audit log intact|AUDIT LOG DAMAGED|Disk space OK|DISK SPACE LOW): ' <<<"$out" |
  tail -n 1) || exit "$status"
ok=false
[[ $line == "Audit log intact: "* || $line == "Disk space OK: "* ]] && ok=true
# shellcheck source=scripts/compose_run.sh
source "$ROOT/scripts/compose_run.sh"
compose_run --no-deps backup ping "$job" "$ok" "${line#*: }" >&2 ||
  echo "labra.sh: the $job ping was not sent" >&2
exit "$status"
