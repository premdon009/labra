#!/usr/bin/env bash
# Local gate. CI runs this same script, so green here means green there.
#
#   scripts/ci_local.sh                 all stages
#   scripts/ci_local.sh --only lint     one stage (repeatable)
#   scripts/ci_local.sh --only stack    build the image and smoke-test the stack (only on request)
#   scripts/ci_local.sh --fast          skip docs and audit
#   scripts/ci_local.sh --dry-run       list stages, run nothing
#   scripts/ci_local.sh --quiet         print only the summary and failures
#
# Each stage ends PASS, FAIL, WARN or SKIP. WARN means "could not be checked"
# (a tool or Docker is missing) and is never counted as a pass. Exit 1 on any FAIL.
#
# Every run keeps its logs in ${LABRA_CI_LOGS:-.ci/runs}/<UTC time>/: one <stage>.log per
# stage, the test output (pytest.txt), a JUnit XML report (junit.xml), coverage.json and
# summary.txt. The newest 10 runs are kept, and the newest failed run is never removed.
# Another CI system points LABRA_CI_LOGS at its artifact directory and collects it.
set -uo pipefail
cd "$(dirname "$0")/.."

STAGES=(preflight hygiene lint types imports services tests tracker manual docs audit stack)
only=() fast=0 dry=0 quiet=0
while (($#)); do
  case "$1" in
    --only) only+=("$2"); shift 2 ;;
    --fast) fast=1; shift ;;
    --dry-run) dry=1; shift ;;
    --quiet) quiet=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

LOGS_ROOT=${LABRA_CI_LOGS:-.ci/runs}
KEEP_RUNS=10
declare -A RESULT SECONDS_TAKEN

# A new directory per run, named by its UTC start time; a suffix keeps same-second runs apart.
new_run_dir() {
  local base n=1 dir
  base="$LOGS_ROOT/$(date -u +%Y%m%dT%H%M%SZ)"
  dir=$base
  mkdir -p "$LOGS_ROOT" || return 1
  until mkdir "$dir" 2>/dev/null; do n=$((n + 1)); dir="$base-$n"; done
  echo "$dir"
}

