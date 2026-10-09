"""Per-module coverage targets on top of the global `fail_under` (EC-H01).

    check_coverage.py coverage.json

Targets live in scripts/coverage_targets.toml as glob = percent. They only go up:
when a module beats its target by 5 points or more, the script suggests raising it.
"""

from __future__ import annotations

import fnmatch
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "scripts" / "coverage_targets.toml"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 1
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    targets: dict[str, float] = tomllib.loads(TARGETS.read_text(encoding="utf-8"))["targets"]

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    floor = pyproject["tool"]["coverage"]["report"]["fail_under"]
    total = report["totals"]["percent_covered"]
    problems = []
    if total < floor:
        problems.append(f"total coverage {total:.1f}% is below fail_under {floor}%")
    for path, data in sorted(report["files"].items()):
        rel = (
            Path(path).resolve().relative_to(ROOT).as_posix() if Path(path).is_absolute() else path
        )
        actual = data["summary"]["percent_covered"]
        for pattern, target in targets.items():
            if not fnmatch.fnmatch(rel, pattern):
                continue
            if actual < target:
                problems.append(f"{rel}: coverage {actual:.1f}% is below its target {target}%")
            elif actual >= target + 5:
                print(
                    f"note: {rel} is at {actual:.1f}%; consider raising '{pattern}' above {target}"
                )
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
