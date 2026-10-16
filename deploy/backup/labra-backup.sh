#!/usr/bin/env bash
# Entry point of the Labra backup image (ADR-0013). One job per run, then exit.
#
#   labra-backup version     tool versions
set -euo pipefail

cmd=${1:-help}
case $cmd in
  version)
    pg_dump --version
    restic version
    rclone version | head -1
    ;;
  help | -h | --help)
    sed -n '2,/^set /p' "$0" | sed '$d; s/^# \{0,1\}//'
    ;;
  *)
    echo "unknown command: $cmd (try: labra-backup help)" >&2
    exit 2
    ;;
esac
