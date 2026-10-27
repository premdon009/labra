#!/usr/bin/env bash
# Bring the whole stack up on any Compose implementation, prove it works end to end, and tear
# it down again (ADR-0009). Uses its own project name, ports, subnet and throwaway secrets, so
# it never touches ./secrets or a stack that is already running.
#
#   scripts/stack_smoke.sh [--compose "docker compose"|"podman compose"|"podman-compose"|
#                           "nerdctl compose"] [--proxy caddy|nginx] [--image REF]
#                          [--backup-image REF] [--keep]
#
# Without --compose, the first reachable of docker, podman and nerdctl is used. Both images must
# already exist locally (scripts/build_image.sh, and again with --backup). With --keep the stack stays up and its settings
# are left in <work>/stack.env for scripts/compare_runtimes.sh. A drill, restore or upgrade that
# hangs is stopped after SMOKE_STEP_LIMIT seconds (default 600) and fails its check.
# Exit 0 pass, 1 fail, 2 unchecked (no runtime).
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
compose_cmd=
proxy=caddy
image=localhost/labra:dev
backup_image=localhost/labra-backup:dev
keep=false
while (($#)); do
  case $1 in
    --compose) compose_cmd=$2; shift 2 ;;
    --proxy) proxy=$2; shift 2 ;;
    --image) image=$2; shift 2 ;;
    --backup-image) backup_image=$2; shift 2 ;;
    --keep) keep=true; shift ;;
    -h | --help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z $compose_cmd ]]; then
  for e in docker podman nerdctl; do
    if command -v "$e" >/dev/null 2>&1 && "$e" info >/dev/null 2>&1; then
      compose_cmd="$e compose"
      break
    fi
  done
fi
if [[ -z $compose_cmd ]]; then
  echo "UNCHECKED: no container runtime reachable." >&2
  exit 2
fi
read -ra compose <<<"$compose_cmd"
# `podman compose` prints a banner on stderr; captured values below read stdout only.

project=labra-smoke-$$
work=$(mktemp -d)
http_port=${SMOKE_HTTP_PORT:-18080}
https_port=${SMOKE_HTTPS_PORT:-18443}
site=labra.lan
files=(-f "$ROOT/compose.yaml")
[[ $proxy == nginx ]] && files+=(-f "$ROOT/deploy/nginx/compose.nginx.yaml")
dc() { "${compose[@]}" -p "$project" "${files[@]}" "$@"; }
# A one-off container, run the way the host scripts run them.
# shellcheck source=scripts/compose_run.sh
source "$ROOT/scripts/compose_run.sh"
job() { local compose=("${compose[@]}" -p "$project" "${files[@]}"); compose_run "$@"; }
engine=${compose[0]%-compose}
# One container of a service, by its labels: podman-compose's `ps` takes no service name, and
# nerdctl compose can list two.
cid() {
  "$engine" ps -q --filter "label=com.docker.compose.project=$project" \
    --filter "label=com.docker.compose.service=$1" | head -1
}
# Checks print to the job's output (fd 3) even from a step whose output goes to its own log.
exec 3>&1

# Each container's state and, for one with a health check, what its last checks printed.
report() {
  local id
  for id in $("$engine" ps -aq --filter "label=com.docker.compose.project=$project"); do
    "$engine" inspect --format '{{.Name}}: {{.State.Status}}, exit {{.State.ExitCode}}
{{- if .State.Health}}, {{.State.Health.Status}}{{range .State.Health.Log}}
  check exit {{.ExitCode}}: {{.Output}}{{end}}{{end}}' "$id" 2>&1 | tail -c 2000
  done
}

# A step that hangs is stopped after LIMIT seconds, with the container commands still running.
limit=${SMOKE_STEP_LIMIT:-600}
limit() {
  timeout "$limit" "$@"
  local rc=$?
  if ((rc == 124)); then
    echo "INFO  ${1##*/} still running after $limit s, stopped; left running:" >&3
    pgrep -af 'compose|podman|docker|nerdctl' | sed 's/^/INFO    /' >&3
  fi
  return "$rc"
}

