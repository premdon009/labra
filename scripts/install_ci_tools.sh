#!/usr/bin/env bash
# Put the gate's optional tools on a CI runner (Ubuntu, amd64), so `scripts/ci_local.sh --strict`
# checks secrets, vulnerabilities, shell scripts and the changelog instead of reporting WARN.
#
#   scripts/install_ci_tools.sh
#
# gitleaks and osv-scanner are release binaries pinned by version and SHA-256 (rows in
# docs/DEPENDENCIES.md); git-cliff comes from PyPI through uv, shellcheck from apt. A tool
# already on PATH is left alone. Needs sudo; downloads go to a temporary directory.
set -euo pipefail

GITLEAKS_VERSION=8.30.1
GITLEAKS_SHA256_AMD64=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
OSV_SCANNER_VERSION=2.7.0
OSV_SCANNER_SHA256_AMD64=160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b
GIT_CLIFF_PIN=2.14.2

[[ $(uname -m) == x86_64 ]] || { echo "only amd64 runners are pinned here" >&2; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"

if ! command -v gitleaks >/dev/null 2>&1; then
  tarball=gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz
  curl -fsSLO "https://github.com/gitleaks/gitleaks/releases/download/v$GITLEAKS_VERSION/$tarball"
  echo "$GITLEAKS_SHA256_AMD64  $tarball" | sha256sum -c
  tar -xzf "$tarball" gitleaks
  sudo install -m 0755 gitleaks /usr/local/bin/gitleaks
fi

if ! command -v osv-scanner >/dev/null 2>&1; then
  curl -fsSLo osv-scanner \
    "https://github.com/google/osv-scanner/releases/download/v$OSV_SCANNER_VERSION/osv-scanner_linux_amd64"
  echo "$OSV_SCANNER_SHA256_AMD64  osv-scanner" | sha256sum -c
  sudo install -m 0755 osv-scanner /usr/local/bin/osv-scanner
fi

if ! command -v git-cliff >/dev/null 2>&1; then
  uv tool install "git-cliff==$GIT_CLIFF_PIN"
  # uv's tool directory may not be on PATH; later steps of a GitHub job get it through GITHUB_PATH.
  bin=$(uv tool dir --bin)
  PATH=$bin:$PATH
  if [[ -n ${GITHUB_PATH:-} ]]; then echo "$bin" >>"$GITHUB_PATH"; fi
fi

if ! command -v shellcheck >/dev/null 2>&1; then
  sudo apt-get update && sudo apt-get install -y --no-install-recommends shellcheck
fi

gitleaks version
osv-scanner --version | head -1
git-cliff --version
shellcheck --version | sed -n 's/^version: //p'
