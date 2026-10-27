#!/usr/bin/env bash
# One row of the portability workflow (.github/workflows/portability.yml), the same on GitHub's
# runner and in a local lab (scripts/ci_portability.sh), so the two can't drift apart.
#
#   scripts/portability_job.sh [--install] ROW
#   scripts/portability_job.sh --rows
#
# ROW is one of docker-caddy, docker-nginx, podman, podman-nginx, podman-compose, nerdctl,
# incus, builders and outside-postgres. --install sets up what the row needs (packages, nerdctl)
# and needs sudo; without it the row runs. With LABRA_PREBUILT=1 a row uses the images in
# results/labra-image.tar instead of building them, except the builders row. The pinned images
# in results/deps are loaded first, so neither the stack nor a build pulls, except Kaniko's. Run
# it from the repository root; results go to ./results. outside-postgres uses
# LABRA_TEST_DATABASE_URL, or starts a throwaway PostgreSQL in Docker when that is unset. --rows
# lists the rows.
# Exit status: the row's; 2 when the row couldn't be checked here (the reason is printed).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
ROWS=(docker-caddy docker-nginx podman podman-nginx podman-compose nerdctl incus builders
  outside-postgres)
NERDCTL_VERSION=2.4.1
NERDCTL_SHA256_AMD64=ff018f11ac2f1354bf7b3aaaca6e0b52d81139c746a89134744d0b7be3a0e62f
# WeasyPrint's libraries, the same list as the Dockerfile's (tests/test_tooling.py checks).
declare -A PACKAGES=(
  [podman]="podman"
  [podman-nginx]="podman"
  [podman-compose]="podman podman-compose"
  [nerdctl]="uidmap"
  [incus]="incus"
  [builders]="podman buildah"
  [outside-postgres]="libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fontconfig"
)

install=false
[[ ${1:-} == --install ]] && { install=true; shift; }
case ${1:-} in
  -h | --help) sed -n '2,16p' "$0"; exit 0 ;;
  --rows) printf '%s\n' "${ROWS[@]}"; exit 0 ;;
