---
items: [W02]
status: accepted
date: 2026-10-09
---

# ADR-0004: Small server at the main lab, with layered offline fallbacks

## Context
The target lab has one main lab and a few collection centres, a modest budget, and internet that sometimes drops at the branches.

## Decision
- **Hosting:** an old laptop (SSD, Debian or Ubuntu Server, disk encryption) at the main lab runs the Docker Compose stack. A mini PC is an optional upgrade, and the same Compose file runs on a small cloud server (design §1a, §17).
- **Remote access:** branches reach the server through Cloudflare Tunnel and Access; no router ports are opened.
- **Offline, in layers:**
  1. Main lab works on the local network even with no internet.
  2. Branches fall back to a 4G hotspot, and then to a pre-numbered paper slip that is keyed in later.
  3. A branch offline counter (X25) is built only if outages turn out to be frequent.
- **Backups:** restic to an encrypted cloud target and a USB disk, with a monitored "backup ok" ping.

## Consequences
- No monthly cloud bill for the default install, but the lab owns the hardware risk; the cold-standby runbook (W10) covers it.
- IDs are app-generated, time-ordered UUIDs so a future offline counter can create rows safely.
