---
items: [W02]
status: accepted
date: 2026-10-09
---

# ADR-0003: Build fresh on FastAPI and Postgres

## Context
Existing open-source lab systems were surveyed ([`docs/research/oss-lims-landscape.md`](../research/oss-lims-landscape.md)). They're either heavy (Java stacks, many services), copyleft, or built around a hospital rather than a small Indian lab chain with outsourced tests and branch billing.

## Decision
One Python application, server-rendered:

- FastAPI, SQLAlchemy 2 (sync) and Alembic on PostgreSQL 18
- Jinja2 pages with HTMX, Alpine.js (CSP build) and Basecoat; no SPA build step
- WeasyPrint for A4 PDFs; ~~SQLAdmin for the admin screens~~ (superseded by [ADR-0010](0010-own-admin-screens.md): own HTMX screens)
- No Redis, Kafka or Kubernetes; everything fits on an old laptop

Modules live in `src/labra/<module>/` with `models.py`, `service.py`, `routes.py` and `templates/`. Routes stay thin and all rules live in `service.py`. Details: design §1d.

## Consequences
- One process and one database to back up, restore and move.
- Postgres features (row locks for numbering, triggers for the append-only audit log, JSONB) are used directly.
- Interactive screens need care to stay fast without client-side state; HTMX partial updates cover the result-entry grid.
