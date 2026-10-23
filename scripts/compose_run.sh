# shellcheck shell=bash
# Sourced by the scripts that run a one-off container of a Compose service, once they have set
# `compose` (the Compose command, as an array).
#
#   compose_run [OPTION...] SERVICE [ARG...]
#
# does what `"${compose[@]}" --profile jobs run --rm -T OPTION... SERVICE ARG...` does on Docker
# and Podman: the container's stdout and stderr come out apart, and its exit status is returned.
# nerdctl compose has no -T, and without a terminal it runs the container detached and exits 0
# whatever the container did. There the container is started detached and waited for, and then
# its output is printed and its exit status returned. Following its logs instead lost the last
# lines when the container ended.
#
# Nothing it starts gets the job lock's descriptor (fd 9): podman-compose's container monitors
# outlive the run and would keep holding the lock.
# shellcheck disable=SC2154 # compose is the caller's
compose_run() {
  if [[ ${compose[0]##*/} != nerdctl ]]; then
    "${compose[@]}" --profile jobs run --rm -T "$@" 9<&-
    return
  fi
  local name=labra-run-$$-$RANDOM status
  "${compose[@]}" --profile jobs run -d --name "$name" "$@" >/dev/null 9<&- || return
  status=$("${compose[0]}" wait "$name" 2>/dev/null 9<&-) ||
    status=$("${compose[0]}" inspect --format '{{.State.ExitCode}}' "$name" 9<&-) || status=1
  "${compose[0]}" logs "$name" 9<&- || true
  "${compose[0]}" rm -f "$name" >/dev/null 2>&1 9<&- || true
  return "$status"
}

# stop_web stops the web app and leaves the database running and ready, for a job that needs it
# with nothing writing meanwhile. nerdctl's compose stop also stops the services web depends on,
# the database among them, and its compose run doesn't start them again.
stop_web() {
  "${compose[@]}" stop web >/dev/null 2>&1 9<&- || true
  "${compose[@]}" up -d --no-build db >/dev/null 9<&-
  local _
  for _ in $(seq 60); do
    "${compose[@]}" exec -T db pg_isready -q >/dev/null 2>&1 9<&- && return
    sleep 1
  done
}
