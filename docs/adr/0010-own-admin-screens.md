---
items: [M14]
status: accepted
date: 2026-10-12
---

# ADR-0010: Own HTMX admin screens instead of SQLAdmin

Supersedes the "SQLAdmin for the admin screens" line of [ADR-0003](0003-fastapi-postgres.md).

## Context
ADR-0003 planned SQLAdmin for the admin screens, to get them for free. By the time the catalog
screens were due, the branch, staff and settings screens were already plain Jinja and HTMX
screens, and SQLAdmin turned out to bypass rules every other screen keeps:

- the strict content security policy (SQLAdmin ships its own scripts and inline handlers);
- the manual-page registry: every screen names its manual page and `scripts/check_manual.py`
  fails without it;
- the stale-edit check that names who changed a record, and the before/after audit entries,
  which live in the service layer that SQLAdmin writes around;
- branch scoping and permissions, which SQLAdmin would need a second copy of.

It would also be one more dependency to watch, with no row in `docs/DEPENDENCIES.md`.

## Decision
Admin screens are built like every other screen: a thin `routes.py` over the module's
`service.py`, Jinja templates with Basecoat, HTMX where a screen needs partial updates.
SQLAdmin is not used.

## Consequences
- One look, one permission model and one audit trail for every screen.
- Every admin screen has a manual page and route tests, like the rest.
- Each new admin table costs a list and a form template; the catalog and prices took about
  a dozen. Bulk edits (for example a price CSV import) are built as screens when needed.
