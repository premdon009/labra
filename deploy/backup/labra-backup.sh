#!/usr/bin/env bash
# Entry point of the Labra backup image (ADR-0013). One job per run, then exit.
#
#   labra-backup backup [--prune] [--tag TAG]   dump the database, snapshot it with the files
#                                               into every repository; --prune applies the
#                                               retention afterwards (the nightly run)
#   labra-backup init                           create the repositories that don't exist yet
#   labra-backup snapshots                      list the snapshots in every repository
#   labra-backup version                        tool versions
#
# Settings (environment): LABRA_BACKUP_REPO_DRIVE (e.g. rclone:drive:labra-backup),
# LABRA_BACKUP_REPO_USB (e.g. /backup/usb/labra), LABRA_HEARTBEAT_URL_BACKUP. Secrets:
# /run/secrets/database_url, /run/secrets/restic_password, /run/secrets/rclone_conf.
set -euo pipefail

SECRETS=${LABRA_SECRETS:-/run/secrets}
WORK=${LABRA_BACKUP_WORK:-/backup/work}
FILES=${LABRA_FILES_DIR:-/data/files}
HOST=labra
KEEP=(--keep-within 2d --keep-within-hourly 7d --keep-within-daily 30d --keep-within-monthly 24m)
HEARTBEAT_MAX=10000

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

# The repositories that are configured, as "name=location" lines.
repos() {
  [[ -z ${LABRA_BACKUP_REPO_DRIVE:-} ]] || echo "drive=$LABRA_BACKUP_REPO_DRIVE"
  [[ -z ${LABRA_BACKUP_REPO_USB:-} ]] || echo "usb=$LABRA_BACKUP_REPO_USB"
}