# Keep the newest $KEEP_RUNS run directories and the newest failed one (marked by a `failed`
# file). Anything else in $LOGS_ROOT is left alone.
prune_runs() {
  local runs=() keep_failed="" d i
  local stamp='[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z'
  for d in "$LOGS_ROOT"/$stamp "$LOGS_ROOT"/$stamp-*; do
    [[ -d $d ]] && runs+=("${d##*/}")
  done
  mapfile -t runs < <(printf '%s\n' "${runs[@]}" | LC_ALL=C sort -r)
  for i in "${runs[@]}"; do
    [[ -e $LOGS_ROOT/$i/failed ]] && { keep_failed=$i; break; }
  done
  for ((i = KEEP_RUNS; i < ${#runs[@]}; i++)); do
    [[ ${runs[i]} == "$keep_failed" ]] || rm -rf -- "${LOGS_ROOT:?}/${runs[i]}"
  done
}

wanted() {
  local s=$1
  if ((${#only[@]})); then
    for o in "${only[@]}"; do [[ $o == "$s" ]] && return 0; done
    return 1
  fi
  [[ $s == stack ]] && return 1
  ((fast)) && [[ $s == docs || $s == audit ]] && return 1
  return 0
}

# A stage function prints its own output and returns 0 PASS, 1 FAIL, 2 WARN.
stage_preflight() {
  uv lock --check || return 1
  scripts/check_tools.sh
}
stage_hygiene() {
  local worst=0 rc
  for check in scripts/check_footprint.sh scripts/check_changelog_dates.sh \
               scripts/check_version_gate.sh scripts/check_banned_terms.sh; do
    echo "-- $check"
    $check; rc=$?
    ((rc == 1)) && worst=1
    ((rc == 2 && worst == 0)) && worst=2
  done
  return $worst
}
# Third-party tools may exit 2 on errors, so their failures are mapped to 1 explicitly.
stage_lint() {
  uv run ruff check . && uv run ruff format --check . || return 1
}
stage_types() {
  uv run pyright || return 1
}
stage_imports() {
  uv run lint-imports || return 1
}
stage_services() {
  uv run python scripts/check_services.py --check
}
stage_tests() {
  local out="$RUN_DIR/pytest.txt"
  # Coverage floors are checked by check_coverage.py, so a skipped database run can
  # report them as unchecked instead of failed.
  uv run pytest -q -rfEs --junitxml="$RUN_DIR/junit.xml" \
    --cov --cov-fail-under=0 --cov-report=term \
    --cov-report=json:"$RUN_DIR/coverage.json" | tee "$out"
  local rc=${PIPESTATUS[0]}
  ((rc != 0)) && return 1
  if grep -q "SKIPPED.*no Postgres for tests" "$out"; then
    uv run python scripts/check_coverage.py "$RUN_DIR/coverage.json"
    echo "WARN: database tests were skipped (no container runtime and no LABRA_TEST_DATABASE_URL);" \
      "they and coverage are unchecked."
    return 2
  fi
  uv run python scripts/check_coverage.py "$RUN_DIR/coverage.json" || return 1
  if grep -q "SKIPPED.*no browser for e2e tests" "$out"; then
    echo "WARN: the browser test was skipped (no Chromium; run: uv run playwright install chromium);" \
      "keyboard shortcuts and the loading state are unchecked."
    return 2
  fi
}
stage_tracker() {
  uv run python scripts/check_tracker.py
}
stage_manual() {
  uv run python scripts/check_manual.py
}
stage_docs() {
  uv run python scripts/check_docs_linked.py || return 1
  uv run zensical build --clean --strict
}
stage_audit() {
  local worst=0 rc
  for check in "uv run python scripts/audit_deps.py --check" \
               scripts/audit_python.sh scripts/osv_scan.sh "scripts/check_secrets.sh --all"; do
    echo "-- $check"
    $check; rc=$?
    ((rc == 1)) && worst=1
    ((rc == 2 && worst == 0)) && worst=2
  done
  return $worst
}
stage_stack() {
  local rt rc
  for rt in docker podman; do
    "$rt" info >/dev/null 2>&1 || continue
    scripts/build_image.sh --builder "$rt"; rc=$?
    ((rc == 0)) || return $((rc == 2 ? 2 : 1))
    scripts/stack_smoke.sh --compose "$rt compose"
    return
  done
  echo "Neither docker nor podman is reachable; the stack is unchecked."
  return 2
}

if ((!dry)); then
  RUN_DIR=$(new_run_dir) || { echo "cannot create a run directory under $LOGS_ROOT" >&2; exit 2; }
fi

for s in "${STAGES[@]}"; do
  if ! wanted "$s"; then RESULT[$s]=SKIP; continue; fi
  if ((dry)); then echo "would run: $s"; RESULT[$s]=SKIP; continue; fi
  ((quiet)) || printf '\n\033[1m== %s\033[0m\n' "$s"
  start=$(date +%s)
  if ((quiet)); then
    "stage_$s" >"$RUN_DIR/$s.log" 2>&1; rc=$?
  else
    "stage_$s" 2>&1 | tee "$RUN_DIR/$s.log"; rc=${PIPESTATUS[0]}
  fi
  SECONDS_TAKEN[$s]=$(($(date +%s) - start))
  case $rc in
    0) RESULT[$s]=PASS ;;
    2) RESULT[$s]=WARN ;;
    *) RESULT[$s]=FAIL; ((quiet)) && cat "$RUN_DIR/$s.log" ;;
  esac
done

pass=0 fail=0 warn=0 skip=0
for s in "${STAGES[@]}"; do
  case ${RESULT[$s]} in PASS) ((pass++)) ;; FAIL) ((fail++)) ;; WARN) ((warn++)) ;; SKIP) ((skip++)) ;; esac
done

summary() {
  printf '%-10s %-6s %s\n' STAGE RESULT TIME
  for s in "${STAGES[@]}"; do
    t=${SECONDS_TAKEN[$s]:-}
    printf '%-10s %-6s %s\n' "$s" "${RESULT[$s]}" "${t:+${t}s}"
  done
  printf '\n%d passed, %d failed, %d unchecked (WARN), %d skipped\n' "$pass" "$fail" "$warn" "$skip"
  if [[ ${RESULT[tests]} == FAIL && -s $RUN_DIR/pytest.txt ]]; then
    echo
    echo "Failed tests:"
    grep -E '^(FAILED|ERROR) ' "$RUN_DIR/pytest.txt" || echo "  (none named; see tests.log)"
  fi
}

echo
if ((dry)); then summary; exit 0; fi
summary | tee "$RUN_DIR/summary.txt"
((fail)) && touch "$RUN_DIR/failed"
prune_runs
echo "Logs: $RUN_DIR"
((fail)) && exit 1
exit 0
