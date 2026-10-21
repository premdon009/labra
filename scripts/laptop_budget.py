"""The laptop budgets: three staff working at once on the main-lab server, measured through the
proxy. Standard library only, so it runs on the laptop itself.

    laptop_budget.py fill 50000 |
      docker compose exec -T db psql -U labra -d labra -v ON_ERROR_STOP=1
    LABRA_BUDGET_PASSWORD=… laptop_budget.py run --username admin --pdf /reports/<id>/pdf

`fill` writes SQL that adds synthetic patients (made-up names, PERF- numbers) to a scratch stack,
so search runs against about two years of a lab's registrations; it refuses a database that has
patients of its own. `run` signs each user in, requests screens, searches and the report PDF
back to back, samples the stack's memory meanwhile, and exits 1 when a budget is missed.
"""

import argparse
import http.client
import json
import os
import re
import shlex
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from runtime_bench import PinnedHTTPS, stats_total

# The budgets (ms, and MiB for the whole stack), from the enterprise checklist.
BUDGETS = {"page_p95_ms": 1000, "search_p95_ms": 300, "pdf_p95_ms": 3000, "memory_mib": 2048}
# Screens an administrator can open; --page names others for a user with another role.
PAGES = ["/", "/frontdesk/visits/new", "/frontdesk/patients", "/admin/system", "/admin/users"]
# A phone's first digits, a patient number, and parts of names, as staff type them.
SEARCHES = ["98", "PERF-001234", "kara", "misa vilo", "deka", "tinu"]
SYLLABLES = ["ka", "ra", "mi", "sa", "vi", "lo", "de", "nu", "pa", "ti", "ye", "go"]
CSRF = re.compile(r'name="csrf_token" value="([^"]+)"')


def fill_sql(patients: int) -> str:
    """Synthetic patients for a scratch stack: names built from syllables, phones that start
    with 9 and numbers PERF-000001 onwards. Run twice, it adds nothing the second time."""
    syllables = "array[" + ", ".join(f"'{s}'" for s in SYLLABLES) + "]"
    n = len(SYLLABLES)
    # Only whole numbers and the fixed syllables go into it.
    return f"""\
do $$ begin
  if exists (select 1 from patient where patient_no not like 'PERF-%') then
    raise exception 'this database has patients of its own; fill only a scratch stack';
  end if;
end $$;
insert into patient (
  id, patient_no, registered_branch_id, title, full_name, sex, dob, dob_is_estimated,
  phone, alt_phone, email, address, city, pincode, created_at, updated_at, row_version
)
select
  gen_random_uuid(), 'PERF-' || lpad(i::text, 6, '0'),
  (select id from branch order by created_at limit 1), '',
  initcap(s[1 + i % {n}] || s[1 + (i / {n}) % {n}] || s[1 + (i / {n**2}) % {n}])
    || ' ' || initcap(s[1 + (i / 7) % {n}] || s[1 + (i / {n**3}) % {n}] || 'n'),
  (array['M', 'F'])[1 + i % 2], date '1950-01-01' + (i * 37) % 25000, false,
  '9' || lpad(((i::bigint * 7919) % 1000000000)::text, 9, '0'), '', '', '', '', '',
  now() - make_interval(mins => i), now(), 1
from generate_series(1, {patients}) as i, (select {syllables} as s) as names
on conflict (patient_no) do nothing;
analyze patient;
"""  # noqa: S608


class User:
    """One member of staff: their own connection and session cookie."""

    def __init__(self, site: str, port: int) -> None:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self.connect = lambda: PinnedHTTPS(site, port, timeout=30, context=context)
        self.conn = self.connect()
        self.cookies: dict[str, str] = {}

    def request(self, method: str, path: str, body: str | None = None) -> tuple[int, bytes]:
        headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items())}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            self.conn.request(method, path, body, headers)
            resp = self.conn.getresponse()
        except (OSError, http.client.HTTPException):
            self.conn.close()
            self.conn = self.connect()
            self.conn.request(method, path, body, headers)
            resp = self.conn.getresponse()
        data = resp.read()
        for header in resp.headers.get_all("Set-Cookie") or []:
            name, _, rest = header.partition("=")
            self.cookies[name.strip()] = rest.split(";", 1)[0]
        return resp.status, data

    def sign_in(self, username: str, password: str) -> None:
        _, page = self.request("GET", "/login")
        token = CSRF.search(page.decode())
        if token is None:
            raise SystemExit("no sign-in form at /login")
        form = urllib.parse.urlencode(
            {"username": username, "password": password, "csrf_token": token[1]}
        )
        status, _ = self.request("POST", "/login", form)
        if status != 303:
            raise SystemExit(f"sign-in as {username} failed ({status})")


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[int(p * (len(ordered) - 1))] * 1000, 1)


