---
items: [W02, W15, W16, W20]
status: accepted
date: 2026-10-09
---

# ADR-0008: Platform services behind ports, with built-in defaults, and a database seam

## Context
Login, logging, metrics, error tracking, health checks, mail and file storage are needed by every install, but larger labs or groups often already run their own identity provider, log collector or monitoring. Labra must work alone out of the box and must not lock a lab into one vendor.

## Decision
- **Fixed core:** patients, visits, billing, samples, results, reports, the audit log, numbering and **authorisation** (roles, permissions, branch scoping).
- **Everything else is a platform service behind a port** (a small `Protocol` in `labra.core.ports` or a standard HTTP endpoint), with a built-in adapter as the default:

| Service | Built-in | External option |
|---|---|---|
| Identity | local password (argon2) | any OIDC provider |
| Logs | JSON lines on stdout | any stdout collector; OTLP (X35) |
| Metrics | `GET /metrics`, Prometheus format | any Prometheus-compatible scraper; OTLP (X35) |
| Errors | log entry + reference number | GlitchTip or Sentry by DSN |
| Health | `GET /healthz`, `GET /readyz` | any HTTP monitor |
| Heartbeats | log line | any ping URL |
| Mail | console (dev), SMTP | any SMTP relay |
| Files | local disk | S3-compatible storage |

- Adapters speak **open protocols** (OIDC, OTLP, Prometheus, SMTP, S3, HTTP pings, the Sentry protocol), so any compliant service works without new code.
- The adapter is chosen from `LABRA_*` settings at startup; an unknown name or a missing setting stops startup with a clear message.
- Domain modules import ports only. An import-linter contract fails CI if a domain module imports `labra.adapters` or a vendor library.
- Vendor libraries are optional extras (`labra[otel]`, `labra[s3]`, `labra[sentry]`).
- An external identity provider proves *who* the user is. *What* they may do stays in Labra: an OIDC login maps to an `app_user` by issuer and subject, and one local break-glass admin always remains.
- Nothing personal crosses a port: logs and error reports are scrubbed, and metric labels never carry patient, visit or user IDs.

Details: design §17.6.

### Database seam (added 2026-10-14)
- **Labra supports the PostgreSQL family:** any PostgreSQL 18 server, chosen by `LABRA_DATABASE_URL`, with psycopg 3 as the driver. Settings refuse any other URL scheme at startup, and `labra check-config` exits 2.
- **No second engine or driver yet.** Trigram search, advisory locks, arrays, JSONB, `DISTINCT ON`, partial indexes and the plpgsql guards in the migrations would each need a second version and a second test run, with no install asking for one. A second engine is X40 (MariaDB) and a second driver X44 (pg8000), built when an install needs them (ADR-0007).
- **Postgres-only code sits behind `labra.core.dialect`.** Domain code reaches those types, functions and locks only through its named helpers, so a second engine changes that module, the models' index options and a new migration chain, and nothing else. `scripts/check_services.py` fails when a `sqlalchemy.dialects` import or a Postgres-only call appears anywhere else outside the migrations. An import-linter contract can't forbid a subpackage of an external package, so the gate does it.

## Consequences
- A lab can adopt its own monitoring or SSO by setting environment variables.
- Each port needs a contract test suite that every adapter passes, and an in-memory fake for domain tests.
- External adapters are built only when an install needs one (ADR-0007).
- Every replaceable part, ports included, is listed with the setting that selects it and the test that proves the swap in the [service register](../dev/services.md), which also sizes the work a second database engine would need.
- A new Postgres-only query is added to `labra.core.dialect` as a named helper with a test in `tests/test_db_dialect.py`.