esac
row=${1:-}
if [[ $# -ne 1 || " ${ROWS[*]} " != *" $row "* ]]; then
  echo "usage: $0 [--install] ROW, ROW one of: ${ROWS[*]}" >&2
  exit 1
fi

# Packages already there (a local lab has them) skip the slow apt-get update. The libraries
# come without the extras the image doesn't have either.
apt_install() {
  (($#)) || return 0
  local installed
  installed=$(dpkg-query -W -f '${db:Status-Abbrev}\n' "$@" 2>/dev/null | grep -c '^ii') || true
  ((installed == $#)) && return 0
  local extras=()
  [[ $row == outside-postgres ]] && extras=(--no-install-recommends)
  sudo apt-get update && sudo apt-get install -y "${extras[@]}" "$@"
}

install_nerdctl() {
  # A copy already in the current directory is used if its checksum matches.
  local tarball=nerdctl-full-$NERDCTL_VERSION-linux-amd64.tar.gz
  [[ -f $tarball ]] ||
    curl -fsSLO "https://github.com/containerd/nerdctl/releases/download/v$NERDCTL_VERSION/$tarball"
  echo "$NERDCTL_SHA256_AMD64  $tarball" | sha256sum -c
  sudo tar -C /usr/local -xzf "$tarball"
  # Ubuntu's AppArmor refuses unprivileged user namespaces to any program without a profile
  # that allows them; RootlessKit needs one.
  sudo tee /etc/apparmor.d/usr.local.bin.rootlesskit >/dev/null <<'EOT'
abi <abi/4.0>,
include <tunables/global>
/usr/local/bin/rootlesskit flags=(unconfined) {
  userns,
  include if exists <local/usr.local.bin.rootlesskit>
}
EOT
  sudo systemctl restart apparmor.service
}

if $install; then
  read -ra packages <<<"${PACKAGES[$row]:-}"
  apt_install "${packages[@]}"
  if [[ $row == nerdctl ]]; then install_nerdctl; fi
  if [[ $row == incus ]]; then sudo incus admin init --minimal; fi
  exit 0
fi

# The pinned images the stack runs, one archive each in results/deps with a list of
# "archive name pinned-ref" lines, and the app images built on another machine.
preload() {
  local engine=$1 file name ref
  if [[ -s results/deps/refs ]]; then
    while read -r file name ref; do
      # Podman and Buildah read a Dockerfile's syntax line as a comment, and can't pull the
      # frontend's archive: it holds an image for each platform.
      if [[ $engine == podman && $name == */docker/dockerfile:* ]]; then continue; fi
      if [[ $engine == podman ]]; then
        # Pulled from an OCI archive, the image keeps the digest Compose asks for.
        podman pull -q "oci-archive:results/deps/$file" >/dev/null
      else
        "$engine" load -i "results/deps/$file" >/dev/null
      fi
      # nerdctl finds an image by its exact name only.
      if [[ $engine == nerdctl ]]; then nerdctl tag "$name" "$ref"; fi
    done <results/deps/refs
  fi
  if [[ ${LABRA_PREBUILT:-} == 1 && -s results/labra-image.tar ]]; then
    "$engine" load -i results/labra-image.tar >/dev/null
  fi
  return 0
}

build() {
  if [[ ${LABRA_PREBUILT:-} == 1 ]] && "$1" image inspect localhost/labra:dev >/dev/null 2>&1; then
    echo "Using the prebuilt image."
    return 0
  fi
  "$ROOT/scripts/build_image.sh" --builder "$1"
}

compare() { "$ROOT/scripts/compare_runtimes.sh" "$@" --out results; }
smoke() { "$ROOT/scripts/stack_smoke.sh" "$@"; }

# A throwaway server at the digest the workflow's service runs, when none was given.
outside_postgres() {
  if [[ -z ${LABRA_TEST_DATABASE_URL:-} ]]; then
    local ref
    # Not local: the exit trap reads it after the function has returned.
    pg_name=labra-outside-pg-$$
    ref=$(grep -oE 'docker\.io/library/postgres:[^ ]+@sha256:[0-9a-f]+' \
      "$ROOT/.github/workflows/portability.yml" | head -1)
    preload docker
    docker run -d --rm --name "$pg_name" -p 5432:5432 -e POSTGRES_DB=labra_test \
      -e POSTGRES_HOST_AUTH_METHOD=trust "$ref" >/dev/null
    trap 'docker rm -f "$pg_name" >/dev/null 2>&1' EXIT
    for _ in $(seq 60); do
      docker exec "$pg_name" pg_isready -U postgres -d labra_test >/dev/null 2>&1 && break
      sleep 1
    done
    export LABRA_TEST_DATABASE_URL=postgresql://postgres@localhost:5432/labra_test
  fi
  # Tests marked serial hold a time budget, so they run afterwards, one at a time.
  local rc=0
  uv run pytest -q -rs -m "db and not e2e and not serial" -n auto || rc=1
  uv run pytest -q -rs -m "db and not e2e and serial" || rc=1
  return "$rc"
}

mkdir -p results
case $row in
  docker-caddy)
    preload docker
    compare --runtimes docker --builders ""
    ;;
  docker-nginx)
    preload docker
    build docker
    smoke --compose "docker compose" --proxy nginx
    ;;
  podman)
    systemctl --user enable --now podman.socket
    preload podman
    compare --runtimes podman --builders ""
    ;;
  podman-nginx)
    systemctl --user enable --now podman.socket
    preload podman
    build podman
    smoke --compose "podman compose" --proxy nginx
    ;;
  podman-compose)
    preload podman
    build podman
    smoke --compose podman-compose
    ;;
  nerdctl)
    if ! containerd-rootless-setuptool.sh install; then
      echo "UNCHECKED: rootless containerd won't start here."
      exit 2
    fi
    preload nerdctl
    compare --runtimes nerdctl --builders ""
    ;;
  incus)
    # Docker's firewall drops forwarded traffic from other bridges.
    sudo iptables -I DOCKER-USER -j ACCEPT
    sudo usermod -aG incus-admin "$USER"
    sg incus-admin -c "'$ROOT/scripts/compare_runtimes.sh' --runtimes incus --builders '' --out results"
    ;;
  builders)
    # Buildah builds from Podman's image store.
    preload docker
    preload podman
    compare --runtimes "" --builders "docker podman buildah kaniko"
    ;;
  outside-postgres)
    outside_postgres
    ;;
esac