def sample_memory(compose: list[str], stop: threading.Event, peak: list[float]) -> None:
    """The stack's memory every two seconds until stopped; the highest total is kept."""
    while not stop.is_set():
        out = subprocess.run(
            [*compose, "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            peak[0] = max(peak[0], stats_total(out.stdout.splitlines()))
        stop.wait(2)


def run(args: argparse.Namespace, password: str) -> dict[str, Any]:
    work: list[tuple[str, str]] = [("page", p) for p in args.page or PAGES]
    work += [("search", f"/frontdesk/patients?q={urllib.parse.quote(q)}") for q in SEARCHES]
    if args.pdf:
        work.append(("pdf", args.pdf))
    timings: dict[str, list[float]] = {"page": [], "search": [], "pdf": []}
    errors: dict[str, int] = {}
    lock = threading.Lock()
    users = [User(args.site, args.port) for _ in range(args.users)]
    for user in users:
        user.sign_in(args.username, password)
    stop_at = time.monotonic() + args.duration

    def work_as(user: User, offset: int) -> None:
        mine: dict[str, list[float]] = {k: [] for k in timings}
        failed: dict[str, int] = {}
        i = offset
        while time.monotonic() < stop_at:
            kind, path = work[i % len(work)]
            i += 1
            began = time.perf_counter()
            status, _ = user.request("GET", path)
            took = time.perf_counter() - began
            if status == 200:
                mine[kind].append(took)
            else:
                failed[f"{path} {status}"] = failed.get(f"{path} {status}", 0) + 1
            time.sleep(args.think)
        with lock:
            for kind, values in mine.items():
                timings[kind].extend(values)
            for key, count in failed.items():
                errors[key] = errors.get(key, 0) + count

    stop, peak = threading.Event(), [0.0]
    sampler = threading.Thread(target=sample_memory, args=(shlex.split(args.compose), stop, peak))
    sampler.start()
    threads = [
        threading.Thread(target=work_as, args=(u, n * len(work) // len(users)))
        for n, u in enumerate(users)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    sampler.join()
    return {
        "users": args.users,
        "requests": sum(len(v) for v in timings.values()),
        "errors": sum(errors.values()),
        "failed": errors,
        "page_p95_ms": percentile(timings["page"], 0.95),
        "search_p95_ms": percentile(timings["search"], 0.95),
        "pdf_p95_ms": percentile(timings["pdf"], 0.95),
        "memory_mib": peak[0],
    }


def verdict(result: dict[str, Any], measured: Callable[[str], bool]) -> list[str]:
    """One line per budget; a budget that wasn't measured is unchecked, never a pass."""
    lines = []
    for key, limit in BUDGETS.items():
        value = result[key]
        if not measured(key):
            lines.append(f"WARN  {key}: not measured")
        elif value < limit:
            lines.append(f"PASS  {key}: {value} (budget {limit})")
        else:
            lines.append(f"FAIL  {key}: {value} (budget {limit})")
    if result["errors"]:
        failed = ", ".join(f"{k}: {n}" for k, n in result["failed"].items())
        lines.append(f"FAIL  errors: {result['errors']} requests didn't return 200: {failed}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(prog="laptop_budget.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fill", help="SQL that adds synthetic patients to a scratch stack")
    p.add_argument("patients", type=int)
    p = sub.add_parser("run", help="three users through the proxy, against the budgets")
    p.add_argument("--site", default="labra.lan")
    p.add_argument("--port", type=int, default=443)
    p.add_argument("--username", required=True)
    p.add_argument("--users", type=int, default=3)
    p.add_argument("--duration", type=float, default=60)
    p.add_argument("--think", type=float, default=0.5, help="seconds between a user's requests")
    p.add_argument("--page", action="append", help="a screen to open (repeat; default: PAGES)")
    p.add_argument("--pdf", help="a released report's PDF address, e.g. /reports/<id>/pdf")
    p.add_argument("--compose", default="docker compose", help="the stack's compose command")
    p.add_argument("--record", type=Path, help="append the result to this JSON-lines file")
    args = parser.parse_args()

    if args.cmd == "fill":
        print(fill_sql(args.patients), end="")
        return 0
    password = os.environ.get("LABRA_BUDGET_PASSWORD")
    if not password:
        print("Set LABRA_BUDGET_PASSWORD to the user's password.", file=sys.stderr)
        return 2
    result = run(args, password)
    print(json.dumps(result))
    lines = verdict(
        result,
        lambda key: (
            (key != "pdf_p95_ms" or bool(args.pdf))
            and (key != "memory_mib" or result["memory_mib"] > 0)
        ),
    )
    print("\n".join(lines))
    if args.record:
        with args.record.open("a") as f:
            f.write(json.dumps(result) + "\n")
    return 1 if any(line.startswith("FAIL") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