cleanup() {
  if [[ $keep == false ]]; then
    # The backup job wrote the repositories as its own uid; it removes them too.
    job --no-deps --entrypoint rm backup -rf /backup/usb/labra /backup/usb/drive >/dev/null 2>&1
    dc --profile jobs down -v >/dev/null 2>&1
    [[ -z ${engine:-} ]] || "$engine" rmi -f localhost/labra-smoke:next \
      localhost/labra-smoke:broken >/dev/null 2>&1
    rm -rf "$work"
  else
    declare -p project compose_cmd proxy LABRA_IMAGE LABRA_BACKUP_IMAGE LABRA_BACKUP_USB_DIR \
      LABRA_SECRETS_DIR LABRA_SITE \
      LABRA_HTTP_PORT LABRA_HTTPS_PORT LABRA_EDGE_SUBNET >"$work/stack.env"
    echo "Kept: project $project, settings in $work/stack.env"
  fi
}
trap cleanup EXIT

# Secrets the way running-the-stack.md sets them up. The app and the jobs read the URLs as a
# non-root user whose host UID differs by runtime, so those files are world-readable inside a
# 0700 directory; db_password is read as root.
secrets=$work/secrets
mkdir -m 700 "$secrets"
openssl rand -hex 24 | tr -d '\n' >"$secrets/db_password"
db_url() { printf 'postgresql+psycopg://%s:%s@db:5432/labra' "$1" "$2" >"$secrets/$3"; }
db_url labra "$(<"$secrets/db_password")" owner_database_url
db_url labra_app "$(openssl rand -hex 24)" database_url
db_url labra_backup "$(openssl rand -hex 24)" backup_database_url
openssl rand -hex 24 | tr -d '\n' >"$secrets/restic_password"
printf '[drive]\ntype = local\n' >"$secrets/rclone.conf"
chmod 600 "$secrets/db_password"
chmod 644 "$secrets"/*database_url "$secrets/restic_password" "$secrets/rclone.conf"
if [[ $proxy == nginx ]]; then
  mkdir -m 700 "$secrets/tls"
  openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj "/CN=$site" \
    -addext "subjectAltName=DNS:$site" -keyout "$secrets/tls/labra.key" \
    -out "$secrets/tls/labra.crt" 2>/dev/null
  chmod 644 "$secrets/tls/labra.crt"
fi

# The USB disk is a folder here; the backup job writes it as uid 10001 on every runtime.
mkdir -m 777 "$work/usb"
export LABRA_IMAGE=$image LABRA_SECRETS_DIR=$secrets LABRA_SITE=$site
export LABRA_BACKUP_IMAGE=$backup_image LABRA_BACKUP_USB_DIR=$work/usb
export LABRA_HTTP_PORT=$http_port LABRA_HTTPS_PORT=$https_port
export LABRA_EDGE_SUBNET=172.29.$((RANDOM % 200 + 20)).0/24

echo "Stack: ${compose[*]}, proxy $proxy, image $image"
started=${EPOCHREALTIME/./}
if ! dc up -d --no-build >"$work/up.log" 2>&1; then
  tail -20 "$work/up.log"
  dc logs --tail 30 2>&1 | tail -40
  report
  echo "FAIL  stack did not start"
  exit 1
fi

fails=0
check() {
  local what=$1 want=$2 got=$3
  # shellcheck disable=SC2053 # want may be a glob pattern
  if [[ $got == $want ]]; then
    echo "PASS  $what"
  else
    echo "FAIL  $what: wanted '$want', got '$got'"
    fails=$((fails + 1))
  fi
}
https() { curl -sk --resolve "$site:$https_port:127.0.0.1" "$@"; }
url() { echo "https://$site:$https_port$1"; }
code() { https -o /dev/null -w '%{http_code}' "$@"; }

# Ready through the proxy, not just up: where Compose doesn't wait on health checks, web starts
# before migrate ends, and after a restart the proxy may still reach for the container that went.
ready() {
  for _ in $(seq 60); do
    [[ $(code "$(url /readyz)") == 200 ]] && return
    sleep 1
  done
}
ready
took=$((${EPOCHREALTIME/./} - started))
echo "INFO  ready in $((took / 1000000)).$((took / 100000 % 10)) s"

check "/healthz through the proxy" 200 "$(code "$(url /healthz)")"
check "/readyz: database, migrations, disk" '*"database":"ok","migrations":"ok","disk":"ok"*' \
  "$(https "$(url /readyz)")"
check "/metrics kept off the network" 404 "$(code "$(url /metrics)")"
check "the manual is inside the image" yes \
  "$(https "$(url /manual/getting-started/login/)" | grep '<h1[^>]*>Signing in' >/dev/null && echo yes || echo no)"
check "the runbooks are inside the image" yes \
  "$(https "$(url /manual/runbooks/disk-full/)" | grep '<h1[^>]*>Disk full' >/dev/null && echo yes || echo no)"
headers=$(https -D - -o /dev/null "$(url /login)" | tr -d '\r' | tr '[:upper:]' '[:lower:]')
for h in strict-transport-security content-security-policy x-frame-options \
  x-content-type-options referrer-policy; do
  check "header $h" yes "$(grep -q "^$h:" <<<"$headers" && echo yes || echo no)"
done
csp=$(grep '^content-security-policy:' <<<"$headers")
check "one CSP through the proxy, the app's, no inline code or eval" yes \
  "$([[ $(wc -l <<<"$csp") == 1 && $csp == *"script-src 'self';"* && $csp != *unsafe* ]] &&
    echo yes || echo no)"
check "plain HTTP redirects to HTTPS" '30[178] https://*' \
  "$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -H "Host: $site" \
    "http://127.0.0.1:$http_port/login")"
tunnel=$(dc exec -T web python -c "
import urllib.request as u, urllib.error as e
def get(p):
    try: return u.urlopen('http://proxy:8080' + p, timeout=5).status
    except e.HTTPError as x: return x.code
print(get('/healthz'), get('/metrics'))" 2>/dev/null | tail -1)
check "tunnel listener: app 200, /metrics 404" "200 404" "$tunnel"
check "Postgres: fsync and data checksums on" "on on" \
  "$(dc exec -T db psql -U labra -d labra -Atc \
    "select current_setting('fsync') || ' ' || current_setting('data_checksums')" 2>/dev/null)"
check "web, the backup job: logins that aren't superusers" "labra_app f f|labra_backup f t" \
  "$(dc exec -T db psql -U labra -d labra -Atc "select string_agg(concat_ws(' ', rolname,
    rolsuper, pg_has_role(oid, 'pg_read_all_data', 'member')), '|' order by rolname)
    from pg_roles where rolname in ('labra_app', 'labra_backup')" 2>/dev/null)"
check "web's login can't change the schema" InsufficientPrivilege "$(dc exec -T web python -c "
from sqlalchemy import text
from labra.core.db import get_engine
with get_engine().connect() as c:
    try:
        c.execute(text('create table planted (id int)'))
        print('created as', c.scalar(text('select current_user')))
    except Exception as x:
        print(type(getattr(x, 'orig', x)).__name__)" 2>/dev/null | tail -1)"

# First start, then sign in through the proxy.
password=smoke-test-pass-$$
dc exec -T web labra add-branch --code MAIN --name "Main lab" --kind main_lab >/dev/null 2>&1
printf '%s\n%s\n' "$password" "$password" |
  dc exec -T web labra create-admin --username admin --full-name "Smoke Admin" >/dev/null 2>&1
jar=$work/cookies
sign_in() {
  local token
  rm -f "$jar"
  token=$(https -c "$jar" -b "$jar" "$(url /login)" |
    sed -n 's/.*name="csrf_token" value="\([^"]*\)".*/\1/p' | head -1)
  code -c "$jar" -b "$jar" -d "username=admin&password=$password&csrf_token=$token" "$(url /login)"
}
check "sign in" "303" "$(sign_in)"
check "admin page after sign-in" 200 "$(code -b "$jar" "$(url /admin/branches)")"
check "forged CSRF token refused" 403 "$(code -b "$jar" \
  -d "username=admin&password=x&csrf_token=forged" "$(url /login)")"
