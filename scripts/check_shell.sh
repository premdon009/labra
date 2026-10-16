#!/usr/bin/env bash
# Lint shell scripts with shellcheck.
# Usage: check_shell.sh [FILE...]   (no files: scripts/*.sh and deploy/*/*.sh)
# Exit 0 clean, 1 findings, 2 unchecked (shellcheck missing).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

if ! command -v shellcheck >/dev/null 2>&1; then
  echo "WARN: shellcheck not installed; shell scripts unchecked." >&2
  exit 2
fi

if (($#)); then files=("$@"); else files=(scripts/*.sh deploy/*/*.sh); fi
shellcheck -x "${files[@]}" || exit 1
