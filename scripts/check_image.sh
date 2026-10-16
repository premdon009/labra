#!/usr/bin/env bash
# Check a built Labra image behaves the same whichever builder made it.
#
#   scripts/check_image.sh REF [--runtime docker|podman|nerdctl] [--backup]
#
# --backup checks the one-shot backup image (ADR-0013) instead of the app image.
# Exit 0 pass, 1 fail, 2 unchecked (no runtime).
set -uo pipefail

ref=${1:?usage: check_image.sh REF [--runtime docker|podman|nerdctl] [--backup]}
shift
rt=
backup=false
while (($#)); do
  case $1 in
    --runtime) rt=$2; shift 2 ;;
    --backup) backup=true; shift ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done
if [[ -z $rt ]]; then
  for e in docker podman nerdctl; do
    if command -v "$e" >/dev/null 2>&1 && "$e" info >/dev/null 2>&1; then rt=$e; break; fi
  done
fi
if [[ -z $rt ]]; then
  echo "UNCHECKED: no container runtime reachable." >&2
  exit 2
fi

if ! "$rt" image inspect "$ref" >/dev/null 2>&1; then
  echo "FAIL  no image $ref in $rt; build it first (scripts/build_image.sh)"
  exit 1
fi

fails=0
check() {
  local what=$1 want=$2 got=$3
  if [[ $got == "$want" ]]; then
    echo "PASS  $what"
  else
    echo "FAIL  $what: wanted '$want', got '$got'"
    fails=$((fails + 1))
  fi
}
run() { "$rt" run --rm --entrypoint "$1" "$ref" "${@:2}" 2>&1 | tail -1; }

check "runs as uid 10001" 10001 "$(run id -u)"
if [[ $backup == true ]]; then
  want_pg=$(sed -n 's/^FROM .*postgres:\([0-9]*\)@.*/\1/p' "$(dirname "$0")/../deploy/backup/Dockerfile" |
    head -1)
  check "pg_dump matches the database's major version" "$want_pg" \
    "$(run pg_dump --version | sed 's/.* \([0-9]*\)\..*/\1/')"
  for tool in restic rclone; do
    want=$(sed -n "s/^ARG ${tool^^}_VERSION=//p" "$(dirname "$0")/../deploy/backup/Dockerfile")
    check "$tool $want" "$want" "$(run sh -c "$tool version | head -1" | grep -o '[0-9][0-9.]*' | head -1)"
  done
  check "help prints" yes "$("$rt" run --rm "$ref" help 2>&1 | grep -q labra-backup && echo yes || echo no)"
  check "cache folder is writable" ok "$(run sh -c 'touch /backup/cache/.probe && echo ok')"
  ((fails == 0))
  exit
fi
check "labra is installed" ok "$(run python -c "import labra.cli; print('ok')")"
check "changelog is packaged" ok \
  "$(run python -c "import importlib.resources as r; r.files('labra').joinpath('CHANGELOG.md').read_text(); print('ok')")"
check "PDF engine renders with the vendored fonts" ok \
  "$(run python -W error::DeprecationWarning -c "
import io, pypdf
from labra.printing.pdf import render_pdf
page = pypdf.PdfReader(io.BytesIO(render_pdf('<p>₹ रमेश</p>').pdf)).pages[0]
fonts = {str(f['/BaseFont']).split('+')[-1] for f in page['/Resources']['/Font'].values()}
print('ok' if '₹' in page.extract_text() and fonts == {'Labra-Sans', 'Labra-Devanagari'} else fonts)")"
check "files volume is writable" ok "$(run sh -c 'touch /data/files/.probe && echo ok')"
health=$("$rt" image inspect "$ref" 2>/dev/null | grep -c healthz)
check "health check kept" yes "$( ((health > 0)) && echo yes || echo no)"

((fails == 0))