check "audit log intact" '*intact*' "$(dc exec -T web labra audit verify 2>/dev/null | head -1)"

# The laptop budgets: three users against about two years of patients, with the containers held
# to 2 CPUs and 4 GB between them. Only a run on the real laptop counts; this one catches a
# regression. The patients stay for the backups below, so those are a realistic size too.
# compose.yaml caps every container's logs. Docker reports it as set; Podman and nerdctl
# translate it to their own log drivers, so they are shown rather than checked.
logs_config=$("$engine" inspect --format '{{json .HostConfig.LogConfig}}' "$(cid web)" 2>&1)
if [[ $engine == docker ]]; then
  check "web's logs rotate" 'json-file 10m 5' "$(python3 -c '
import json, sys
c = json.loads(sys.argv[1])
print(c["Type"], c["Config"].get("max-size"), c["Config"].get("max-file"))' "$logs_config" 2>&1)"
else
  echo "INFO  web's log settings on $engine: $logs_config"
fi
cap() { "$engine" update --cpus "$2" --memory "$3" --memory-swap "$3" "$(cid "$1")"; }
capped=$(cap web 1 2g >/dev/null 2>&1 && cap db 0.75 1536m >/dev/null 2>&1 &&
  cap proxy 0.25 512m >/dev/null 2>&1 && echo yes || echo no)
