#!/usr/bin/env bash
# Run the portability workflow's rows (.github/workflows/portability.yml) here before a push,
# each in its own lab: a privileged Ubuntu 26.04 container with systemd, Docker and Podman
# (deploy/ci-lab/Containerfile) that runs scripts/portability_job.sh as GitHub's runner does.
#
#   scripts/ci_portability.sh [ROW...] [--jobs N] [--build] [--keep] [--if-needed]
#
# Without ROW every row runs, N at a time (default 2). The app images are built here once and
# loaded into each lab with the pinned images the stack and the image builds use, so a lab pulls
# nothing but Kaniko's base images; with --build each row builds its own. The working tree is
# tested as it is, uncommitted changes included. --if-needed runs nothing when neither the branch
# (against master) nor the working tree changes a path the workflow watches. --keep leaves the
# labs running to look inside. incus needs a VM and runs on GitHub only. Logs and results:
# .ci/portability/<UTC time>/<row>/.
# Exit 0 every row passed or was skipped, 1 a row failed, 2 nothing ran (Docker unreachable).
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
mapfile -t ALL < <("$ROOT/scripts/portability_job.sh" --rows)
rows=()
jobs=2
build=false
keep=false
if_needed=false
while (($#)); do
  case $1 in
    --jobs) jobs=${2:-}; shift 2 ;;
    --build) build=true; shift ;;
    --keep) keep=true; shift ;;
    --if-needed) if_needed=true; shift ;;
    -h | --help) sed -n '2,16p' "$0"; exit 0 ;;
    -*) echo "unknown argument: $1" >&2; exit 1 ;;
    *)
      if [[ " ${ALL[*]} " != *" $1 "* ]]; then
        echo "unknown row: $1 (rows: ${ALL[*]})" >&2
        exit 1
      fi
      rows+=("$1")
      shift
      ;;
  esac
