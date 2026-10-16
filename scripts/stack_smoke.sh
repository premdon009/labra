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
# are left in <work>/stack.env for scripts/compare_runtimes.sh.
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
    -h | --help) sed -n '2,13p' "$0"; exit 0 ;;
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

cleanup() {
  if [[ $keep == false ]]; then
    # The backup job wrote the repositories as its own uid; it removes them too.
    dc --profile jobs run --rm --no-deps -T --entrypoint rm backup -rf /backup/usb/labra \
      /backup/usb/drive >/dev/null 2>&1
    dc --profile jobs down -v >/dev/null 2>&1
    rm -rf "$work"
  else
    declare -p project compose_cmd proxy LABRA_IMAGE LABRA_BACKUP_IMAGE LABRA_BACKUP_USB_DIR \
      LABRA_SECRETS_DIR LABRA_SITE \
      LABRA_HTTP_PORT LABRA_HTTPS_PORT LABRA_EDGE_SUBNET >"$work/stack.env"
    echo "Kept: project $project, settings in $work/stack.env"
  fi
}
trap cleanup EXIT

# Secrets the way running-the-stack.md sets them up. The app reads database_url as a non-root
# user whose host UID differs by runtime, so that one file is world-readable inside a 0700
# directory; the others are read as root.
secrets=$work/secrets
mkdir -m 700 "$secrets"
openssl rand -hex 24 | tr -d '\n' >"$secrets/db_password"
printf 'postgresql+psycopg://labra:%s@db:5432/labra' "$(<"$secrets/db_password")" \
  >"$secrets/database_url"
openssl rand -hex 24 | tr -d '\n' >"$secrets/restic_password"
printf '[drive]\ntype = local\n' >"$secrets/rclone.conf"
chmod 600 "$secrets/db_password"
chmod 644 "$secrets/database_url" "$secrets/restic_password" "$secrets/rclone.conf"
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

# Ready, not just up: where Compose doesn't wait on health checks, web starts before migrate ends.
for _ in $(seq 60); do
  [[ $(code "$(url /readyz)") == 200 ]] && break
  sleep 1
done
took=$((${EPOCHREALTIME/./} - started))
echo "INFO  ready in $((took / 1000000)).$((took / 100000 % 10)) s"

check "/healthz through the proxy" 200 "$(code "$(url /healthz)")"
check "/readyz: database, migrations, disk" '*"database":"ok","migrations":"ok","disk":"ok"*' \
  "$(https "$(url /readyz)")"
check "/metrics kept off the network" 404 "$(code "$(url /metrics)")"
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
check "backup job not started by up" 0 "$(dc ps -a --format '{{.Service}}' 2>/dev/null |
  grep -c '^backup$')"
check "backup job runs on request" '*restic 0.*' \
  "$(dc --profile jobs run --rm --no-deps backup version 2>/dev/null | tr '\n' ' ')"

# A real backup into both repositories: rclone's local backend stands in for Google Drive.
bk() {
  dc --profile jobs run --rm --no-deps -T -e LABRA_BACKUP_REPO_USB="${usb_repo:-/backup/usb/labra}" \
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
echo "INFO  first backup added $(runs | tail -1 | cut -d'|' -f3) bytes across both repositories"
check "second backup adds little" yes "$(bk backup && (($(runs | tail -1 | cut -d'|' -f3) < 1000000)) &&
  echo yes || echo no)"
check "nightly run applies the retention" 0 "$(bk backup --prune --tag nightly; echo $?)"
check "both repositories list three snapshots" 2 "$(bk snapshots; grep -c '^3 snapshots$' "$work/backup.log")"
check "missing USB disk fails the run, Drive still copied" 1 "$(usb_repo=/backup/usb/unplugged bk backup; echo $?)"
check "failed run logged with the Drive snapshot" 'f|drive:*|*' "$(runs | tail -1)"

# The monthly drill and a restore, through the host scripts the runbook uses.
export LABRA_COMPOSE="${compose[*]} -p $project ${files[*]}"
export LABRA_BACKUP_REPO_USB=/backup/usb/labra LABRA_BACKUP_REPO_DRIVE=rclone:drive:/backup/usb/drive
sql() { dc exec -T db psql -U labra -d labra -Atc "$1" 2>/dev/null; }
drill() { "$ROOT/scripts/drill.sh" >>"$work/drill.log" 2>&1; }
restore() { "$ROOT/scripts/restore.sh" "$@" >>"$work/restore.log" 2>&1; }
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
for _ in $(seq 60); do
  [[ $(code "$(url /readyz)") == 200 ]] && break
  sleep 1
done
check "sign in after the restore" 303 "$(sign_in)"
dc --profile jobs run --rm --no-deps -T --entrypoint sh backup -c 'chmod -R u+w /backup/usb/labra/data &&
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
check "System page shows the failed drill" yes "$(grep -q 'usb: restore failed' <<<"$system" && echo yes)"
logs=$(dc logs --no-color web 2>&1)
check "logs hold no password" 0 "$(grep -c "$password" <<<"$logs")"
check "logs hold no database URL" 0 "$(grep -c 'postgresql+psycopg' <<<"$logs")"

echo "$((fails == 0 ? 1 : 0)) stack ($proxy on ${compose[*]}): $fails failed" |
  sed 's/^1 /PASS  /; s/^0 /FAIL  /'
((fails == 0))
