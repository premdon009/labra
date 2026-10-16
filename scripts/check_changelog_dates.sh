#!/usr/bin/env bash
# Every released version heading in CHANGELOG.md must carry a date:
#   ## [x.y.z] - YYYY-MM-DD      (only "## [Unreleased]" may go without one)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

bad=$(grep -nE '^## ' CHANGELOG.md \
  | grep -vE '^[0-9]+:## \[Unreleased\]$' \
  | grep -vE '^[0-9]+:## \[[0-9]+\.[0-9]+\.[0-9]+((a|b|rc)[0-9]+)?\] - [0-9]{4}-[0-9]{2}-[0-9]{2}$')
if [[ -n $bad ]]; then
  echo "CHANGELOG.md headings must be '## [x.y.z] - YYYY-MM-DD' or '## [Unreleased]':"
  echo "$bad"
  exit 1
fi
