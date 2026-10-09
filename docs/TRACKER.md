# Labra tracker
Every feature, work item and checklist item has a **permanent ID**. This table is the one place to see what's left. It's committed to the repo as `docs/TRACKER.md` and updated in the same PR that finishes an item.

**ID scheme:**
| Prefix | Meaning | Defined in |
|---|---|---|
| `W01`… | Project / infrastructure work (repo, CI, install, pilot) | this tracker |
| `M01`… | Minimal-version features | §1a feature table |
| `X01`… | Next expansion (0.x after the pilot) | §1b, §1c |
| `LT01`… | Later (1.x / 2.x) | §1b, §1c, §2 |
| `R01`… | Rejected, kept with the reason so it isn't proposed again without reading why | §1b, §1c |
| `EC-A01`… | Enterprise checklist items (letter = checklist section) | §14a |
| `M17.1` | Sub-item (dotted), used when one item is split | wherever split |

**Rules:**
- IDs are never renumbered or reused. A dropped item stays in the table, struck through, with status `dropped` and the reason.
- A new idea takes the next free number in its prefix. It's added here in the same change that adds it to the docs.
- **Status** goes `todo` → `doing` → `done`, or `blocked` / `dropped` (each with a reason). On `done`, strike through the ID and title, then fill in the date and PR. Example: `| ~~M08~~ | ~~Barcode sample labels~~ | P | done | 2026-11-02 · #14 |`.
- Branches, commits and PRs carry the ID, e.g. `feat/m07-billing` and `feat(billing): M07 part payment and dues`. Then `git log --grep M07` shows an item's whole history.
- Manual pages list the IDs they document (`features: [M07]` front matter). That keeps the manual's features overview (§13a) linked to this table.
- **Each item is ticked in one place only.** Features are ticked here. Checklist items are ticked in `docs/ENTERPRISE_CHECKLIST.md`; this table only shows their counts per section, filled in by a script, so the two can't disagree.

**Tracker tooling (adopted by the owner 2026-10-08; built as W08.1, mirror deferred as X34):**
1. **Status column plus strike-through,** not strike-through alone. The strike makes done items stand out; the status, date and PR make each one auditable and searchable.
2. **`scripts/check_tracker.py` in CI and pre-commit.** It fails on:
   - a duplicate ID
   - an ID used in docs or commits but missing here
   - a `done` row without a date and PR
   - an old ID that was removed or renumbered

   It also rewrites the progress line and the checklist counts, so nobody counts by hand.
3. **Release gate:** the pilot tag can't be created while any `W`, `M` or gate-P `EC` item is still open. The script checks this.
4. **Later, mirror to GitHub Issues + Projects (X34).** While it's a one-person project, the markdown table is faster, works offline and gets reviewed in PRs. When outside contributors arrive, open one issue per open ID (e.g. `[X15] Culture & sensitivity`) on a Projects board, and decide in an ADR whether the issues or this file is the source of truth. Not now.

**Progress** (maintained by the script): Work 10/17 · Minimal 5/33 · After pilot (P2) 0/9 · Checklist gate P 0/61 · gate 1 0/31

**Gate `P2`** (owner, 2026-10-08, pilot-first cut, §18.2): the item is part of the minimal version but is built in the first release *after* the pilot. The pilot tag is checked against gate `P` only. `P2` items must be done before the first tagged release after the pilot.

