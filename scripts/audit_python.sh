#!/usr/bin/env bash
# Known-vulnerability check of the locked Python dependencies with pip-audit.
# Exit 0 clean, 1 vulnerable, 2 unchecked (offline or tool error).
set -uo pipefail
cd "$(dirname "$0")/.."

req=$(mktemp)
trap 'rm -f "$req"' EXIT
uv export --frozen --all-groups --all-extras --no-hashes --no-emit-project >"$req" || exit 2

out=$(uv run pip-audit --strict --disable-pip --no-deps -r "$req" 2>&1)
rc=$?
echo "$out"
((rc == 0)) && exit 0
if grep -qiE "connection|timed out|resolve|network|HTTPError" <<<"$out"; then
  echo "WARN: pip-audit couldn't reach the vulnerability database; unchecked." >&2
  exit 2
fi
exit 1