done
((${#rows[@]})) || rows=("${ALL[@]}")
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo "--jobs takes a number" >&2; exit 1; }

# The paths that start the workflow on a pull request, against what this branch changes.
watched() {
  sed -n '/^    paths:$/,/^[^ ]/s/^      - //p' "$ROOT/.github/workflows/portability.yml"
}
changed() {
  git -C "$ROOT" diff --name-only master...HEAD
  git -C "$ROOT" diff --name-only HEAD
  git -C "$ROOT" ls-files -o --exclude-standard
}
if $if_needed; then
  mapfile -t patterns < <(watched)
  hit=
  while read -r file; do
    for pattern in "${patterns[@]}"; do
      # shellcheck disable=SC2053 # the right side is a glob; ** and * both cross a /
      [[ $file == ${pattern//\*\*/*} ]] && { hit=$file; break 2; }
    done
  done < <(changed | sort -u)
  if [[ -z $hit ]]; then
    echo "Nothing the portability workflow watches has changed; no row to run."
    exit 0
  fi
  echo "$hit changed; running the portability rows."
fi

if ! docker info >/dev/null 2>&1; then
  echo "UNCHECKED: Docker isn't reachable." >&2
  exit 2
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
run=$ROOT/.ci/portability/$stamp
cache=$ROOT/.ci/portability/cache
label=org.labra.ci-portability=$stamp
mkdir -p "$run/images/deps" "$cache"

# shellcheck disable=SC2329 # called by the trap below
cleanup() {
  if ! $keep; then
    docker ps -aq --filter "label=$label" | xargs -r docker rm -f -v >/dev/null 2>&1
  fi
  rm -rf "$run/images"
}
trap cleanup EXIT
trap 'jobs -p | xargs -r kill 2>/dev/null; exit 130' INT TERM

# The lab image, rebuilt only when its Containerfile changes.
lab_image=labra-ci-lab:$(sha256sum "$ROOT/deploy/ci-lab/Containerfile" | cut -c1-12)
if ! docker image inspect "$lab_image" >/dev/null 2>&1; then
  echo "Building $lab_image; the first build takes a while."
  if ! docker build -f "$ROOT/deploy/ci-lab/Containerfile" -t "$lab_image" \
    "$ROOT/deploy/ci-lab" >"$run/lab-image.log" 2>&1; then
    echo "The lab image didn't build: $run/lab-image.log"
    exit 1
  fi
  docker images --format '{{.Repository}}:{{.Tag}}' labra-ci-lab | grep -vxF "$lab_image" |
    xargs -r docker rmi >/dev/null 2>&1
fi

# Each pinned image in an archive of its own, under a tag, as a lab's engines need them; the
# list says which archive holds which pinned reference (scripts/portability_job.sh). The tags
# stay: with Docker's containerd image store, removing the only tag of an image pulled by
# digest removes the image.
pinned() {
  grep -ohE '(docker\.io|ghcr\.io)/[^ "]+@sha256:[0-9a-f]{64}' "$ROOT/compose.yaml" \
    "$ROOT/deploy/nginx/compose.nginx.yaml" "$ROOT/scripts/build_image.sh" "$ROOT/Dockerfile" |
    grep -E '/(postgres|caddy|nginx|kaniko|python|uv|dockerfile):' | sort -u
}
echo "Saving the pinned images."
n=0
for ref in $(pinned); do
  n=$((n + 1))
  name=${ref%%@*}
  name=${name%:*}:labra-pinned
  if ! docker image inspect "$ref" >/dev/null 2>&1; then
    for _ in 1 2 3 4 5; do docker pull -q "$ref" >>"$run/images.log" 2>&1 && break; sleep 3; done
  fi
  if ! { docker tag "$ref" "$name" && docker save -o "$run/images/deps/$n.tar" "$name"; } \
    >>"$run/images.log" 2>&1; then
    echo "Couldn't save $ref: $run/images.log"
    exit 1
  fi
  echo "$n.tar $name $ref" >>"$run/images/deps/refs"
done

prebuilt=0
if ! $build; then
  echo "Building the app images."
  if ! { "$ROOT/scripts/build_image.sh" --builder docker &&
    "$ROOT/scripts/build_image.sh" --builder docker --backup &&
    docker save -o "$run/images/labra-image.tar" localhost/labra:dev localhost/labra-backup:dev; } \
    >"$run/build.log" 2>&1; then
    echo "The app images didn't build: $run/build.log"
    exit 1
  fi
  prebuilt=1
fi

# The working tree as it is: tracked and new files, without secrets or data.
(cd "$ROOT" && git ls-files -co --exclude-standard -z | grep -zv '^secrets/\|^data/\|^\.env' |
  tar --null --ignore-failed-read -T - -czf "$run/images/src.tgz" 2>/dev/null)

run_row() {
  local row=$1 dir=$run/$1 name=labra-ci-$stamp-$1 began=$SECONDS rc uid
  local home=/home/runner
  mkdir -p "$dir/results"
  finish() {
    echo "$1" >"$dir/result"
    echo "${2:-}" >"$dir/note"
    echo $((SECONDS - began)) >"$dir/seconds"
    echo "$row: $1${2:+ ($2)}"
    if ! $keep; then
      docker rm -f -v "$name" >/dev/null 2>&1
    fi
  }
  if [[ $row == incus ]]; then
    finish SKIP "needs a VM; runs on GitHub only"
    return
  fi
  # On Docker's default bridge the lab gets the host's name servers, as a runner has them; on a
  # network of its own only Docker's 127.0.0.11, and nerdctl then prints a notice on every run.
  if ! docker run -d --name "$name" --hostname "$row" --label "$label" \
    --privileged --cgroupns=private --tmpfs /run --tmpfs /run/lock \
    -v /var/lib/docker -v /var/lib/containerd -v /var/lib/containers -v "$home" \
    "$lab_image" >"$dir/lab.log" 2>&1; then
    finish FAIL "the lab didn't start; see lab.log"
    return
  fi
  uid=$(docker exec "$name" id -u runner)
  # The runner's own systemd, where Podman's socket and rootless containerd run.
  for _ in $(seq 60); do
    docker exec "$name" test -S "/run/user/$uid/bus" && break
    sleep 1
  done
  as_runner() {
    docker exec -i -u runner -w "$home/labra" -e USER=runner -e "XDG_RUNTIME_DIR=/run/user/$uid" \
      -e "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus" \
      -e "LABRA_PREBUILT=$prebuilt" "$name" "$@"
  }
  local images=(deps)
  ((prebuilt)) && images+=(labra-image.tar)
  if ! {
    docker exec -u runner "$name" mkdir -p "$home/labra/results" &&
      as_runner tar -xzf - <"$run/images/src.tgz" &&
      (cd "$run/images" && tar -cf - "${images[@]}") | as_runner tar -C results -xf - &&
      (cd "$cache" && tar -cf - --files-from <(compgen -G 'nerdctl-full-*.tar.gz')) |
      as_runner tar -xf -
  } >>"$dir/lab.log" 2>&1; then
    finish FAIL "couldn't copy the tree into the lab; see lab.log"
    return
  fi
  local step=install
  as_runner ./scripts/portability_job.sh --install "$row" >"$dir/install.log" 2>&1
  rc=$?
  if ((rc == 0)); then
    step=job
    as_runner timeout 45m ./scripts/portability_job.sh "$row" >"$dir/job.log" 2>&1
    rc=$?
  fi
  as_runner tar -C results --exclude=./deps --exclude='*.tar' -cf - . 2>/dev/null |
    tar -C "$dir/results" -xf - 2>/dev/null
  as_runner sh -c 'tar -cf - nerdctl-full-*.tar.gz 2>/dev/null' | tar -C "$cache" -xf - 2>/dev/null
  if ((rc == 0)); then
    finish PASS
  elif ((rc == 2)) && grep -q '^UNCHECKED: ' "$dir/job.log"; then
    finish SKIP "$(sed -n 's/^UNCHECKED: //p' "$dir/job.log" | tail -1)"
  elif [[ $step == job ]]; then
    finish FAIL "exit $rc; see job.log"
  else
    finish FAIL "exit $rc in --install; see install.log"
  fi
}

echo "Rows: ${rows[*]}, $jobs at a time. Logs: $run"
for row in "${rows[@]}"; do
  while (($(jobs -rp | wc -l) >= jobs)); do wait -n; done
  run_row "$row" &
done
wait

failed=0
{
  echo "| Row | Result | Time | Note |"
  echo "|---|---|---|---|"
  for row in "${rows[@]}"; do
    result=$(cat "$run/$row/result" 2>/dev/null || echo FAIL)
    [[ $result == FAIL ]] && failed=1
    secs=$(cat "$run/$row/seconds" 2>/dev/null || echo 0)
    printf '| %s | %s | %dm %02ds | %s |\n' "$row" "$result" $((secs / 60)) $((secs % 60)) \
      "$(cat "$run/$row/note" 2>/dev/null)"
  done
} >"$run/summary.md"
echo
cat "$run/summary.md"
echo "Logs: $run"
exit "$failed"
