#!/usr/bin/env bash
# Entry point of the Labra backup image (ADR-0013). One job per run, then exit.
#
#   labra-backup backup [--prune] [--tag TAG]   dump the database, snapshot it with the files
#                                               into every repository; --prune applies the
#                                               retention afterwards (the nightly run)
#   labra-backup restore [--from usb|drive] [--replace] [SNAPSHOT]
#                                               load a snapshot's dump into the database (it
#                                               must be empty unless --replace) and put the
#                                               files back; the newest snapshot by default,
#                                               from the USB disk when there is one; exits 4
#                                               when the database loaded but the files didn't
#   labra-backup restore --scratch NAME_drill [--from usb|drive] [SNAPSHOT]
#                                               the drill: check the repository, load the dump
#                                               into a new scratch database, files left alone
#   labra-backup drop-database NAME_drill       drop a scratch database
#   labra-backup log-run KIND STARTED OK DETAIL add a run log row and ping the job's monitor
#   labra-backup init                           create the repositories that don't exist yet
#   labra-backup snapshots                      list the snapshots in every repository
#   labra-backup watchdog                       fetch LABRA_WATCHDOG_URL (default: the app's
#                                               /healthz) and ping the watchdog check only
#                                               when it answers, so silence means trouble
#   labra-backup repos                          the names of the configured repositories
#   labra-backup version                        tool versions
#
# Settings (environment): LABRA_BACKUP_REPO_DRIVE (e.g. rclone:drive:labra-backup),
# LABRA_BACKUP_REPO_USB (e.g. /backup/usb/labra), LABRA_HEARTBEAT_URL_<JOB>. Secrets:
# /run/secrets/database_url, /run/secrets/restic_password, /run/secrets/rclone_conf.
set -euo pipefail

SECRETS=${LABRA_SECRETS:-/run/secrets}
WORK=${LABRA_BACKUP_WORK:-/backup/work}
FILES=${LABRA_FILES_DIR:-/data/files}
HOST=labra
# The dump's path inside every snapshot, so a restore knows where to find it.
DUMP=$WORK/dump/labra.sql
KEEP=(--keep-within 2d --keep-within-hourly 7d --keep-within-daily 30d --keep-within-monthly 24m)
HEARTBEAT_MAX=10000
MISMATCH="'the restored tables don''t match the dump: '"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

# The repositories that are configured, as "name=location" lines.
repos() {
  [[ -z ${LABRA_BACKUP_REPO_DRIVE:-} ]] || echo "drive=$LABRA_BACKUP_REPO_DRIVE"
  [[ -z ${LABRA_BACKUP_REPO_USB:-} ]] || echo "usb=$LABRA_BACKUP_REPO_USB"
}

