"""Measurements for scripts/compare_runtimes.sh: HTTP load through the proxy, container and
engine memory, and the results report. Standard library only, so it runs on any host.

    runtime_bench.py load --port 18443 --path /healthz --duration 15 --concurrency 8
    <runtime> stats --no-stream --format '{{.Name}}\t{{.MemUsage}}' | runtime_bench.py stats
    runtime_bench.py rss dockerd containerd …
    runtime_bench.py record FILE key=value …
    runtime_bench.py report FILE
"""

import argparse
import http.client
import json
import re
import socket
import ssl
import sys
import threading
import time
from pathlib import Path

UNITS = {"b": 1, "kb": 1e3, "kib": 1024, "mb": 1e6, "mib": 1024**2, "gb": 1e9, "gib": 1024**3}
MIB = 1024**2


class PinnedHTTPS(http.client.HTTPSConnection):
    """Connects to 127.0.0.1 but sends the site's name for SNI and Host, like `curl --resolve`."""

    def connect(self) -> None:
        raw = socket.create_connection(("127.0.0.1", self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)  # type: ignore[attr-defined]


def load(site: str, port: int, path: str, duration: float, concurrency: int) -> dict[str, float]:
    """Each worker keeps one connection open and sends requests back to back."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    latencies: list[float] = []
    errors = [0]
    lock = threading.Lock()
    stop = time.monotonic() + duration

    def worker() -> None:
        conn = PinnedHTTPS(site, port, timeout=10, context=context)
        mine: list[float] = []
        failed = 0
        while time.monotonic() < stop:
            began = time.perf_counter()
            try:
                conn.request("GET", path)
                resp = conn.getresponse()
                resp.read()
                if resp.status != 200:
                    failed += 1
                    continue
                mine.append(time.perf_counter() - began)
            except (OSError, http.client.HTTPException):
                failed += 1
                conn.close()
                conn = PinnedHTTPS(site, port, timeout=10, context=context)
        conn.close()
        with lock:
            latencies.extend(mine)
            errors[0] += failed

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    latencies.sort()

    def pct(p: float) -> float:
        return round(latencies[int(p * (len(latencies) - 1))] * 1000, 1) if latencies else 0.0

    return {
        "requests": len(latencies),
        "errors": errors[0],
        "rps": round(len(latencies) / duration, 1),
        "p50_ms": pct(0.50),
        "p95_ms": pct(0.95),
        "p99_ms": pct(0.99),
    }


def to_bytes(text: str) -> float:
    match = re.match(r"\s*([\d.]+)\s*([a-zA-Z]*)", text)
    if not match:
        return 0.0
    return float(match[1]) * UNITS.get(match[2].lower() or "b", 1)


def stats_total(lines: list[str]) -> float:
    """Sum the used half of `MemUsage` ("45.2MiB / 15.4GiB") over the stack's containers."""
    total = 0.0
    for line in lines:
        _, _, usage = line.partition("\t")
        total += to_bytes(usage.split("/")[0])
    return round(total / MIB, 1)


def rss_total(names: set[str]) -> float | None:
    """Resident memory of every process with one of these names, or None if there are none
    (the engine runs elsewhere, e.g. in Docker Desktop's VM)."""
    total, seen = 0, False
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            status = (proc / "status").read_text()
        except OSError:
            continue
        name = re.search(r"^Name:\s*(\S+)", status, re.M)
        rss = re.search(r"^VmRSS:\s*(\d+) kB", status, re.M)
        if name and name[1] in names:
            seen = True
            total += int(rss[1]) if rss else 0
    return round(total / 1024, 1) if seen else None


COLUMNS = [
    ("runtime", "Runtime"),
    ("version", "Version"),
    ("smoke", "Smoke test"),
    ("ready_s", "Ready (s)"),
    ("engine_idle_mib", "Engine idle (MiB)"),
    ("engine_busy_mib", "Engine, stack up (MiB)"),
    ("stack_mib", "Stack containers (MiB)"),
    ("stack_after_load_mib", "Stack after load (MiB)"),
    ("healthz_rps", "/healthz req/s"),
    ("healthz_p95_ms", "/healthz p95 (ms)"),
    ("readyz_rps", "/readyz req/s"),
    ("readyz_p95_ms", "/readyz p95 (ms)"),
    ("load_errors", "Errors under load"),
    ("restart_s", "Web restart (s)"),
    ("log_driver", "Log driver"),
    ("trace", "Request ID in logs"),
    ("image_mib", "Image (MiB)"),
]
BUILD_COLUMNS = [
    ("builder", "Builder"),
    ("first_s", "Build (s)"),
    ("rebuild_s", "Rebuild (s)"),
    ("check", "Image checks"),
]


def report(path: Path) -> str:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def table(cols: list[tuple[str, str]], kind: str) -> list[str]:
        mine = [r for r in rows if r.get("kind") == kind]
        if not mine:
            return []
        out = ["| " + " | ".join(h for _, h in cols) + " |", "|" + "---|" * len(cols)]
        out += ["| " + " | ".join(str(r.get(k, "")) for k, _ in cols) + " |" for r in mine]
        return [*out, ""]

    return "\n".join(table(COLUMNS, "runtime") + table(BUILD_COLUMNS, "builder"))


def main() -> int:
    parser = argparse.ArgumentParser(prog="runtime_bench.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("load")
    p.add_argument("--site", default="labra.lan")
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--path", default="/healthz")
    p.add_argument("--duration", type=float, default=15)
    p.add_argument("--concurrency", type=int, default=8)
    sub.add_parser("stats")
    p = sub.add_parser("rss")
    p.add_argument("names", nargs="+")
    p = sub.add_parser("record")
    p.add_argument("file", type=Path)
    p.add_argument("pairs", nargs="+")
    p = sub.add_parser("report")
    p.add_argument("file", type=Path)
    args = parser.parse_args()

    if args.cmd == "load":
        result = load(args.site, args.port, args.path, args.duration, args.concurrency)
        print(json.dumps(result))
    elif args.cmd == "stats":
        print(stats_total(sys.stdin.read().splitlines()))
    elif args.cmd == "rss":
        total = rss_total(set(args.names))
        print("n/a" if total is None else total)
    elif args.cmd == "record":
        row = dict(pair.split("=", 1) for pair in args.pairs)
        with args.file.open("a") as f:
            f.write(json.dumps(row) + "\n")
    else:
        print(report(args.file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