echo "INFO  containers capped to 2 CPUs and 4 GB between them: $capped"
python3 "$ROOT/scripts/laptop_budget.py" fill 50000 |
  dc exec -T db psql -U labra -d labra -q -v ON_ERROR_STOP=1 >/dev/null 2>&1
check "50,000 synthetic patients added" 50000 \
  "$(dc exec -T db psql -U labra -d labra -Atc 'select count(*) from patient' 2>/dev/null)"
budget=$(LABRA_BUDGET_PASSWORD=$password python3 "$ROOT/scripts/laptop_budget.py" run \
  --port "$https_port" --site "$site" --username admin --duration 20 \
  --compose "$(printf '%q ' "${compose[@]}" -p "$project" "${files[@]}")" 2>&1)
grep -E '^(PASS|FAIL|WARN) ' <<<"$budget" | sed 's/^/INFO  budget: /'
check "laptop budgets: pages, search and memory with 3 users" yes \
  "$(grep -q '^PASS  page_p95_ms' <<<"$budget" && ! grep -q '^FAIL' <<<"$budget" &&
    echo yes || echo no)"
check "backup job not started by up" 0 "$(dc ps -a --format '{{.Service}}' 2>/dev/null |
  grep -c '^backup$')"
version=$(job --no-deps backup version 2>"$work/version.log" | tr '\n' ' ')
check "backup job runs on request" '*restic 0.*' "$version"
[[ $version == *"restic 0."* ]] || tail -5 "$work/version.log" | sed 's/^/INFO    /'

# A real backup into both repositories: rclone's local backend stands in for Google Drive.
bk() {
  job --no-deps -e LABRA_BACKUP_REPO_USB="${usb_repo:-/backup/usb/labra}" \
    -e LABRA_BACKUP_REPO_DRIVE=rclone:drive:/backup/usb/drive backup "$@" >>"$work/backup.log" 2>&1
}
runs() {
  dc exec -T db psql -U labra -d labra -Atc \
    "select ok, snapshot, coalesce(bytes_added, 0) from ops_run where kind = 'backup' order by id" \
    2>/dev/null
}
check "backup repositories created" 0 "$(bk init; echo $?)"
check "backup into both repositories" 0 "$(bk backup; echo $?)"
check "backup run logged with both snapshots" 't|drive:* usb:*|*' "$(runs | tail -1)"
first=$(runs | tail -1 | cut -d'|' -f3)
echo "INFO  first backup added $first bytes across both repositories"
bk backup
second=$(runs | tail -1 | cut -d'|' -f3)
echo "INFO  second backup added $second bytes"
# Restic cuts the dump into chunks of 0.5 to 8 MiB, and each row changed since the first
# backup adds its whole chunk again, in each repository: from a sixth to over half of the first
# so far. Without deduplication the second would be as big as the first.
check "second backup adds little" yes "$( ((second < first * 3 / 4)) && echo yes || echo no)"
check "nightly run applies the retention" 0 "$(bk backup --prune --tag nightly; echo $?)"
check "both repositories list three snapshots" 2 "$(bk snapshots; grep -c '^3 snapshots$' "$work/backup.log")"
check "missing USB disk fails the run, Drive still copied" 1 "$(usb_repo=/backup/usb/unplugged bk backup; echo $?)"
check "failed run logged with the Drive snapshot" 'f|drive:*|*' "$(runs | tail -1)"