# The location of one configured repository by name, or of the first one when no name is
# given: the USB disk before Drive, since restoring from it needs no internet.
repo_location() {
  local want=$1 name location
  while IFS='=' read -r name location; do
    if [[ -z $want || $name == "$want" ]]; then
      echo "$location"
      return 0
    fi
  done < <(repos | sort -r)
  return 1
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
  elif ! pg_dump --no-owner --no-privileges --file="$DUMP" 2>"$WORK/pg_dump.err"; then
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
  rm -f "$DUMP"
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

# "table rows" for each COPY block of a plain dump: what every table must hold after a restore.
dump_counts() {
  awk '/^COPY [^ ]+ .* FROM stdin;$/ { table = $2; n = 0; next }
       table != "" && /^\\\.$/ { print table, n; table = ""; next }
       table != "" { n++ }' "$1"
}

# Every table in the restored database against the dump, as the last statement of the restore's
# transaction: a table that doesn't match raises, so the whole load rolls back.
check_counts_sql() {
  local table want
  echo "do \$check\$ declare got bigint; bad text := ''; begin"
  while read -r table want; do
    echo "  select count(*) into got from $table;"
    echo "  if got <> $want then bad := bad || '${table//\'/\'\'}: ' || got || ' rows, the dump has $want. '; end if;"
  done <"$WORK/counts"
  echo "  if bad <> '' then raise exception using message = $MISMATCH || bad; end if;"
  echo "end \$check\$;"
}

# A scratch database can be dropped and made again, so its name can never be the lab's own.
scratch_name() {
  [[ $1 =~ ^[a-z0-9_]+_drill$ ]] && return 0
  log "a scratch database's name ends in _drill (got $1)"
  return 2
}

cmd_restore() {
  local from='' scratch='' replace=false files=true snapshot=latest
  while (($#)); do
    case $1 in
      --from) from=$2; shift 2 ;;
      --scratch) scratch=$2; files=false; shift 2 ;;
      --replace) replace=true; shift ;;
      -*) echo "unknown argument: $1" >&2; exit 2 ;;
      *) snapshot=$1; shift ;;
    esac
  done
  local location target tables rows bad error sql=$WORK/restore.sql
  if [[ -n $scratch ]]; then
    scratch_name "$scratch" || return 2
  fi
  connect
  rclone_config
  if ! location=$(repo_location "$from"); then
    log "no repository${from:+ named $from} is configured"
    return 1
  fi
  if ! present "$location"; then
    log "no repository at $location (is the disk mounted?)"
    return 1
  fi
  target=${scratch:-$PGDATABASE}
  restic -r "$location" unlock >/dev/null 2>&1 || true
  if [[ -z $scratch && $replace == false && $(psql -X -At -c \
    "select count(*) from information_schema.tables where table_schema = 'public'") != 0 ]]; then
    log "the database $PGDATABASE already has tables; add --replace to overwrite them"
    return 3
  fi
  if [[ -n $scratch ]] && ! restic -r "$location" check >/dev/null 2>"$WORK/restic.err"; then
    log "the repository at $location is damaged: $(tail -3 "$WORK/restic.err" | tr '\n' ' ')"
    return 1
  fi
  mkdir -p "$WORK"
  if ! restic -r "$location" dump --host "$HOST" "$snapshot" "$DUMP" >"$sql" \
    2>"$WORK/restic.err"; then
    log "could not read the dump in $snapshot: $(tail -3 "$WORK/restic.err" | tr '\n' ' ')"
    return 1
  fi
  dump_counts "$sql" >"$WORK/counts"
  if [[ ! -s $WORK/counts ]]; then
    log "the dump in $snapshot holds no tables"
    return 1
  fi
  if [[ -n $scratch ]] && ! psql -X -q -v ON_ERROR_STOP=1 -d postgres \
    -c "drop database if exists \"$scratch\" with (force)" -c "create database \"$scratch\""; then
    log "could not create the scratch database $scratch"
    return 1
  fi
  # One transaction, the row counts checked last: a restore that stops half way, or loads
  # fewer rows than the dump holds, leaves the database as it was.
  if ! {
    if [[ $replace == true ]]; then echo 'drop schema public cascade; create schema public;'; fi
    cat "$sql"
    check_counts_sql
  } | psql -X -q -1 -v ON_ERROR_STOP=1 -d "$target" >/dev/null 2>"$WORK/psql.err"; then
    rm -f "$sql"
    bad=$(sed -n "s/.*the restored tables don't match the dump: //p" "$WORK/psql.err" | head -1)
    if [[ -n $bad ]]; then
      log "the restored tables don't match the dump: $bad"
    else
      log "the dump did not load: $(tail -3 "$WORK/psql.err" | tr '\n' ' ')"
    fi
    return 1
  fi
  rm -f "$sql"
  # The database is committed by now, so a failure here is a partial restore and says so.
  if [[ $files == true ]] && ! restic -r "$location" restore --host "$HOST" "$snapshot:$FILES" \
    --target "$FILES" >/dev/null 2>"$WORK/restic.err"; then
    error=$(tail -3 "$WORK/restic.err" | tr '\n' ' ')
    log "the database is restored from $snapshot, but the stored files are not: $error"
    return 4
  fi
  tables=$(wc -l <"$WORK/counts")
  rows=$(awk '{ n += $2 } END { print n + 0 }' "$WORK/counts")
  echo "$snapshot from $location into $target: $tables tables, $rows rows, as in the dump"
}

cmd_drop_database() {
  scratch_name "${1:-}" || return 2
  connect
  psql -X -q -v ON_ERROR_STOP=1 -d postgres -c "drop database if exists \"$1\" with (force)"
}

cmd_log_run() {
  (($# == 4)) || { echo "usage: labra-backup log-run KIND STARTED OK DETAIL" >&2; exit 2; }
  connect
  record "$1" "$2" "$3" "" "" "$4"
  heartbeat "$1" "$3" "$4"
}

# Pings only on success: a dead server, line or tunnel sends nothing, and the monitor's
# grace period turns that silence into one alert instead of one per blip.
cmd_watchdog() {
  local url=${LABRA_WATCHDOG_URL:-http://web:8000/healthz} body
  if ! body=$(curl -fsS -m 20 "$url" 2>&1); then
    log "watchdog: $url did not answer: $body"
    return 1
  fi
  if [[ $body != *'"status":"ok"'* ]]; then
    log "watchdog: $url answered without status ok: ${body:0:200}"
    return 1
  fi
  heartbeat watchdog true "$url answered"
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
  restore) cmd_restore "$@" ;;
  drop-database) cmd_drop_database "$@" ;;
  log-run) cmd_log_run "$@" ;;
  watchdog) cmd_watchdog ;;
  repos) repos | cut -d= -f1 ;;
  version) pg_dump --version; restic version; rclone version | head -1 ;;
  help | -h | --help) sed -n '2,/^set /p' "$0" | sed '$d; s/^# \{0,1\}//' ;;
  *) echo "unknown command: $cmd (try: labra-backup help)" >&2; exit 2 ;;
esac
