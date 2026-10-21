#!/usr/bin/env bash
# The monthly restore drill (ADR-0013). For each configured repository: check it, load its
# newest snapshot into a scratch database, compare every table with the dump, check the audit
# log's hash chain there, then drop the scratch database. The result goes to the run log and to
# LABRA_HEARTBEAT_URL_DRILL (/fail when anything failed). The lab keeps working meanwhile.
#
#   scripts/drill.sh
#
# LABRA_COMPOSE picks the Compose command (default "docker compose").
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
read -ra compose <<<"${LABRA_COMPOSE:-docker compose}"
case ${1:-} in -h | --help) sed -n '2,9p' "$0"; exit 0 ;; esac
scratch=labra_drill

exec 9<"$ROOT/scripts/backup.sh"
if ! flock -w "${LABRA_JOB_WAIT:-7200}" 9; then
  echo "a backup job is still running; giving up" >&2
  exit 1
fi
cd "$ROOT"
# 9<&-: what Compose starts must not hold the job lock, as podman-compose's container
# monitors outlive this script.
job() { "${compose[@]}" --profile jobs run --rm -T backup "$@" 9<&-; }

started=$(date -u +%FT%TZ)
ok=true
lines=()
err=$(mktemp)
trap 'rm -f "$err"' EXIT
if ! names=$(job repos 2>"$err"); then
  ok=false
  lines+=("the backup job did not start: $(tail -2 "$err" | tr '\n' ' ')")
  names=
fi
for name in $names; do
  if out=$(job restore --from "$name" --scratch "$scratch" 2>&1); then
    lines+=("$name: $(tail -1 <<<"$out")")
    if out=$("${compose[@]}" run --rm --no-deps -T web labra audit verify --database "$scratch" \
      9<&- 2>&1); then
      lines+=("$name: $(tail -1 <<<"$out")")
    else
      ok=false
      lines+=("$name: $(tail -1 <<<"$out")")
    fi
  else
    ok=false
    lines+=("$name: restore failed: $(tail -2 <<<"$out" | tr '\n' ' ')")
  fi
done
if ((${#lines[@]} == 0)); then
  ok=false
  lines+=("no repository configured: set LABRA_BACKUP_REPO_DRIVE or LABRA_BACKUP_REPO_USB")
fi
job drop-database "$scratch" >/dev/null 2>&1 || true
detail=$(printf '%s\n' "${lines[@]}")
printf '%s\n' "$detail"
job log-run drill "$started" "$ok" "$detail" >/dev/null 2>&1 || echo "run log not written" >&2
[[ $ok == true ]]
