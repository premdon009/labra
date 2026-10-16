#!/usr/bin/env bash
# Reject personal footprint in tracked or staged files: home directories, Windows
# user folders and default machine hostnames. Tests may use fake values on purpose.
# Usage: check_footprint.sh [FILE...]   (no files: every file git doesn't ignore)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

pattern='/home/[a-z_][a-z0-9_-]*/|/Users/[A-Za-z][A-Za-z0-9._-]*/|[A-Za-z]:\\Users\\[A-Za-z]|DESKTOP-[A-Z0-9]{7}|LAPTOP-[A-Z0-9]{7}'

if (($#)); then files=("$@"); else mapfile -t files < <(git ls-files --cached --others --exclude-standard); fi

hits=$(printf '%s\0' "${files[@]}" \
  | grep -zvE '^(tests/|scripts/check_footprint\.sh$|uv\.lock$)' \
  | xargs -0r grep -nIE "$pattern" -- 2>/dev/null)
if [[ -n $hits ]]; then
  echo "Personal footprint found (use ~/… or a placeholder):"
  echo "$hits"
  exit 1
fi
