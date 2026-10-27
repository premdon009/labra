#!/usr/bin/env bash
# Upgrade Labra to another version, rolling back by itself if anything fails.
#
#   scripts/upgrade.sh VERSION      e.g. 0.2.0: the image ghcr.io/premdon009/labra:VERSION
#   scripts/upgrade.sh IMAGE        any image reference, e.g. a mirror's
#
# 1. Pulls the new image and checks the disk; nothing changes if either fails.
# 2. Stops the web app, so nothing is written from here on, and takes a backup tagged
#    pre-upgrade.
# 3. Starts the stack on the new image: migrations, then the app, which must answer /readyz
#    within LABRA_UPGRADE_WAIT seconds (default 180).
# 4. If that fails: restores the pre-upgrade backup over the database, goes back to the old
#    image and checks the audit log.
# The result goes in the run log, which the System page shows.
# The image in use is kept as LABRA_IMAGE in the .env file beside compose.yaml (LABRA_ENV_FILE
# names another). LABRA_COMPOSE picks the Compose command (default "docker compose"),
# LABRA_ENGINE the container engine (default docker).
#
# Exit status: 0 upgraded, or already on it; 1 not upgraded, nothing changed; 2 bad arguments;
# 4 the upgrade failed and was rolled back; 5 the rollback failed too: follow
# docs/runbooks/restore-from-backup.md.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
read -ra compose <<<"${LABRA_COMPOSE:-docker compose}"
read -ra engine <<<"${LABRA_ENGINE:-docker}"
env_file=${LABRA_ENV_FILE:-$ROOT/.env}
wait_for=${LABRA_UPGRADE_WAIT:-180}

usage() { sed -n '2,21p' "$0"; }
case ${1:-} in
  -h | --help) usage; exit 0 ;;
  '') usage >&2; exit 2 ;;
esac
(($# == 1)) || { usage >&2; exit 2; }
if [[ $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+((a|b|rc)[0-9]+)?$ ]]; then
  new=ghcr.io/premdon009/labra:$1
elif [[ $1 == *[:@]* && $1 != -* ]]; then
  new=$1
else
  echo "Not a version or an image reference: $1" >&2
  exit 2
fi

# Backups wait while an upgrade runs, so the pre-upgrade backup is the newest one.
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
started=$(date -u +%FT%TZ)

log_run() {
  compose_run --no-deps backup log-run upgrade "$started" "$1" "$2" >/dev/null ||
    echo "The run log wasn't written." >&2
}

# Starts the stack, giving up after wait_for seconds: podman-compose waits for ever for an app
# that never gets healthy.
up() { timeout "$wait_for" "${compose[@]}" up -d --no-build 9<&-; }

ready() {
  local tries=$((wait_for / 2 + 1))
  while ((tries--)); do
    dc exec -T web python -m labra.probe /readyz >/dev/null 2>&1 && return 0
    ((tries)) && sleep 2
  done
  return 1
}

keep_image() {
  local tmp
  [[ -e $env_file ]] || (umask 077 && : >"$env_file")
  tmp=$(mktemp "$env_file.XXXXXX")
  { grep -v '^LABRA_IMAGE=' "$env_file" || true; echo "LABRA_IMAGE=$1"; } >"$tmp"
  chmod --reference="$env_file" "$tmp"
  mv "$tmp" "$env_file"
}

# The web container, found by its Compose label: podman-compose's `ps` takes no service name,
# and nerdctl's can list two containers for one; the last is the newest.
web=
for id in $(dc ps -q); do
  label=$("${engine[@]}" inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$id")
  [[ $label != web ]] || web=$id
done
if [[ -z $web ]]; then
  echo "The web app isn't running; start the stack first (docker compose up -d)." >&2
  exit 1
fi
old=$("${engine[@]}" inspect --format '{{.Config.Image}}' "$web")
old_id=$("${engine[@]}" inspect --format '{{.Image}}' "$web")
if [[ $old == "$new" ]]; then
  echo "Already on $new."
  exit 0
fi
echo "Upgrading from $old ($old_id) to $new"

if ! "${engine[@]}" image inspect "$new" >/dev/null 2>&1 && ! "${engine[@]}" pull "$new"; then
  echo "Couldn't get $new; nothing changed." >&2
  exit 1
fi
if ! dc exec -T web labra check-disk; then
  echo "Not enough disk space for the backup and the new image; nothing changed." >&2
  exit 1
fi

echo "Stopping the web app and taking a backup"
stop_web
if ! compose_run backup backup --tag pre-upgrade; then
  dc up -d --no-build >/dev/null
  log_run false "not upgraded to $new: the pre-upgrade backup failed"
  echo "The backup failed, so nothing was upgraded. See the messages above." >&2
  exit 1
fi
snapshots=$(dc exec -T db psql -U labra -d labra -Atc \
  "select snapshot from ops_run where kind = 'backup' and ok order by id desc limit 1")
# The USB copy restores fastest; Drive when there is no USB disk.
repo=usb
snapshot=$(grep -o 'usb:[^ ]*' <<<"$snapshots" | cut -d: -f2 || true)
if [[ -z $snapshot ]]; then
  repo=drive
  snapshot=$(grep -o 'drive:[^ ]*' <<<"$snapshots" | cut -d: -f2 || true)
fi

echo "Starting $new"
keep_image "$new"
# The migrations run first, as a job, so a failed one is its exit status on every Compose:
# podman-compose starts web after a failed migrate. They may take as long as they need. They
# use the database already running: nerdctl's compose run would start a second one.
if ! LABRA_IMAGE=$new compose_run --no-deps migrate; then
  why="the migrations failed"
elif ! LABRA_IMAGE=$new up; then
  why="the stack didn't start within $wait_for s"
elif ! LABRA_IMAGE=$new ready; then
  why="the app didn't answer within $wait_for s"
else
  log_run true "upgraded from $old to $new"
  echo "Upgraded to $new."
  exit 0
fi

echo "The upgrade failed: $why. Rolling back to $old from snapshot $repo:$snapshot" >&2
keep_image "$old"
export LABRA_IMAGE=$old
stop_web
if [[ -n $snapshot ]] &&
  compose_run restore restore --replace --from "$repo" "$snapshot" &&
  up && ready &&
  compose_run --no-deps web labra audit verify; then
  log_run false "not upgraded to $new: $why; rolled back to $old"
  echo "Rolled back: the lab runs $old again, with its data as before the upgrade." >&2
  exit 4
fi
log_run false "not upgraded to $new: $why, and the rollback to $old failed"
echo "THE ROLLBACK FAILED. Follow docs/runbooks/restore-from-backup.md (The same server)" \
  "with snapshot $repo:$snapshot." >&2
exit 5
