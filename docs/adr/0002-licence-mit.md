---
items: [W02]
status: accepted
date: 2026-10-09
---

# ADR-0002: Licence stays MIT; copyleft projects are for ideas only

## Context
Labs, integrators and other developers should be able to run, change and fork Labra without legal advice. Several mature lab systems are GPL or AGPL.

## Decision
- Labra is MIT-licensed.
- GPL and AGPL projects are studied for workflows and screens only. No code, templates or text is copied from them.
- Runtime dependencies must be on the allowlist: MIT, BSD-2-Clause, BSD-3-Clause, 0BSD, Apache-2.0, PSF, ISC, MIT-CMU, PostgreSQL.
- Exceptions: **psycopg** (LGPL-3.0), imported unmodified as a library, which LGPL allows without affecting Labra's licence; **MPL-2.0** for test-only tools.
- `scripts/audit_deps.py --check` enforces the allowlist against [`docs/DEPENDENCIES.md`](../DEPENDENCIES.md).

## Consequences
- Some convenient libraries are off-limits; each rejected one is noted in the dependency register with the alternative used.
- Anyone can fork Labra if the maintainers stop (see the maintainer-handover practice in the design §18.3).