## Work and minimal version (gate P, all must be done before the pilot)
| ID | Item | Gate | Status | Done (date · PR) |
|---|---|---|---|---|
| ~~W01~~ | ~~Repo scaffold: README, licence, community files, CI, pre-commit, gitleaks (§13)~~ | P | done | 2026-10-09 · af39ae4 |
| ~~W02~~ | ~~Research and compliance docs from the zip; ADR-0001 to 0008 (§13, §17.1, §17.6)~~ | P | done | 2026-10-09 · af39ae4 |
| ~~W03~~ | ~~Docker Compose stack: web, postgres, caddy, cloudflared (§1a)~~ | P | done | 2026-10-09 · f5ec4d0 |
| ~~W04~~ | ~~Foundation: settings, number series, file store~~ | P | done | 2026-10-09 · 662312a |
| ~~W05~~ | ~~Synthetic seed data and dummy datasets~~ | P | done | 2026-10-09 · 144d19c |
| W06 | Laptop install guide and hardening: SSD, OS, LUKS, UPS (§1a) | P | todo | |
| W07 | Restore-drill script and runbooks | P | todo | |
| ~~W08~~ | ~~Local gate script matching CI (`scripts/ci_local.sh`)~~ | P | done | 2026-10-09 · c0b6258 |
| ~~W08.1~~ | ~~Tracker tooling (§0 items 1–3): status column + strike-through, `scripts/check_tracker.py` rules and progress rewrite, pilot/release tag gate~~ | P | done | 2026-10-09 · c0b6258 |
| W09 | Pilot: one week running in parallel with the current system (§1a build order 5) | P | todo | |
| W10 | Cold standby: cold-restore runbook + `failover.sh` / `failback.sh`, rehearsed once on a rented India-region VPS (§17.4) | P | todo | |
| W10.1 | Warm standby: VPS restores the newest snapshot nightly (§17.4) | P2 | todo | |
| W11 | Multi-arch Docker images (amd64 + arm64), no provider-specific services (§17) | P | doing | amd64 image built locally; arm64 needs QEMU, unrun until CI |
| W12 | Release pipeline: git-cliff changelog, GHCR images with version tags, `rc` tag for the pilot, `docs/dev/releasing.md` (§18.3) | P | doing | release workflow unrun until the first tag |
| ~~W13~~ | ~~Dependency register `docs/DEPENDENCIES.md` + `scripts/audit_deps.py` + weekly scheduled check + "no dependency without a row" gate (§19)~~ | P | done | 2026-10-09 · d954bd5 |
| ~~W14~~ | ~~Supply-chain pinning: GitHub Actions by commit SHA, images by digest, vendored JS/CSS with recorded SHA-256 (§19.1)~~ | P | done | 2026-10-09 · d954bd5 |
| ~~W15~~ | ~~Platform ports: `labra.core.ports`, built-in adapters chosen from settings with fail-fast startup, one contract test suite per port, import-linter "core imports ports only", ADR-0008 (§17.6)~~ | P | done | 2026-10-09 · 662312a |
| W16 | Observability endpoints: `/readyz`, `/metrics` (Prometheus, internal or token only), request and job metrics without personal labels, job heartbeat pings (§17.6) | P | doing | readyz verified under Compose; backup heartbeat comes with W07 |
| ~~M01~~ | ~~Login and roles~~ | P | done | 2026-10-09 · 635a0db |
| ~~M01.1~~ | ~~Permission switches per role (`role_permission`)~~ | P | done | 2026-10-09 · 635a0db |
| ~~M01.2~~ | ~~Staff without login (collected/delivered by)~~ | P | done | 2026-10-09 · 635a0db |
| ~~M02~~ | ~~Branches~~ | P | done | 2026-10-09 · 0a85c84 |
| M03 | Patients | P | todo | |
| M04 | Referrers | P | todo | |
| M05 | Catalog (calculated parameters, preset comments) | P | todo | |
| M05.1 | Test short codes + aliases; code-first search with confirm line (§1d) | P | todo | |
| M05.2 | Reference ranges by sex/age with critical + absurd limits, interpretation bands, abnormal flag on options (§1d) | P | todo | |
| M06 | Prices: branch override and history | P | todo | |
| M07 | Visit and billing: bill of supply, payments, dues | P | todo | |
| M08 | Barcode sample labels | P | todo | |
| M09 | Manual routing, in-house or external, showing cost and margin | P | todo | |
| M10 | External labs and result PDF upload | P | todo | |
| M11 | Results: worklist, flags, previous value, critical-value log, verification | P | todo | |
| M11.1 | Result grid: keyboard entry, server-computed flags, colour states (screen only) (§1d) | P | todo | |
| M11.2 | Absurd-value guard and Friedewald/formula validity checks (§1d) | P | todo | |
| M12 | Reports: combined/separate, signature image, release, amendments, QR | P | todo | |
| M12.1 | Report layout v2: ISO 15189 §7.4.1.6 items on every report, panel/page-break rules, compact tiered ranges (§7.0) | P | todo | |
| M13 | Reports for the owner | P | todo | |
| M07.1 | Bill Rule 49 / 46 field check; 16-character number-format validation (§8) | P | todo | |
| M20.1 | Optional "abnormal results at a glance" box at the top of page 1 (§7.0) | P2 | todo | |
| M14 | Admin (SQLAdmin) | P | todo | |
| ~~M15~~ | ~~Compliance floor: hash-chained audit log, consent, no fetal-sex fields~~ | P | done | 2026-10-09 · 662312a |
| M16 | Backups: Google Drive + USB via restic | P | todo | |
| M17 | Letterhead and margin calibration (§7.2) | P | todo | |
| M17.1 | Convert-to-SVG suggestion (§7.2) | P2 | todo | |
| M18 | Fast front desk: one-screen visit | P | todo | |
| M18.1 | Keyboard shortcuts and `?` overlay (§1c); the shortcuts themselves ship in M18, the overlay waits | P2 | todo | |
| M19 | Patient history and cumulative results | P | todo | |
| M20 | Report options: selected tests, reference column, A4/A5, methods, barcode | P | todo | |
| M21 | Delivery tracking and outsourcing timeline | P | todo | |
| M22 | Lab status board (TV) | P2 | todo | |
| M23 | Currency display settings (§8) | P | todo | |
| M24 | Starter catalog import: the tests the lab already reports (Appendix A), ranges cited (§1c) | P | todo | |
| M24.1 | Rest of the ~300-test starter set | P2 | todo | |
| M25 | User manual, in-app help, screenshot generator (§13a); done when M25.1–M25.3 are done | P / P2 | todo | |
| M25.1 | Manual site (Zensical, reads `mkdocs.yml`; §19.3), page template, `manual_page=` registry gate, staleness gate (§16.1) | P | doing | screenshots pending, to be taken by hand |
| M25.2 | Playwright screenshot generator; until then manual pages carry hand-taken screenshots of seed data | P2 | todo | |
| M25.3 | In-app `?` help and printable manual PDF | P2 | todo | |
| M26 | Integration seam: event outbox + daily accounting export + full data export (CSV + Parquet) (§17) | P | todo | |
| M26.1 | Monthly Parquet archive of closed months into the restic repository (§17.3) | P2 | todo | |

