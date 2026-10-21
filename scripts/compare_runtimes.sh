#!/usr/bin/env bash
# Compare the container runtimes and image builders installed on this machine on the same Labra
# stack (ADR-0009, docs/dev/runtimes.md). For each runtime: does it work (stack_smoke.sh), how
# heavy is the engine, how fast does the stack start and serve, does it restart a crashed web
# process, and do logs carry the request ID end to end. For each builder: build time and the
# image checks.
#
#   scripts/compare_runtimes.sh [--runtimes "docker podman nerdctl incus"]
#                               [--builders "docker podman buildah kaniko"]
#                               [--duration 15] [--concurrency 8] [--out DIR]
#
# Every runtime runs the same image, built once and loaded from one archive. Missing tools are
# skipped. Incus runs the stack with Podman inside a Debian system container. Results go to
# DIR/results.md (default: a new temporary directory).
# Exit 0 every tested runtime passed, 1 any failed, 2 nothing to test.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
runtimes="docker podman nerdctl incus"
builders="docker podman buildah kaniko"
duration=15
concurrency=8
out=
while (($#)); do
  case $1 in
    --runtimes) runtimes=$2; shift 2 ;;
    --builders) builders=$2; shift 2 ;;
    --duration) duration=$2; shift 2 ;;
    --concurrency) concurrency=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    -h | --help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done
out=${out:-$(mktemp -d)}
mkdir -p "$out"
results=$out/results.jsonl
: >"$results"
bench() { python3 "$ROOT/scripts/runtime_bench.py" "$@"; }
record() { bench record "$results" "$@"; }
image=localhost/labra:dev
backup_image=localhost/labra-backup:dev
archive=$out/labra-image.tar
tested=0
failed=0

# The processes that make up each engine; Podman has no daemon, only a monitor per container.
declare -A ENGINE=(
  [docker]="dockerd containerd containerd-shim-runc-v2 docker-proxy"
  [podman]="conmon podman pasta pasta.avx2 slirp4netns rootlessport aardvark-dns catatonit"
  [nerdctl]="containerd containerd-shim-runc-v2 buildkitd rootlesskit slirp4netns"
)

reachable() { command -v "$1" >/dev/null 2>&1 && "$1" info >/dev/null 2>&1; }
secs() { local us=$((${EPOCHREALTIME/./} - $1)); echo "$((us / 1000000)).$((us / 100000 % 10))"; }

# Images the default stack needs, pulled before timing so start-up isn't a download test.
stack_images() {
  grep -ohE 'docker\.io/library/(postgres|caddy)[^ ]+' "$ROOT/compose.yaml"
}

pull() {
  local rt=$1 ref
  for ref in $(stack_images); do
    for _ in 1 2 3 4 5; do
      "$rt" pull -q "$ref" >/dev/null 2>&1 && break
      sleep 3
    done
  done
}

# The same images for every runtime, so they all run identical bytes. The backup image is in
# the archive too: nerdctl compose pulls a missing image instead of building it.
ensure_archive() {
  [[ -s $archive ]] && return 0
  local b
  for b in docker podman; do
    if reachable "$b"; then
      if ! "$b" image inspect "$image" >/dev/null 2>&1; then
        "$ROOT/scripts/build_image.sh" --builder "$b" --tag "$image" >"$out/build-$b.log" 2>&1 ||
          return 1
      fi
      if ! "$b" image inspect "$backup_image" >/dev/null 2>&1; then
        "$ROOT/scripts/build_image.sh" --builder "$b" --backup --tag "$backup_image" \
          >>"$out/build-$b.log" 2>&1 || return 1
      fi
      # Podman writes more than one image to an archive only when asked.
      if [[ $b == podman ]]; then
        podman save -m -o "$archive" "$image" "$backup_image" && return 0
      else
        docker save -o "$archive" "$image" "$backup_image" && return 0
      fi
    fi
  done
  return 1
}