# On a new server the restore is the first to mount the files volume, so the backup image's
# own folder decides who owns it.
probe=labra-smoke-files-$$
check "the backup image can write to a new files volume" ok "$("$engine" run --rm \
  --entrypoint sh -v "$probe:/data/files" "$backup_image" -c 'touch /data/files/x && echo ok' 2>&1)"
"$engine" volume rm -f "$probe" >/dev/null 2>&1 || true

# The monthly drill and a restore, through the host scripts the runbook uses.
export LABRA_COMPOSE="${compose[*]} -p $project ${files[*]}"
export LABRA_BACKUP_REPO_USB=/backup/usb/labra LABRA_BACKUP_REPO_DRIVE=rclone:drive:/backup/usb/drive
sql() { dc exec -T db psql -U labra -d labra -Atc "$1" 2>/dev/null; }
drill() { limit "$ROOT/scripts/drill.sh" >>"$work/drill.log" 2>&1; }
restore() { limit "$ROOT/scripts/restore.sh" "$@" >>"$work/restore.log" 2>&1; }
last_drill() { sql "select ok from ops_run where kind = 'drill' order by id desc limit 1"; }
b9="select count(*) from branch where code = 'B9'"
check "restore drill of both repositories" 0 "$(drill; echo $?)"
check "drill logged as passed" t "$(last_drill)"
check "drill checked the audit log in both copies" 2 "$(grep -c '^[a-z]*: Audit log intact' "$work/drill.log")"
check "drill leaves no scratch database" 0 \
  "$(sql "select count(*) from pg_database where datname = 'labra_drill'")"
dc exec -T web labra add-branch --code B9 --name "Branch nine" --kind collection_centre >/dev/null 2>&1
check "restore refuses a database that holds data" 3 "$(restore; echo $?)"
check "refused restore changed nothing" 1 "$(sql "$b9")"
check "restore --replace from the newest snapshot" 0 "$(restore --replace; echo $?)"
check "restore checked the audit log" '*Audit log intact*' "$(tail -3 "$work/restore.log")"
check "data written after the backup is gone" 0 "$(sql "$b9")"
ready
check "sign in after the restore" 303 "$(sign_in)"
job --no-deps --entrypoint sh backup -c 'chmod -R u+w /backup/usb/labra/data &&
  find /backup/usb/labra/data -type f -exec truncate -s 64 {} +' >/dev/null 2>&1
check "drill fails on a damaged repository" 1 "$(drill; echo $?)"
check "failed drill logged" f "$(last_drill)"
check "failed drill names the damaged copy" 1 "$(grep -c '^usb: restore failed' "$work/drill.log")"

# The nightly audit check, the disk check and the watchdog, through the wrappers the timers run.
last_run() { sql "select ok from ops_run where kind = '$1' order by id desc limit 1"; }
check "audit check from the timer's wrapper" 0 "$("$ROOT/scripts/labra.sh" audit verify >/dev/null 2>&1; echo $?)"
check "audit check logged" t "$(last_run verify)"
check "disk check" 0 "$("$ROOT/scripts/labra.sh" check-disk >/dev/null 2>&1; echo $?)"
check "disk check logged" t "$(last_run disk)"
check "watchdog reaches the app" 0 "$("$ROOT/scripts/watchdog.sh" >/dev/null 2>&1; echo $?)"
check "watchdog fails when nothing answers" 1 \
  "$(LABRA_WATCHDOG_URL=http://web:9/healthz "$ROOT/scripts/watchdog.sh" >/dev/null 2>&1; echo $?)"
system=$(https -b "$jar" "$(url /admin/system)")
check "System page reads the proxy's certificate" yes "$(grep -q 'Valid until' <<<"$system" && echo yes)"
# Only Caddy's own certificate renews by itself; a hand-made nginx one is renewed by hand.
renews=no
grep -q 'renews it by itself' <<<"$system" && renews=yes
check "System page knows who renews the certificate" "$([[ $proxy == caddy ]] && echo yes || echo no)" "$renews"
check "System page shows the failed drill" yes "$(grep -q 'usb: restore failed' <<<"$system" && echo yes)"
logs=$(dc logs --no-color web 2>&1)
check "logs hold no password" 0 "$(grep -c "$password" <<<"$logs")"
check "logs hold no database URL" 0 "$(grep -c 'postgresql+psycopg' <<<"$logs")"

