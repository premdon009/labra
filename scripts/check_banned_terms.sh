#!/usr/bin/env bash
# Reject terms that must never appear in the repository (AGENTS.md rule 2).
# The list lives outside the repo, one term per line, case-insensitive:
#   ${LABRA_BANNED_TERMS:-~/.config/labra/banned-terms.txt}
# Usage: check_banned_terms.sh [FILE...]   (no files: every file git doesn't ignore)
# Exit 0 clean, 1 found, 2 unchecked (no list on this machine).
# LABRA_BANNED_TERMS_OPTIONAL=1 makes a missing list a skip (exit 0): GitHub CI writes the list
# from a secret, and a fork's pull request gets no secrets.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

list=${LABRA_BANNED_TERMS:-$HOME/.config/labra/banned-terms.txt}
if [[ ! -s $list ]]; then
  if [[ -n ${LABRA_BANNED_TERMS_OPTIONAL:-} ]]; then
    echo "No banned-terms list here (no secret for this run); check skipped."
    exit 0
  fi
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