# libpq settings from the app's database URL, so the password never sits on a command line.
connect() {
  local url rest auth hostport
  url=$(<"$SECRETS/database_url")
  rest=${url#*://}
  auth=${rest%%@*}
  hostport=${rest#*@}
  hostport=${hostport%%/*}
  export PGUSER=${auth%%:*}
  # Percent-escapes in the URL become the characters they stand for; a literal backslash
  # is doubled first so printf keeps it.
  local password=${auth#*:}
  password=${password//\\/\\\\}
  export PGPASSWORD
  PGPASSWORD=$(printf '%b' "${password//%/\\x}")
  export PGHOST=${hostport%%:*}
  export PGPORT=5432
  [[ $hostport != *:* ]] || PGPORT=${hostport##*:}
  local db=${rest#*/}
  export PGDATABASE=${db%%\?*}
}

# rclone refreshes its Google token in its config file, so it gets a writable copy.
rclone_config() {
  if [[ -r $SECRETS/rclone_conf ]]; then
    mkdir -p "$WORK"
    install -m 600 "$SECRETS/rclone_conf" "$WORK/rclone.conf"
    export RCLONE_CONFIG=$WORK/rclone.conf
  fi
}

# A local repository that isn't there means the disk isn't mounted: never create one in the
# empty mount point, where it would fill the server's own disk.
present() {
  local location=$1
  [[ $location == *:* ]] || [[ -f $location/config ]]
}

# Ping the job's monitor: https only, /fail on failure, the body capped. A monitor that
# can't be reached never fails the job.
heartbeat() {
  local job=$1 ok=$2 detail=$3 var url
  var=LABRA_HEARTBEAT_URL_${job^^}
  url=${!var:-}
  [[ -n $url ]] || return 0
  if [[ $url != https://* ]]; then
    log "heartbeat for $job not sent: the URL must use https"
    return 0
  fi
  [[ $ok == true ]] || url=${url%/}/fail
  printf '%s' "${detail:0:$HEARTBEAT_MAX}" |
    curl -fsS -m 10 --retry 2 -o /dev/null --data-binary @- "$url" ||
    log "heartbeat for $job not delivered"
}

# One row in the run log. psql quotes every value (:'name'), so a detail can't inject SQL.
record() {
  local kind=$1 started=$2 ok=$3 snapshot=$4 bytes=$5 detail=$6
  psql -X -q -v ON_ERROR_STOP=1 -v kind="$kind" -v started="$started" -v ok="$ok" \
    -v snapshot="$snapshot" -v bytes="$bytes" -v detail="${detail:0:2000}" <<'SQL' ||
insert into ops_run (kind, started_at, finished_at, ok, snapshot, bytes_added, detail)
values (:'kind', :'started', greatest(now(), :'started'::timestamptz), :'ok',
        nullif(:'snapshot', ''), nullif(:'bytes', '')::bigint, nullif(:'detail', ''));
SQL
    log "run log not written"
}

# The value of one field in restic's JSON summary line.
summary_field() {
  sed -n "s/.*\"message_type\":\"summary\".*\"$1\":\"\{0,1\}\([^,\"}]*\).*/\1/p" | tail -1
}

cmd_backup() {
  local prune=false tag=scheduled
  while (($#)); do
    case $1 in
      --prune) prune=true; shift ;;
      --tag) tag=$2; shift 2 ;;
      *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
  done
  local started ok=true snapshots=() added=0 problems=() name location out id bytes
  started=$(date -u +%FT%TZ)
  mkdir -p "$WORK/dump"
  connect
  rclone_config
  if [[ -z $(repos) ]]; then
    problems+=("no repository configured: set LABRA_BACKUP_REPO_DRIVE or LABRA_BACKUP_REPO_USB")
  elif ! pg_dump --file="$WORK/dump/labra.sql" 2>"$WORK/pg_dump.err"; then
    problems+=("pg_dump failed: $(tail -3 "$WORK/pg_dump.err" | tr '\n' ' ')")
  else
    while IFS='=' read -r name location; do
      if ! present "$location"; then
        problems+=("$name: no repository at $location (disk not mounted?)")
        continue
      fi
      restic -r "$location" unlock >/dev/null 2>&1 || true
      if out=$(restic -r "$location" backup --json --host "$HOST" --tag "$tag" \
        "$WORK/dump" "$FILES" 2>"$WORK/restic.err"); then
        id=$(summary_field snapshot_id <<<"$out")
        bytes=$(summary_field data_added <<<"$out")
        snapshots+=("$name:${id:0:8}")
        added=$((added + ${bytes:-0}))
        log "$name: snapshot ${id:0:8}, ${bytes:-0} bytes added"
      else
        problems+=("$name: restic backup failed: $(tail -3 "$WORK/restic.err" | tr '\n' ' ')")
        continue
      fi
      if [[ $prune == true ]] &&
        ! restic -r "$location" forget --host "$HOST" "${KEEP[@]}" --prune \
          >/dev/null 2>"$WORK/restic.err"; then
        problems+=("$name: retention failed: $(tail -3 "$WORK/restic.err" | tr '\n' ' ')")
      fi
    done < <(repos)
  fi
  rm -f "$WORK/dump/labra.sql"
  local detail
  if ((${#problems[@]})); then
    ok=false
    detail=$(printf '%s\n' "${problems[@]}")
    log "backup failed: $detail"
  else
    detail="${#snapshots[@]} snapshot(s), $added bytes added"
  fi
  record backup "$started" "$ok" "${snapshots[*]}" "$added" "$detail"
  heartbeat backup "$ok" "$detail"
  [[ $ok == true ]]
}

cmd_init() {
  local name location failed=0
  rclone_config
  while IFS='=' read -r name location; do
    if restic -r "$location" cat config >/dev/null 2>&1; then
      log "$name: repository already exists"
    elif [[ $location != *:* && ! -d $location && ! -w $(dirname "$location") ]]; then
      log "$name: cannot create $location (is the disk mounted and writable by uid $(id -u)?)"
      failed=1
    elif restic -r "$location" init >/dev/null; then
      log "$name: repository created"
    else
      failed=1
    fi
  done < <(repos)
  return "$failed"
}

cmd_snapshots() {
  local name location
  rclone_config
  while IFS='=' read -r name location; do
    echo "== $name ($location)"
    restic -r "$location" snapshots --host "$HOST" || true
  done < <(repos)
}

cmd=${1:-help}
(($#)) && shift
case $cmd in
  backup) cmd_backup "$@" ;;
  init) cmd_init ;;
  snapshots) cmd_snapshots ;;
  version) pg_dump --version; restic version; rclone version | head -1 ;;
  help | -h | --help) sed -n '2,/^set /p' "$0" | sed '$d; s/^# \{0,1\}//' ;;
  *) echo "unknown command: $cmd (try: labra-backup help)" >&2; exit 2 ;;
esac