measure_runtime() {
  local rt=$1
  local log=$out/smoke-$rt.log
  local procs
  read -ra procs <<<"${ENGINE[$rt]}"
  echo "== $rt"
  local version
  # Docker's client and engine versions can differ (Docker Desktop); the others are one binary.
  if [[ $rt == docker ]]; then
    version=$(docker version --format '{{.Server.Version}}' 2>/dev/null)
  else
    version=$("$rt" --version 2>/dev/null | awk '{print $3}')
  fi
  "$rt" load -i "$archive" >/dev/null 2>&1 || { echo "   could not load the image"; return 1; }
  pull "$rt"
  local idle
  idle=$(bench rss "${procs[@]}")

  "$ROOT/scripts/stack_smoke.sh" --compose "$rt compose" --image "$image" --keep >"$log" 2>&1
  local smoke=$?
  local state
  state=$(sed -n 's/^Kept: .*settings in //p' "$log")
  if [[ -z $state ]]; then
    record kind=runtime runtime="$rt" version="$version" smoke=FAIL
    sed 's/^/   /' "$log"
    return 1
  fi
  local compose_cmd project
  # shellcheck source=/dev/null
  source "$state"
  local -a dc
  read -ra dc <<<"$compose_cmd"
  dc+=(-p "$project" -f "$ROOT/compose.yaml")
  local ready
  ready=$(sed -n 's/^INFO  ready in \([0-9.]*\) s/\1/p' "$log")

  local label=com.docker.compose.project=$project
  stack_mem() {
    "$rt" stats --no-stream --format '{{.Name}}\t{{.MemUsage}}' 2>/dev/null |
      grep "$project" | bench stats
  }
  local stack busy
  sleep 5
  stack=$(stack_mem)
  busy=$(bench rss "${procs[@]}")

  local hz rz
  hz=$(bench load --port "$LABRA_HTTPS_PORT" --path /healthz --duration "$duration" \
    --concurrency "$concurrency")
  rz=$(bench load --port "$LABRA_HTTPS_PORT" --path /readyz --duration "$duration" \
    --concurrency "$concurrency")
  field() { python3 -c "import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])" "$1" "$2"; }
  local after
  after=$(stack_mem)

  # Trace: a request ID sent through the proxy comes back and appears in the runtime's logs.
  local rid=bench$RANDOM$RANDOM got trace=no
  got=$(curl -sk --resolve "$LABRA_SITE:$LABRA_HTTPS_PORT:127.0.0.1" -H "X-Request-ID: $rid" \
    -D - -o /dev/null "https://$LABRA_SITE:$LABRA_HTTPS_PORT/login" | tr -d '\r' |
    sed -n 's/^x-request-id: //Ip')
  sleep 2
  [[ $got == "$rid" ]] && "${dc[@]}" logs --no-color web 2>/dev/null | grep -q "\"request_id\": *\"$rid\"" &&
    trace=yes

  local web driver
  web=$("$rt" ps -q --filter "label=$label" --filter label=com.docker.compose.service=web | head -1)
  driver=$("$rt" inspect --format '{{.HostConfig.LogConfig.Type}}' "$web" 2>/dev/null)

  # Reliability: the web process exits; time until the runtime restarts it and it's ready.
  local began restart=none
  began=${EPOCHREALTIME/./}
  "${dc[@]}" exec -T web python -c "import os, signal; os.kill(1, signal.SIGTERM)" \
    >/dev/null 2>&1
  sleep 2
  for _ in $(seq 120); do
    if [[ $(curl -sk -o /dev/null -w '%{http_code}' \
      --resolve "$LABRA_SITE:$LABRA_HTTPS_PORT:127.0.0.1" \
      "https://$LABRA_SITE:$LABRA_HTTPS_PORT/readyz") == 200 ]]; then
      restart=$(secs "$began")
      break
    fi
    sleep 1
  done

  local size
  size=$("$rt" image inspect --format '{{.Size}}' "$image" 2>/dev/null | head -1)
  size=$((${size:-0} / 1048576))

  "${dc[@]}" down -v >/dev/null 2>&1
  rm -rf "$(dirname "$state")"

  record kind=runtime runtime="$rt" version="$version" \
    smoke="$( ((smoke == 0)) && echo PASS || echo FAIL)" ready_s="$ready" \
    engine_idle_mib="$idle" engine_busy_mib="$busy" stack_mib="$stack" \
    stack_after_load_mib="$after" \
    healthz_rps="$(field "$hz" rps)" healthz_p95_ms="$(field "$hz" p95_ms)" \
    readyz_rps="$(field "$rz" rps)" readyz_p95_ms="$(field "$rz" p95_ms)" \
    load_errors="$(($(field "$hz" errors) + $(field "$rz" errors)))" \
    restart_s="$restart" log_driver="${driver:-?}" trace="$trace" image_mib="$size"
  # A failure shows the whole run: what Compose and the containers printed come before the FAILs.
  if ((smoke == 0)); then
    grep -E '^PASS  stack' "$log" | sed 's/^/   /'
  else
    sed 's/^/   /' "$log"
  fi
  ((smoke == 0))
}

# Incus: a Debian system container with nesting, Podman inside, this same script inside that.
measure_incus() {
  echo "== incus"
  local name=labra-bench-$$
  incus_run "$name"
  local rc=$?
  incus delete -f "$name" >/dev/null 2>&1
  return "$rc"
}