# An upgrade, then one to an image whose migration fails, which must roll back by itself.
export LABRA_ENGINE=$engine LABRA_ENV_FILE=$work/env LABRA_UPGRADE_WAIT=90
# The drill above damaged the USB copy; a fresh one, so the pre-upgrade backups succeed.
job --no-deps --entrypoint rm backup -rf /backup/usb/labra >/dev/null 2>&1
bk init
mkdir "$work/next" "$work/broken"
printf 'FROM %s\nLABEL org.labra.smoke=next\n' "$image" >"$work/next/Dockerfile"
versions=$(dc exec -T web python -c \
  'import labra, pathlib; print(pathlib.Path(labra.__file__).parent / "migrations" / "versions")' |
  tail -1)
cat >"$work/broken/9999_smoke_broken.py" <<PY
revision = "9999_smoke_broken"
down_revision = "$(sql 'select version_num from alembic_version')"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("select 1/0")


def downgrade() -> None:
    pass
PY
printf 'FROM %s\nCOPY 9999_smoke_broken.py %s/\n' "$image" "$versions" >"$work/broken/Dockerfile"
if [[ $engine == nerdctl ]]; then
  # nerdctl builds with BuildKit, which looks a FROM image up in a registry, never among the
  # local images. So a container of the image is committed instead, with its command put back.
  derive() { # TAG [FILE FOLDER]
    local c
    c=$("$engine" run -d "$image" sleep infinity) || return
    [[ -z ${2:-} ]] || "$engine" cp "$2" "$c:$3/"
    "$engine" commit -c "CMD $("$engine" image inspect --format '{{json .Config.Cmd}}' "$image")" \
      "$c" "$1"
    "$engine" rm -f "$c"
  }
  derive localhost/labra-smoke:next >"$work/build.log" 2>&1
  derive localhost/labra-smoke:broken "$work/broken/9999_smoke_broken.py" "$versions" \
    >>"$work/build.log" 2>&1
else
  "$engine" build -q -t localhost/labra-smoke:next "$work/next" >"$work/build.log" 2>&1
  "$engine" build -q -t localhost/labra-smoke:broken "$work/broken" >>"$work/build.log" 2>&1
fi
upgrade() { limit "$ROOT/scripts/upgrade.sh" "$@" >>"$work/upgrade.log" 2>&1; }
web_image() { "$engine" inspect --format '{{.Config.Image}}' "$(cid web)"; }
backups="select count(*) from ops_run where kind = 'backup' and ok"
before=$(sql "$backups")
fails_before_upgrade=$fails
check "upgrade to a new image" 0 "$(upgrade localhost/labra-smoke:next; echo $?)"
check "web runs the new image" localhost/labra-smoke:next "$(web_image)"
check "upgrade logged" t "$(last_run upgrade)"
check "pre-upgrade backup taken" $((before + 1)) "$(sql "$backups")"
dc exec -T web labra add-branch --code B8 --name "Branch eight" --kind collection_centre >/dev/null 2>&1
check "an upgrade whose migration fails rolls back" 4 "$(upgrade localhost/labra-smoke:broken; echo $?)"
# Not the stack start's migration: there, podman-compose starts web after it fails.
check "the failed migration stopped the upgrade before the app started" 1 \
  "$(grep -c '^The upgrade failed: the migrations failed\.' "$work/upgrade.log")"
check "web runs the previous image again" localhost/labra-smoke:next "$(web_image)"
check "failed upgrade logged" f "$(last_run upgrade)"
check "data from before the upgrade kept" 1 "$(sql "select count(*) from branch where code = 'B8'")"
check "the image in use is kept for the next start" "LABRA_IMAGE=localhost/labra-smoke:next" \
  "$(cat "$work/env")"
ready
check "sign in after the rollback" 303 "$(sign_in)"
((fails == fails_before_upgrade)) || tail -20 "$work/upgrade.log" | sed 's/^/INFO    /'

echo "$((fails == 0 ? 1 : 0)) stack ($proxy on ${compose[*]}): $fails failed" |
  sed 's/^1 /PASS  /; s/^0 /FAIL  /'
((fails == 0))
