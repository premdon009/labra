# Labra

Open-source software for small diagnostic lab chains in India: one main lab and a few collection centres. It covers patients, visits, billing, samples, in-house and outsourced tests, results and reports. It runs on a small server at the main lab (an old laptop or a mini PC) and can move to a cheap cloud server when needed.

> **Status:** early development (0.x). Not ready for real patient data. See [`docs/TRACKER.md`](docs/TRACKER.md) for what's done and what's next.

## What makes it different
- **Small-lab first:** one server, works over a patchy connection, printable A4 reports and bills.
- **Portable:** login, logs, metrics, file storage and messaging sit behind small interfaces. The built-in versions work out of the box; a lab that already runs an identity provider, log collector or object store points Labra at it through config ([design §17.6](docs/design/v1-plan.md)).
- **Your data stays yours:** full CSV and Parquet export, and an event outbox for accounting or other systems.

## Quick start (development)
```bash
uv sync
scripts/ci_local.sh          # every gate CI runs
uv run labra serve           # http://127.0.0.1:8000
```
Tests need Docker for a throwaway Postgres. The full stack is `docker compose up -d`. Details are in [`docs/dev/setup.md`](docs/dev/setup.md).

## Documentation
- User manual: `docs/manual/` (built with Zensical)
- Design: [`docs/design/v1-plan.md`](docs/design/v1-plan.md) and the decision records in [`docs/adr/`](docs/adr/)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AGENTS.md`](AGENTS.md)

## Licence
MIT, see [`LICENSE`](LICENSE). Third-party notices are in [`ATTRIBUTIONS.md`](ATTRIBUTIONS.md).
