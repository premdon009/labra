#!/usr/bin/env bash
# Install the systemd timers that run Labra's scheduled jobs on the server (ADR-0013).
#
#   sudo scripts/install_timers.sh [--interval 15m|30m|2h|4h|24h] [--lab-hours 07:00-21:00]
#                                  [--tz Asia/Kolkata] [--user USER] [--dry-run]
#
# Backups run every --interval inside lab hours, plus a nightly run at 23:30 that also
# applies the retention. 24h means the nightly run only. Defaults come from
# LABRA_BACKUP_INTERVAL and LABRA_BACKUP_LAB_HOURS, then 15m and 07:00-21:00. --user is the
# account that runs the jobs (it must be able to run containers); default root. --dry-run
# prints the unit files instead of installing them. Run it again to change the schedule.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
interval=${LABRA_BACKUP_INTERVAL:-15m}
lab_hours=${LABRA_BACKUP_LAB_HOURS:-07:00-21:00}
tz=Asia/Kolkata
user=root
dry=false
unit_dir=${LABRA_UNIT_DIR:-/etc/systemd/system}
while (($#)); do
  case $1 in
    --interval) interval=$2; shift 2 ;;
    --lab-hours) lab_hours=$2; shift 2 ;;
    --tz) tz=$2; shift 2 ;;
    --user) user=$2; shift 2 ;;
    --dry-run) dry=true; shift ;;
    -h | --help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

die() { echo "$*" >&2; exit 2; }

minutes() {
  [[ $1 =~ ^([01][0-9]|2[0-3]):([0-5][0-9])$ ]] || die "not a time of day (HH:MM): $1"
  echo $((10#${BASH_REMATCH[1]} * 60 + 10#${BASH_REMATCH[2]}))
}

# OnCalendar lines for every run inside lab hours: one line per minute-of-the-hour, naming
# the hours it runs in, so 15m from 07:00 to 21:00 is four lines.
calendar() {
  local step start end t m keys
  case $interval in
    15m) step=15 ;; 30m) step=30 ;; 2h) step=120 ;; 4h) step=240 ;; 24h) return 0 ;;
    *) die "interval must be one of 15m, 30m, 2h, 4h, 24h (got $interval)" ;;
  esac
  [[ $lab_hours == *-* ]] || die "lab hours look like 07:00-21:00 (got $lab_hours)"
  start=$(minutes "${lab_hours%-*}")
  end=$(minutes "${lab_hours#*-}")
  ((start < end)) || die "lab hours must start before they end (got $lab_hours)"
  local -A hours=()
  for ((t = start; t <= end; t += step)); do
    m=$((t % 60))
    hours[$m]+=${hours[$m]:+,}$((t / 60))
  done
  keys=$(printf '%s\n' "${!hours[@]}" | sort -n)
  for m in $keys; do
    printf 'OnCalendar=*-*-* %s:%02d:00 %s\n' "${hours[$m]}" "$m" "$tz"
  done
}

service() {
  local what=$1 args=$2
  cat <<UNIT
[Unit]
Description=Labra $what (ADR-0013)
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
User=$user
ExecStart=$ROOT/scripts/backup.sh $args
UNIT
}

timer() {
  local what=$1 when=$2 persistent=$3
  cat <<UNIT
[Unit]
Description=Labra $what schedule

[Timer]
$when
AccuracySec=1min
Persistent=$persistent

[Install]
WantedBy=timers.target
UNIT
}

lab=$(calendar)
declare -A units=(
  [labra-backup-nightly.service]=$(service "nightly backup" "backup --prune --tag nightly")
  [labra-backup-nightly.timer]=$(timer "nightly backup" "OnCalendar=*-*-* 23:30:00 $tz" true)
)
if [[ -n $lab ]]; then
  units[labra-backup.service]=$(service "backup" "backup")
  units[labra-backup.timer]=$(timer "backup" "$lab" false)
fi

names=$(printf '%s\n' "${!units[@]}" | sort)
if [[ $dry == true ]]; then
  for name in $names; do printf '# %s\n%s\n\n' "$name" "${units[$name]}"; done
  exit 0
fi

for name in $names; do
  printf '%s\n' "${units[$name]}" >"$unit_dir/$name"
done
if [[ -z $lab && -f $unit_dir/labra-backup.timer ]]; then
  systemctl disable --now labra-backup.timer || true
  rm -f "$unit_dir/labra-backup.timer" "$unit_dir/labra-backup.service"
fi
systemctl daemon-reload
for name in $names; do
  [[ $name == *.timer ]] && systemctl enable --now "$name"
done
systemctl list-timers 'labra-*' --no-pager
