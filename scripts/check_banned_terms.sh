#!/usr/bin/env bash
# Reject terms that must never appear in the repository (AGENTS.md rule 2).
# The list lives outside the repo, one term per line, case-insensitive:
#   ${LABRA_BANNED_TERMS:-~/.config/labra/banned-terms.txt}
# Usage: check_banned_terms.sh [FILE...]   (no files: every file git doesn't ignore)
# Exit 0 clean, 1 found, 2 unchecked (no list on this machine).
set -uo pipefail
cd "$(dirname "$0")/.."

list=${LABRA_BANNED_TERMS:-$HOME/.config/labra/banned-terms.txt}
if [[ ! -s $list ]]; then
  echo "WARN: no banned-terms list at $list; check skipped." >&2
  exit 2
fi

if (($#)); then files=("$@"); else mapfile -t files < <(git ls-files --cached --others --exclude-standard); fi
patterns=$(grep -vE '^\s*(#|$)' "$list")
[[ -z $patterns ]] && exit 0

# Print file and line only, never the matched term, so CI logs don't repeat it.
hits=$(printf '%s\0' "${files[@]}" | xargs -0r grep -lIiF -f <(echo "$patterns") -- 2>/dev/null)
if [[ -n $hits ]]; then
  echo "Banned term found in:"
  echo "$hits"
  exit 1
fi
exit 0