incus_run() {
  local name=$1 src=$out/labra-src.tgz
  (cd "$ROOT" && git ls-files -co --exclude-standard -z |
    grep -zv '^secrets/\|^data/\|^\.env' | tar --null -T - -czf "$src") || return 1
  incus launch images:debian/13 "$name" -c security.nesting=true \
    -c security.syscalls.intercept.mknod=true -c security.syscalls.intercept.setxattr=true \
    >/dev/null || return 1
  for _ in $(seq 30); do
    incus exec "$name" -- systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded' &&
      break
    sleep 2
  done
  incus file push "$src" "$archive" "$name/root/" >/dev/null || return 1
  incus exec "$name" -- bash -c '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq && apt-get install -y -qq podman podman-compose docker-compose \
      curl openssl python3 git >/dev/null
    systemctl enable --now podman.socket
    mkdir -p /root/labra && tar -C /root/labra -xzf /root/labra-src.tgz
    cp /root/labra-image.tar /root/out-image.tar' >/dev/null 2>&1 ||
    { echo "   setup inside the container failed"; return 1; }
  incus exec "$name" -- bash -c "mkdir -p /root/out && mv /root/out-image.tar \
    /root/out/labra-image.tar && /root/labra/scripts/compare_runtimes.sh --runtimes podman \
    --builders '' --duration $duration --concurrency $concurrency --out /root/out" |
    sed 's/^/   /'
  local rc=${PIPESTATUS[0]}
  incus file pull "$name/root/out/results.jsonl" "$out/incus.jsonl" >/dev/null 2>&1
  local mem
  mem=$(incus info "$name" 2>/dev/null | sed -n 's/^ *Memory (current): *//p' | head -1)
  if [[ -s $out/incus.jsonl ]]; then
    python3 -c "
import json, sys
for line in open(sys.argv[1]):
    row = json.loads(line)
    row['runtime'] = 'incus → ' + row['runtime']
    row['engine_busy_mib'] = 'system container: ' + sys.argv[2]
    print(json.dumps(row))" "$out/incus.jsonl" "${mem:-?}" >>"$results"
  fi
  return "$rc"
}

for rt in $runtimes; do
  if [[ $rt == incus ]]; then
    if ! { command -v incus >/dev/null 2>&1 && incus info >/dev/null 2>&1; }; then
      echo "== incus: not installed or not reachable, skipped"
      continue
    fi
    ensure_archive || { echo "no image archive; build failed (see $out)"; exit 1; }
    tested=$((tested + 1))
    measure_incus || failed=$((failed + 1))
    continue
  fi
  if ! reachable "$rt"; then
    echo "== $rt: not installed or not reachable, skipped"
    continue
  fi
  ensure_archive || { echo "no image archive; build failed (see $out)"; exit 1; }
  tested=$((tested + 1))
  measure_runtime "$rt" || failed=$((failed + 1))
done

for b in $builders; do
  case $b in
    kaniko) reachable docker || reachable podman || continue ;;
    *) command -v "$b" >/dev/null 2>&1 || { echo "== build $b: not installed, skipped"; continue; } ;;
  esac
  echo "== build $b"
  tag=localhost/labra:bench-$b
  t=${EPOCHREALTIME/./}
  "$ROOT/scripts/build_image.sh" --builder "$b" --tag "$tag" >"$out/build-$b.log" 2>&1
  rc=$?
  first=$(secs "$t")
  t=${EPOCHREALTIME/./}
  "$ROOT/scripts/build_image.sh" --builder "$b" --tag "$tag" >>"$out/build-$b.log" 2>&1
  rebuild=$(secs "$t")
  check=FAIL
  case $b in
    docker | kaniko) crt=$(reachable docker && echo docker || echo podman) ;;
    *) crt=podman ;;
  esac
  ((rc == 0)) && "$ROOT/scripts/check_image.sh" "$tag" --runtime "$crt" >>"$out/build-$b.log" 2>&1 &&
    check=PASS
  [[ $check == FAIL ]] && failed=$((failed + 1))
  tested=$((tested + 1))
  record kind=builder builder="$b" first_s="$first" rebuild_s="$rebuild" check="$check"
  "$crt" rmi "$tag" >/dev/null 2>&1
done

rm -f "$archive" "$out/labra-src.tgz"
((tested == 0)) && { echo "UNCHECKED: no runtime or builder found."; exit 2; }
bench report "$results" >"$out/results.md"
echo
cat "$out/results.md"
echo "Results: $out/results.md (logs alongside)"
((failed == 0))
