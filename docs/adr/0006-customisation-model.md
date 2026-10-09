---
items: [W02]
status: accepted
date: 2026-10-09
---

# ADR-0006: Customisation through settings, data, templates and plugins — not forks

## Context
Every lab wants its own numbering, report layout, prices and routing of outsourced tests. Forking per lab would make upgrades impossible for a small team.

## Decision
Customisation happens in five layers, from most to least common (design §10):

1. **Settings:** typed rows in the `setting` table, branch value over lab value.
2. **Data:** catalogue, ranges, packages, prices, external labs, branches, users and roles.
3. **Templates:** report, bill, receipt, label and letterhead files, overridable in `/data/templates`.
4. **Custom fields:** an `extra` JSONB column now, an editor later.
5. **Plugins:** Python entry points (`labra.notifiers`, `labra.report_renderers`, `labra.result_importers`, `labra.routing_strategies`, `labra.accounting_exporters`, and the platform ports in [ADR-0008](0008-platform-ports.md)).

## Consequences
- An upgrade never overwrites a lab's settings, data or template overrides.
- Plugin interfaces are public API and change only with a deprecation notice (EC-G05).