## Next expansion (0.x, after the pilot)
| ID | Item | Note | Status | Done (date · PR) |
|---|---|---|---|---|
| X01 | WhatsApp report delivery + SMS fallback | | todo | |
| X02 | Report download via QR / link | | todo | |
| X03 | Smart report layout | | todo | |
| X04 | Referring-doctor portal | | todo | |
| X05 | Inventory: purchases, kit opening, automatic deduction per test, expiry | | todo | |
| X06 | Home collection with reminders | | todo | |
| X07 | Internal QC (Levey-Jennings + Westgard) | needed for NABL | todo | |
| X08 | Non-conformance log and EQA records | | todo | |
| X09 | Reflex test suggestions | | todo | |
| X10 | Rule-based autoverification (off by default) | | todo | |
| X11 | Turnaround (TAT) dashboard | | todo | |
| X12 | Regional-language report headings | | todo | |
| X13 | Patient card with QR | | todo | |
| X14 | B2B price list for labs sending samples to us | | todo | |
| X15 | Culture & sensitivity | **priority 1**; move to minimal if culture is done in-house | todo | |
| X16 | Special report layouts (CBC histograms, thyroid, HbA1c) | | todo | |
| X17 | Email reports + message log | | todo | |
| X18 | In-app notification panel | | todo | |
| X19 | Contacts phone book | | todo | |
| X20 | Expenses, supplier/external-lab payments and ledgers | **priority 2** | todo | |
| X21 | Remaining statements, with Excel/PDF export | | todo | |
| X22 | Owner analytics dashboard | | todo | |
| X23 | Owner phone dashboard (PWA) | | todo | |
| X24 | Opt-in update check, no telemetry | gate 1 | todo | |
| X25 | Branch offline counter (§9 Layer 3) | first, if outages are frequent | todo | |
| X26 | Organisation-certificate PAdES signing (§7.1 B) | | todo | |
| X27 | Tax invoice and GST split | | todo | |
| X28 | Refunds and credit notes | | todo | |
| X29 | Discount approvals | | todo | |
| X30 | Day close | | todo | |
| X31 | Price CSV import with preview | | todo | |
| X32 | Two-level verification | | todo | |
| X33 | `/api/v1` token auth + read endpoints, added only when a real consumer exists (§17) | | todo | |
| X34 | Mirror the tracker to GitHub Issues + Projects; ADR on which is the source of truth (§0 item 4) | when outside contributors arrive | todo | |
| X35 | OpenTelemetry export (traces, metrics, logs over OTLP) as the optional extra `labra[otel]` (§17.6) | when a lab runs a collector | todo | |

