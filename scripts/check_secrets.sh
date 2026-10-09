#!/usr/bin/env bash
# Secret scan with gitleaks. Default: staged changes (pre-commit). --all: whole history.
# Exit 0 clean, 1 secrets found, 2 unchecked (gitleaks missing).
set -uo pipefail
cd "$(dirname "$0")/.."

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "WARN: gitleaks not installed; secrets unchecked." >&2
  exit 2
fi

if [[ ${1:-} == --all ]]; then
  gitleaks git --redact --no-banner .
else
  gitleaks git --staged --redact --no-banner .
fi
(($? == 0)) || exit 1
