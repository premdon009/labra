---
items: [W02, M26]
status: accepted
date: 2026-10-09
---

# ADR-0007: Replaceable edges, stable core

## Context
Labra may have one maintainer. Accounting, inventory, messaging and other systems are better done by existing software, and the hosting must be able to move quickly if the laptop fails.

## Decision
- The core flow (visit → bill → sample → result → report) stays one application. Its internal modules are not made separately swappable.
- Each **edge** — accounting, inventory, notifications, report signing, file storage, backup target, hosting, data export, analysers — is reached through one small interface: the event outbox, a plugin entry point, the `FileStore` protocol, or config.
- **Build the integration point now; build an adapter only when a real system needs it.**
- `event_outbox` is written in the same transaction as the business change; readers track their own cursor; payloads carry IDs and amounts, not names or phones.

Details: design §17.1–§17.2.

## Consequences
- Several "later" features become "through an external app via M26" instead of being built in.
- [ADR-0008](0008-platform-ports.md) applies the same idea to platform services such as login, logs and metrics.
