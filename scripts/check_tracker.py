"""Check docs/TRACKER.md and docs/ENTERPRISE_CHECKLIST.md, and keep their counts current.

    check_tracker.py              check; exit 1 on any problem (stale counts included)
    check_tracker.py --write      also rewrite the progress line and checklist counts
    check_tracker.py --tag v0.1.0rc1
                                  refuse a release tag while its gate has open items

Rules: IDs are unique; statuses are known; `done` rows are struck through with a date
and a PR or commit; `blocked`/`dropped` rows give a reason; every ID used in docs,
tests or branch commits exists; no ID that exists on master has been removed; every
commit on the branch carries an ID.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "docs" / "TRACKER.md"
CHECKLIST = ROOT / "docs" / "ENTERPRISE_CHECKLIST.md"

ID = r"(?:(?:W|M|X|LT|R)\d{2}(?:\.\d+)?|EC-[A-O]\d{2})"
ID_RE = re.compile(rf"(?<![\w-]){ID}(?![\w])")
ROW_RE = re.compile(rf"^\|\s*(~~)?({ID})(~~)?\s*\|")
CHECK_RE = re.compile(rf"^- \[([ x])\] (?:\*\*(P|1|L)\*\* )?`({ID})`")
COMMIT_RE = re.compile(rf"^[a-z]+(\([a-z0-9._-]+\))?!?: {ID}( |,|$)")
DONE_RE = re.compile(r"\d{4}-\d{2}-\d{2} · (#\d+|[0-9a-f]{7,40})")
STATUSES = {"todo", "doing", "done", "blocked", "dropped"}
PROGRESS_RE = re.compile(r"^\*\*Progress\*\* \(maintained by the script\): .*$", re.M)

# Where IDs may be referenced. Research notes are external material, so not scanned.
SCANNED = ["docs/**/*.md", "tests/**/*.py", "*.md", ".github/**/*.md"]
NOT_SCANNED = ("docs/research/",)


@dataclass
class Row:
    id: str
    title: str
    gate: str
    status: str
    done: str
    struck: bool
    line: int


@dataclass
class Check:
    id: str
    gate: str
    done: bool
    line: int


def parse_tracker(text: str) -> list[Row]:
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        m = ROW_RE.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and m.group(2).startswith("R"):
            # Rejected table: ID | Item | Reason
            cells = [cells[0], cells[1], "", "rejected", cells[2]]
        if len(cells) < 5:
            continue
        rows.append(
            Row(
                id=m.group(2),
                title=cells[1],
                gate=cells[2],
                status=cells[3],
                done=cells[4],
                struck=bool(m.group(1) and m.group(3)),
                line=n,
            )
        )
    return rows


def parse_checklist(text: str) -> list[Check]:
    checks = []
    for n, line in enumerate(text.splitlines(), 1):
        m = CHECK_RE.match(line)
        if m:
            # Items without a gate marker (section O) count towards gate 1.
            checks.append(
                Check(id=m.group(3), gate=m.group(2) or "1", done=m.group(1) == "x", line=n)
            )
    return checks


def check_rows(rows: list[Row], checks: list[Check]) -> list[str]:
    problems = []
    seen: dict[str, int] = {}
    for r in rows:
        if r.id in seen:
            problems.append(
                f"TRACKER.md:{r.line}: duplicate ID {r.id} (first at line {seen[r.id]})"
            )
        seen.setdefault(r.id, r.line)
        if r.status not in STATUSES and not (r.status == "rejected" and r.id.startswith("R")):
            problems.append(f"TRACKER.md:{r.line}: {r.id} has unknown status '{r.status}'")
        elif r.status == "done":
            if not r.struck or not r.title.startswith("~~"):
                problems.append(f"TRACKER.md:{r.line}: {r.id} is done; strike through ID and title")
            if not DONE_RE.search(r.done):
                problems.append(
                    f"TRACKER.md:{r.line}: {r.id} is done; give 'YYYY-MM-DD · #PR' or a commit"
                )
        elif r.status in {"blocked", "dropped"} and not r.done:
            problems.append(f"TRACKER.md:{r.line}: {r.id} is {r.status}; give the reason")
    for c in checks:
        if c.id in seen:
            problems.append(f"ENTERPRISE_CHECKLIST.md:{c.line}: duplicate ID {c.id}")
        seen.setdefault(c.id, c.line)
    return problems


def git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out.stdout


def base_ref() -> str | None:
    for ref in ("origin/master", "master"):
        if git("rev-parse", "--verify", "--quiet", ref) is not None:
            return ref
    return None


def check_references(known: set[str]) -> list[str]:
    problems = []
    for pattern in SCANNED:
        for path in sorted(ROOT.glob(pattern)):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(NOT_SCANNED) or not path.is_file():
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for ref in ID_RE.findall(line):
                    if ref not in known:
                        problems.append(f"{rel}:{n}: unknown ID {ref}")
    return sorted(set(problems))


def check_history(known: set[str]) -> list[str]:
    base = base_ref()
    if base is None:
        return []
    problems = []
    old = git("show", f"{base}:docs/TRACKER.md")
    if old:
        old_ids = {r.id for r in parse_tracker(old)}
        old_checklist = git("show", f"{base}:docs/ENTERPRISE_CHECKLIST.md") or ""
        old_ids |= {c.id for c in parse_checklist(old_checklist)}
        for gone in sorted(old_ids - known):
            problems.append(f"{gone} exists on {base} but was removed; strike it through instead")
    head = git("rev-parse", "--abbrev-ref", "HEAD") or ""
    if head.strip() not in {"master", "HEAD"}:
        for subject in (git("log", "--format=%s", f"{base}..HEAD") or "").splitlines():
            if subject.startswith(("Merge", "Revert")):
                continue
            if not COMMIT_RE.match(subject):
                problems.append(f"commit without a tracker ID: {subject}")
            for ref in ID_RE.findall(subject):
                if ref not in known:
                    problems.append(f"commit mentions unknown ID {ref}: {subject}")
    return problems


def ratio(items: list[tuple[bool, bool]]) -> str:
    """'done/total' over (counted, done) pairs, or an em dash when there are none."""
    counted = [d for c, d in items if c]
    return f"{sum(counted)}/{len(counted)}" if counted else "—"


def progress_line(rows: list[Row], checks: list[Check]) -> str:
    live = [r for r in rows if r.status != "dropped"]

    def part(pred) -> str:
        return ratio([(pred(r), r.status == "done") for r in live])

    work = part(lambda r: r.id.startswith("W") and r.gate == "P")
    minimal = part(lambda r: r.id.startswith("M") and r.gate == "P")
    p2 = part(lambda r: r.gate == "P2")
    gate_p = ratio([(c.gate == "P", c.done) for c in checks])
    gate_1 = ratio([(c.gate == "1", c.done) for c in checks])
    return (
        f"**Progress** (maintained by the script): Work {work} · Minimal {minimal} · "
        f"After pilot (P2) {p2} · Checklist gate P {gate_p} · gate 1 {gate_1}"
    )


SECTION_ROW_RE = re.compile(r"^\| ([A-O]) [^|]*\| EC-[A-O]\d{2}\u2013[A-O]\d{2} \|.*\|$")


def rewrite_counts(text: str, rows: list[Row], checks: list[Check]) -> str:
    text = PROGRESS_RE.sub(progress_line(rows, checks), text)
    out = []
    for line in text.splitlines():
        m = SECTION_ROW_RE.match(line)
        if m:
            letter = m.group(1)
            sec = [c for c in checks if c.id.startswith(f"EC-{letter}")]
            if sec:
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                nums = sorted(c.id for c in sec)
                cells[1] = f"{nums[0]}\u2013{nums[-1][3:]}"
                for i, gate in ((2, "P"), (3, "1"), (4, "L")):
                    cells[i] = ratio([(c.gate == gate, c.done) for c in sec])
                line = "| " + " | ".join(cells) + " |"
        out.append(line)
    return "\n".join(out) + "\n"


def parse_version(tag: str) -> tuple[tuple[int, int, int], bool]:
    m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)((?:a|b|rc)\d+)?", tag)
    if not m:
        raise SystemExit(f"not a release tag: {tag} (expected vX.Y.Z or vX.Y.ZrcN)")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))), bool(m.group(4))


PILOT = (0, 1, 0)


def check_tag(tag: str, rows: list[Row], checks: list[Check]) -> list[str]:
    version, _pre = parse_version(tag)
    if version < PILOT:
        return []
    gates = {"P"} if version == PILOT else {"P", "P2"}
    open_items = [
        r.id
        for r in rows
        if r.gate in gates and r.id[0] in "WM" and r.status not in {"done", "dropped"}
    ]
    open_items += [c.id for c in checks if c.gate in gates and not c.done]
    if not open_items:
        return []
    label = "pilot" if version == PILOT else "post-pilot"
    return [
        f"{tag} is a {label} tag; open gate {'/'.join(sorted(gates))} items: "
        + ", ".join(open_items)
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--write", action="store_true", help="rewrite progress and counts")
    ap.add_argument("--tag", help="check that this release tag may be created")
    args = ap.parse_args(argv)

    tracker_text = TRACKER.read_text(encoding="utf-8")
    rows = parse_tracker(tracker_text)
    checks = parse_checklist(CHECKLIST.read_text(encoding="utf-8"))
    known = {r.id for r in rows} | {c.id for c in checks}

    if args.tag:
        problems = check_tag(args.tag, rows, checks)
    else:
        problems = check_rows(rows, checks) + check_references(known) + check_history(known)
        fresh = rewrite_counts(tracker_text, rows, checks)
        if fresh != tracker_text:
            if args.write:
                TRACKER.write_text(fresh, encoding="utf-8")
                print("TRACKER.md: progress line and counts rewritten")
            else:
                problems.append("TRACKER.md: progress line or counts are stale; run with --write")

    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
