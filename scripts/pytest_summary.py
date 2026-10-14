#!/usr/bin/env python3
"""Name the failed and flaky tests in a gate run's pytest output.

Usage: pytest_summary.py PYTEST_TXT RUN_DIR

Reads output from `pytest -rfER --reruns 1`. A test is flaky when it failed, was re-run and
then passed; its ID goes to RUN_DIR/flaky.txt. Prints one line per failed or flaky test.
Exit 0 when every test passed first time, 1 when any test failed or was flaky.
"""

import argparse
import sys
from pathlib import Path

RERUN_SECTION = "rerun test summary info"
SHORT_SECTION = "short test summary info"


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Name the failed and flaky tests of a gate run.")
    parser.add_argument("pytest_txt", type=Path)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)

    failed, flaky = read(args.pytest_txt.read_text(errors="replace"))
    for test in failed:
        print(f"failed: {test}")
    for test in flaky:
        print(f"flaky (passed on re-run): {test}")
    if flaky:
        (args.run_dir / "flaky.txt").write_text("".join(f"{t}\n" for t in flaky))
    return 1 if failed or flaky else 0


if __name__ == "__main__":
    sys.exit(main())
