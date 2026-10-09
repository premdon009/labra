#!/usr/bin/env bash
# Labra stays on 0.x until the maintainers approve 1.0. Refuse a version >= 1.0.0
# in pyproject.toml unless LABRA_ALLOW_MAJOR=1 is set for that commit.
set -uo pipefail
cd "$(dirname "$0")/.."

version=$(grep -m1 -E '^version = ' pyproject.toml | cut -d'"' -f2)
major=${version%%.*}
if ((major >= 1)) && [[ ${LABRA_ALLOW_MAJOR:-} != 1 ]]; then
  echo "pyproject.toml version is $version. Labra stays on 0.x until 1.0 is approved;"
  echo "set LABRA_ALLOW_MAJOR=1 for the approved release commit."
  exit 1
fi
