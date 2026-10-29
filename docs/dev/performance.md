---
items: [EC-F01, W32, W42]
---

# Performance budgets

Labra runs on one old laptop or mini PC at the main lab: 4 GB of memory, 2 CPU cores. With
three staff working at once it must stay within these budgets:

| What | Budget | Measured as |
|---|---|---|
| A screen on the LAN | under 1 s | 95th percentile of the screens below |
| Patient search | under 300 ms | 95th percentile of phone, number and name searches |
| A report PDF | under 3 s | 95th percentile of one released report's PDF |
| Memory | under 2 GB | the whole stack (database, app, proxy), at its highest |

Only a run on the real laptop counts. The checks below catch a change that makes Labra slower
long before that.

## Where each budget is checked

- **Every test run (`uv run pytest`):**
  - patient search over 50,000 patients, as an owner at the main lab and as front-desk staff at
    a branch: the median of five rounds per search under 300 ms
    (`tests/test_db_laptop_budget.py`);
  - a three-page report PDF within its render budget (`tests/test_db_pdf_snapshots.py`);
  - a full lab worklist in no more queries than a short one, and in time
    (`tests/test_db_lab_worklist.py`).

  These tests are marked `serial`. The gate runs the other tests in parallel first, then
  these on their own, so other workers can't use up their time budget.
- **Every `scripts/ci_local.sh --only stack` run:** with the containers held to the limits in
  `compose.yaml`, 2 CPUs and 4 GB between them (web 1 CPU and 2 GB, db 0.75 CPU and 1.5 GB,
  proxy 0.25 CPU and 512 MB), `scripts/stack_smoke.sh` checks those limits, adds 50,000
  synthetic patients, and runs
  `scripts/laptop_budget.py` with three users for 20 seconds. Its PDF budget shows as
  unchecked (WARN) there, because the smoke stack has no released report.
- **On the laptop, before the pilot:** the full run below.

50,000 patients is about two years of the volume the design assumes (three branches, about
2,000 to 2,700 reports a month), and two years is the retention NABL asks for.

## Running it on the laptop

Run it on a copy of the lab's stack with demo data, never on the live one. `fill` refuses a
database that has patients of its own.

1. Add the synthetic patients:

   ```bash
   python3 scripts/laptop_budget.py fill 50000 |
     docker compose exec -T db psql -U labra -d labra -v ON_ERROR_STOP=1
   ```

2. Release one report through the screens and copy its PDF address, `/reports/<id>/pdf`.
3. From a front-desk PC on the LAN (so the network is part of the measurement):

   ```bash
   LABRA_BUDGET_PASSWORD='…' python3 scripts/laptop_budget.py run \
     --site labra.lan --port 443 --username admin --pdf /reports/<id>/pdf \
     --duration 300 --compose 'ssh labra-server docker compose' --record budget.jsonl
   ```

   Each of the three users opens a screen, searches or downloads the PDF every half second
   (`--think`), for five minutes. `--page` replaces the default screens (repeat it), for a user
   whose role opens other screens. `--compose` is how to reach the stack's
   `docker compose stats` for memory; leave it out when running on the server itself.
4. It prints one line per budget and exits 1 when one is missed. Add the result to the table
   below.

## Results

| Date | Where | Pages p95 | Search p95 | PDF p95 | Memory peak | Notes |
|---|---|---|---|---|---|---|
| 2026-10-21 | Development PC (WSL 2, Docker Desktop), containers capped as above, 3 users, 20 s | 32–250 ms | 27–224 ms | not measured | 432–459 MiB | three runs; the spread is the shared PC, not Labra |
| 2026-10-21 | Development PC, in process (pytest), 50,000 patients | — | 35–50 ms (median per search) | — | — | owner and branch front desk |
| — | The laptop, before the pilot | to be filled in | | | | closes the laptop budgets item |

## How long the tests take

The gate's tests stage, on the development PC (WSL 2, 14 CPUs, Docker Desktop). The parallel
run starts a Postgres container per worker, and each test takes about three times the CPU it
takes alone, because every core is busy. So 8 workers make it about twice as fast, not eight
times. 4 workers took 311 s. GitHub's runner has 4 CPUs.

| Date | How | Tests | Time |
|---|---|---|---|
| 2026-10-23 | one at a time | 995 | 415 s and 519 s (two gate runs) |
| 2026-10-26 | one at a time (`LABRA_TEST_WORKERS=0`) | 998 | 550 s |
| 2026-10-26 | 8 workers, then the 4 `serial` tests alone | 995 + 4 | 223–260 s + 26–31 s; the stage 252–295 s over three gate runs |

## Backup size

The same smoke run backs up the 50,000 patients twice: the first backup added 20.45 MB across
both repositories (local disk and the USB copy), the second, with nothing changed but the run
log, 3.37 MB, because restic stores only the chunks of about 1 MB that changed. That is
within the 2 to 5 MB a run that [design §17.3](../design/v1-plan.md) estimated, and the
stored report PDFs (about 6 to 7 GB a year) stay the larger part of the backup.
