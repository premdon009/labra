#!/usr/bin/env python3
"""Name the failed and flaky tests in a gate run's pytest output.

Usage: pytest_summary.py PYTEST_TXT RUN_DIR [--history TSV --run ID --commit SHA]

Reads output from `pytest -rfER --reruns 1`. A test is flaky when it failed, was re-run and
then passed; its ID goes to RUN_DIR/flaky.txt. Prints one line per failed or flaky test.
With --history, appends the run and each failed or flaky test to a tab-separated history
(columns: run, commit, test, outcome; test `*` with outcome `run` marks a run), and says how
often each flaky test was flaky in recent runs. scripts/flaky_report.py reads that history.
Exit 0 when every test passed first time, 1 when any test failed or was flaky.
"""

import argparse
import sys
from pathlib import Path

RERUN_SECTION = "rerun test summary info"
SHORT_SECTION = "short test summary info"
HISTORY_HEADER = "run\tcommit\ttest\toutcome\n"
RECENT_RUNS = 20


def _test_id(line: str) -> str:
    """`FAILED tests/x.py::test_a[p] - AssertionError` -> `tests/x.py::test_a[p]`.
    A parameter ID may itself hold " - ", so the message starts after its closing bracket."""
    rest = line.split(" ", 1)[1]
    end = rest.find(" - ")
    if "[" in rest[: max(end, 0)] and "]" not in rest[:end]:
        end = rest.find(" - ", rest.find("]"))
    return (rest if end < 0 else rest[:end]).strip()


def read(text: str) -> tuple[list[str], list[str]]:
    """Return (failed, flaky) test IDs, each in the order pytest printed them."""
    failed: list[str] = []
    flaky: list[str] = []
    section = ""
    rerun = ""
    for line in text.splitlines():
        if line.startswith("=") and line.endswith("="):
            section = line.strip("= ")
            continue
        if section == RERUN_SECTION:
            if line.startswith("RERUN "):
                rerun = _test_id(line)
            elif line.startswith("PASSED ") and _test_id(line) == rerun and rerun not in flaky:
                flaky.append(rerun)
        elif section == SHORT_SECTION and line.startswith(("FAILED ", "ERROR ")):
            test = _test_id(line)
            if test not in failed:
                failed.append(test)
    return failed, flaky


def record(history: Path, run: str, commit: str, failed: list[str], flaky: list[str]) -> None:
    """Append this run, and its failed and flaky tests, to the history file."""
    rows = [(run, commit, "*", "run")]
    rows += [(run, commit, test, "failed") for test in failed]
    rows += [(run, commit, test, "flaky") for test in flaky]
    new = not history.exists() or history.stat().st_size == 0
    with history.open("a") as out:
        if new:
            out.write(HISTORY_HEADER)
        out.writelines("\t".join(row) + "\n" for row in rows)


def run_order(run: str) -> tuple[str, int]:
    """Sort key for run IDs: start time, then the same-second suffix as a number (-10 after -9)."""
    stamp, _, n = run.partition("-")
    return stamp, int(n) if n.isdigit() else 0


def recent_flaky(history: Path, test: str, runs: int = RECENT_RUNS) -> tuple[int, int]:
    """How many of the last `runs` recorded runs had `test` flaky, and how many runs that is."""
    rows = [line.rstrip("\n").split("\t") for line in history.read_text().splitlines()[1:]]
    rows = [row for row in rows if len(row) == 4]
    recent = sorted({row[0] for row in rows if row[3] == "run"}, key=run_order)[-runs:]
    times = {row[0] for row in rows if row[2] == test and row[3] == "flaky"} & set(recent)
    return len(times), len(recent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Name the failed and flaky tests of a gate run.")
    parser.add_argument("pytest_txt", type=Path)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--history", type=Path, help="tab-separated history to append to")
    parser.add_argument("--run", default="", help="the run's ID, for the history")
    parser.add_argument("--commit", default="", help="the commit tested, for the history")
    args = parser.parse_args(argv)

    failed, flaky = read(args.pytest_txt.read_text(errors="replace"))
    if args.history:
        record(args.history, args.run or args.run_dir.name, args.commit or "unknown", failed, flaky)
    for test in failed:
        print(f"failed: {test}")
    for test in flaky:
        print(f"flaky (passed on re-run): {test}")
        if args.history:
            times, runs = recent_flaky(args.history, test)
            seen = "once" if times == 1 else f"{times} times"
            over = "this run" if runs == 1 else f"the last {runs} runs"
            print(f"  flaky {seen} in {over}; see scripts/flaky_report.py")
    if flaky:
        (args.run_dir / "flaky.txt").write_text("".join(f"{t}\n" for t in flaky))
    return 1 if failed or flaky else 0


if __name__ == "__main__":
    sys.exit(main())
