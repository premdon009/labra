---
items: [W02]
status: accepted
date: 2026-10-09
---

# ADR-0001: Record architecture decisions

## Context
Labra may have only one maintainer for long stretches. Decisions that live only in someone's head, or in a long design document, get re-argued or quietly reversed.

## Decision
Every decision that is costly to reverse gets a short record in `docs/adr/NNNN-slug.md`: context, decision, consequences. Records are numbered in order and never renumbered. A changed decision gets a new record that says which one it supersedes, and the old one is marked `superseded`.

The design document [`docs/design/v1-plan.md`](../design/v1-plan.md) holds the detail; an ADR holds the decision and links to the detail.

## Consequences
- A new contributor can read why things are the way they are in a few minutes.
- `scripts/check_docs_linked.sh` fails if an ADR isn't linked from the ADR index.