## Later (1.x / 2.x)
| ID | Item | Release | Status | Done (date · PR) |
|---|---|---|---|---|
| LT01 | AI "explain my report" (advisory) | 2.x | todo | |
| LT02 | AI value extraction from external PDFs | 2.x | todo | |
| LT03 | Analyser bridge: HL7 v2 / ASTM, data log | 2.x | todo | |
| LT04 | ABDM M1–M3 | 2.x | todo | |
| LT05 | Multi-site analytics | 2.x | todo | |
| LT06 | Full sample tracking with manifests | 1.x | todo | |
| LT07 | Email-inbox auto-match of external results | 1.x | todo | |
| LT08 | Custom fields and template editor in the UI | 1.x | todo | |
| LT09 | Credit accounts and statements | 1.x | todo | |
| LT10 | External-lab invoice reconciliation | 1.x | todo | |
| LT11 | Permission matrix UI and per-user override | 1.x | todo | |
| LT12 | FHIR export | 1.x | todo | |
| LT13 | Tally export | 1.x | todo | |
| LT14 | Labra Signer agent (personal DSC) | 1.x | todo | |
| LT15 | Aadhaar eSign / DocuSeal link-out plugins | 1.x | todo | |
| LT16 | Result trend charts | 1.x | todo | |
| LT17 | Continuation-page letterhead; A5/thermal bill layouts | 1.x | todo | |
| LT18 | Thermal-printer (ZPL) labels | 1.x | todo | |

## Rejected (kept as a record)
| ID | Item | Reason |
|---|---|---|
| R01 | Referral doctor commission | NMC fee-splitting rules (§1b) |
| R02 | ML / "AI" autoverification | Moves Labra toward a medical device (§1b) |
| R03 | White-label native mobile apps | Cost; a PWA covers it (§1b) |
| R04 | Digital pathology | Out of scope (§1b) |
| R05 | Year-end "reset / switch database" | Breaks the audit trail and NABL retention (§1c) |

## Enterprise checklist (counts only; tick the items in §14a)
| Section | IDs | Gate P | Gate 1 | Gate L |
|---|---|---|---|---|
| A Security | EC-A01–A16 | 0/12 | 0/3 | 0/1 |
| B Data integrity and money | EC-B01–B08 | 0/7 | 0/1 | — |
| C Privacy and compliance | EC-C01–C09 | 0/5 | 0/3 | 0/1 |
| D Reliability, backup, DR | EC-D01–D09 | 0/7 | 0/1 | 0/1 |
| E Observability and support | EC-E01–E06 | 0/4 | 0/2 | — |
| F Performance | EC-F01–F04 | 0/3 | 0/1 | — |
| G Upgrades and migrations | EC-G01–G06 | 0/4 | 0/2 | — |
| H Code quality and testing | EC-H01–H07 | 0/5 | 0/2 | — |
| I Supply chain | EC-I01–I07 | 0/5 | 0/2 | — |
| J Usability | EC-J01–J05 | 0/3 | 0/2 | — |
| K Configuration safety | EC-K01–K05 | 0/3 | 0/2 | — |
| L Documentation | EC-L01–L05 | 0/3 | 0/2 | — |
| O Open-source health | EC-O01–O08 | — | 0/8 | — |

The release checklist (§14a M) repeats every release, so it has no IDs; each release PR carries its own ticked copy.
