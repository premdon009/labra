#!/usr/bin/env python3
"""Which tests go wrong most often, from the gate's test history.

Usage: flaky_report.py [--history TSV] [--last N]

Reads the tab-separated history that scripts/ci_local.sh appends to after each tests stage
(${LABRA_CI_LOGS:-.ci/runs}/history.tsv; columns: run, commit, test, outcome). Prints one line
per test that was ever flaky or failed, the most flaky first. A report, not a gate: exit 0.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Tally:
    flaky: int = 0
    failed: int = 0
    last_run: str = ""
    last_commit: str = ""


def run_order(run: str) -> tuple[str, int]:
    """Sort key for run IDs: start time, then the same-second suffix as a number (-10 after -9)."""
    stamp, _, n = run.partition("-")
    return stamp, int(n) if n.isdigit() else 0


def tally(lines: list[str], last: int | None = None) -> tuple[list[str], dict[str, Tally]]:
    """Return the runs counted, oldest first, and a tally per test over those runs."""
    rows = [line.split("\t") for line in lines if line and not line.startswith("run\t")]
    rows = [row for row in rows if len(row) == 4]
    runs = sorted({run for run, _, _, outcome in rows if outcome == "run"}, key=run_order)
    if last is not None:
        runs = runs[-last:] if last > 0 else []
    counted = set(runs)
    tests: dict[str, Tally] = {}
    for run, commit, test, outcome in sorted(rows, key=lambda row: run_order(row[0])):
        if run not in counted or outcome not in ("flaky", "failed"):
            continue
        t = tests.setdefault(test, Tally())
        if outcome == "flaky":
            t.flaky += 1
        else:
            t.failed += 1
        t.last_run, t.last_commit = run, commit
    return runs, tests


def report(runs: list[str], tests: dict[str, Tally]) -> list[str]:
    if not runs:
        return ["no runs recorded"]
    counted = f"{len(runs)} run" if len(runs) == 1 else f"{len(runs)} runs"
    lines = [f"{counted}, {runs[0]} to {runs[-1]}"]
    if not tests:
        return [*lines, "no test was flaky or failed"]
    order = sorted(tests.items(), key=lambda kv: (-kv[1].flaky, -kv[1].failed, kv[0]))
    for test, t in order:
        lines.append(
            f"{t.flaky} flaky / {t.failed} failed / {counted}  {test}"
            f"  last: {t.last_run} {t.last_commit}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    default = Path(os.environ.get("LABRA_CI_LOGS", ".ci/runs")) / "history.tsv"
    parser = argparse.ArgumentParser(description="Which tests go wrong most often.")
    parser.add_argument("--history", type=Path, default=default)
    parser.add_argument("--last", type=int, help="count only the newest N runs")
    args = parser.parse_args(argv)

    lines = args.history.read_text().splitlines() if args.history.exists() else []
    for line in report(*tally(lines, args.last)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
