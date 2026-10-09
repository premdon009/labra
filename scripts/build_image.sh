#!/usr/bin/env bash
# Build the Labra image with any of the supported builders, so a move away from Docker is a
# change of command, not of Dockerfile (ADR-0009).
#
#   scripts/build_image.sh --builder docker|podman|buildah|kaniko [--tag REF] [--platform P]
#
# Kaniko runs as a container on whichever engine is present (docker or podman) and the result
# is loaded into that engine. Exit 0 built, 1 failed, 2 unchecked (builder not installed).
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# The maintained fork; the original Google project was archived in 2025.
KANIKO_IMAGE=ghcr.io/osscontainertools/kaniko:v1.28.5@sha256:738807f0e31daf07743f89260a95956dcc6ee4f62553f4f6344c990cabab8675

builder=docker
tag=localhost/labra:dev
platform=
while (($#)); do
  case $1 in
    --builder) builder=$2; shift 2 ;;
    --tag) tag=$2; shift 2 ;;
    --platform) platform=$2; shift 2 ;;
    -h | --help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "UNCHECKED: $1 is not installed." >&2
    exit 2
  fi
}

engine() {
  for e in docker podman; do
    if command -v "$e" >/dev/null 2>&1 && "$e" info >/dev/null 2>&1; then
      echo "$e"
      return
    fi
  done
}

case $builder in
  docker)
    need docker
    if [[ -n $platform ]]; then
      docker buildx build --platform "$platform" -t "$tag" "$ROOT"
    else
      docker build -t "$tag" "$ROOT"
    fi
    ;;
  podman | buildah)
    need "$builder"
    # --format docker keeps the HEALTHCHECK; the OCI format has no field for it.
    "$builder" build --format docker ${platform:+--platform "$platform"} -t "$tag" "$ROOT"
    ;;
  kaniko)
    rt=$(engine)
    if [[ -z $rt ]]; then
      echo "UNCHECKED: kaniko needs docker or podman to run in." >&2
      exit 2
    fi
    name=labra-kaniko-$$
    trap '"$rt" rm -f "$name" >/dev/null 2>&1' EXIT
    "$rt" run --name "$name" -v "$ROOT:/workspace:ro" "$KANIKO_IMAGE" \
      --context dir:///workspace --dockerfile Dockerfile \
      ${platform:+--custom-platform "$platform"} \
      --no-push --destination "$tag" --tar-path /tmp/labra.tar || exit 1
    # `cp -` wraps the file in a tar stream; unwrap it before loading.
    "$rt" cp "$name:/tmp/labra.tar" - | tar -xO | "$rt" load || exit 1
    ;;
  *)
    echo "unknown builder: $builder" >&2
    exit 1
    ;;
esac
