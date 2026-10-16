#!/usr/bin/env bash
# Known-vulnerability check of uv.lock with osv-scanner.
# Exit 0 clean, 1 vulnerable, 2 unchecked (tool missing or offline).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

if ! command -v osv-scanner >/dev/null 2>&1; then
  echo "WARN: osv-scanner not installed; unchecked." >&2
  exit 2
fi

osv-scanner scan source --lockfile uv.lock
case $? in
  0) exit 0 ;;
  1) exit 1 ;;
  *) echo "WARN: osv-scanner couldn't complete; unchecked." >&2; exit 2 ;;
esac
