# Labra v1: detailed product and technical plan

## 0. Master tracker and item IDs (owner request 2026-10-05)
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

**Progress** (maintained by the script): Work 0/15 · Minimal 0/33 · After pilot (P2) 0/9 · Checklist gate P 0/61 · gate 1 0/31

**Gate `P2`** (owner, 2026-10-08, pilot-first cut, §18.2): the item is part of the minimal version but is built in the first release *after* the pilot. The pilot tag is checked against gate `P` only. `P2` items must be done before the first tagged release after the pilot.

### Work and minimal version (gate P, all must be done before the pilot)
| ID | Item | Gate | Status | Done (date · PR) |
|---|---|---|---|---|
| W01 | Repo scaffold: README, licence, community files, CI, pre-commit, gitleaks (§13) | P | todo | |
| W02 | Research and compliance docs from the zip; ADR-0001 to 0006 (§13) | P | todo | |
| W03 | Docker Compose stack: web, postgres, caddy, cloudflared (§1a) | P | todo | |
| W04 | Foundation: settings, number series, file store | P | todo | |
| W05 | Synthetic seed data and dummy datasets | P | todo | |
| W06 | Laptop install guide and hardening: SSD, OS, LUKS, UPS (§1a) | P | todo | |
| W07 | Restore-drill script and runbooks | P | todo | |
| W08 | Local gate script matching CI (`scripts/ci_local.sh`) | P | todo | |
| W08.1 | Tracker tooling (§0 items 1–3): status column + strike-through, `scripts/check_tracker.py` rules and progress rewrite, pilot/release tag gate | P | todo | |
| W09 | Pilot: one week running in parallel with the current system (§1a build order 5) | P | todo | |
| W10 | Cold standby: cold-restore runbook + `failover.sh` / `failback.sh`, rehearsed once on a rented India-region VPS (§17.4) | P | todo | |
| W10.1 | Warm standby: VPS restores the newest snapshot nightly (§17.4) | P2 | todo | |
| W11 | Multi-arch Docker images (amd64 + arm64), no provider-specific services (§17) | P | todo | |
| W12 | Release pipeline: git-cliff changelog, GHCR images with version tags, `rc` tag for the pilot, `docs/dev/releasing.md` (§18.3) | P | todo | |
| W13 | Dependency register `docs/DEPENDENCIES.md` + `scripts/audit_deps.py` + weekly scheduled check + "no dependency without a row" gate (§19) | P | todo | |
| W14 | Supply-chain pinning: GitHub Actions by commit SHA, images by digest, vendored JS/CSS with recorded SHA-256 (§19.1) | P | todo | |
| M01 | Login and roles | P | todo | |
| M01.1 | Permission switches per role (`role_permission`) | P | todo | |
| M01.2 | Staff without login (collected/delivered by) | P | todo | |
| M02 | Branches | P | todo | |
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
| M07.1 | Bill of supply Rule 49 field check; 16-character number-format validation (§8). Rule 46 (tax invoice) comes with X27 | P | todo | |
| M20.1 | Optional "abnormal results at a glance" box at the top of page 1 (§7.0) | P2 | todo | |
| M14 | Admin screens (own HTMX, ADR-0010) | P | todo | |
| M15 | Compliance floor: hash-chained audit log, consent, no fetal-sex fields | P | todo | |
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
| M25.1 | Manual site (Zensical, reads `mkdocs.yml`; §19.3), page template, `manual_page=` registry gate, staleness gate (§16.1) | P | todo | |
| M25.2 | Playwright screenshot generator; until then manual pages carry hand-taken screenshots of seed data | P2 | todo | |
| M25.3 | In-app `?` help and printable manual PDF | P2 | todo | |
| M26 | Integration seam: event outbox + daily accounting export + full data export (CSV + Parquet) (§17) | P | todo | |
| M26.1 | Monthly Parquet archive of closed months into the restic repository (§17.3) | P2 | todo | |

### Next expansion (0.x, after the pilot)
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

### Later (1.x / 2.x)
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

### Rejected (kept as a record)
| ID | Item | Reason |
|---|---|---|
| R01 | Referral doctor commission | NMC fee-splitting rules (§1b) |
| R02 | ML / "AI" autoverification | Moves Labra toward a medical device (§1b) |
| R03 | White-label native mobile apps | Cost; a PWA covers it (§1b) |
| R04 | Digital pathology | Out of scope (§1b) |
| R05 | Year-end "reset / switch database" | Breaks the audit trail and NABL retention (§1c) |

### Enterprise checklist (counts only; tick the items in §14a)
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

## 1. Context
**Labra** (`premdon009/labra`, public, MIT) is open-source software for running small Indian diagnostic lab chains: patients, orders, samples, outsourcing, results, reports and billing.

- **Origin:** a bootstrap plan was written 2026-08-18 and archived in `~/labra-plan-and-research.zip`, together with an open-source lab-software survey and an Indian lab-regulations survey.
- **This document** replaces that plan's scope with the owner's requirements gathered on 2026-10-05.
- **Nothing was built** when this plan was written.

**The owner's lab setup (the reference customer):**
- **Main lab:** one, running about 60% of tests in-house.
- **Branches:** 2–3 collection centres with 10–30 patients a day each. They register patients, bill, collect samples and send them to the main lab.
- **Outsourcing:** about **40% of tests go to third-party labs**, chosen **per case** on price, margin and turnaround. Results come back through **portals and email** (PDF).
- **Patient reports:** **combined or separate, decided per case.**
- **Admin portal:** used about 4–5 times a week (prices, catalog, settings).
- **Internet:** must keep working through outages.
- **Customisation:** it's open source, so workflows must be configurable, not hard-coded for one lab.

**Decisions already made:**
- **Backend:** FastAPI.
- **Database:** Postgres.
- **Hosting:** a mini PC at the main lab by default; the same Docker Compose file runs on a cloud server.
- **Medical standards:** used where they apply.
- **Regulations:** documented, not legally certified.
- **AI:** advisory only, later.

## 1a. MINIMAL WORKING VERSION: build this first (owner, 2026-10-05)
Goal: the smallest Labra that runs a real day at the owner's labs (register → bill → sample → in-house or outsourced → result → signed-off report → collection report) on an **old laptop**, with automatic backups to **Google Drive**. Everything in §2 onwards stays as the **expansion design**: the data model leaves room for it, but none of it is built until the minimal version is in daily use.

### Server hardware: old laptop
| Item | Minimum | Notes |
|---|---|---|
| Laptop | old-gen AMD CPU, **4 GB RAM works, 8 GB comfortable** | The whole stack uses under about 1 GB (below) |
| Disk | **Replace the HDD with a SATA SSD (256 GB, about ₹1,500–2,500)** | Biggest single win for speed and reliability; old laptop HDDs are the most likely part to fail |
| OS | **Debian 13 or Ubuntu Server LTS, no desktop** (saves about 1 GB RAM) | Set "do nothing on lid close", turn off sleep, auto-start on power, enable automatic security updates |
| Power | The laptop battery is its own UPS; put the **router and switch on a small UPS** too | Without that, branches lose access during a power cut even though the laptop stays up |
| Network | Wired Ethernet to the router; fixed local IP (`labra.lan`) | Wi-Fi only as fallback |
| Internet | Main lab broadband + a 4G hotspot fallback; branches use a 4G hotspot fallback | This is the minimal version's offline strategy (below) |

**Estimated memory use (4 GB laptop):**
| Process | RAM |
|---|---|
| Postgres (tuned: `shared_buffers=256MB`, `max_connections=30`) | about 300 MB |
| Labra web (uvicorn, 2 workers, PDF rendering inline) | about 250 MB |
| Caddy | about 30 MB |
| cloudflared | about 30 MB |
| OS | about 300 MB |
| **Total** | **about 1 GB** (leaves room on 4 GB) |

There's **no separate worker process** in the minimal version: PDFs are rendered when a report or bill is opened (1–3 s on an old CPU), and backups run from a systemd timer. Docker Compose is still used, since it makes installs and upgrades reproducible. Docker's own overhead is small.

### Backups to Google Drive
- **Tools:** `pg_dump` (database) + the `/data/files` folder (PDFs, logos, signature images) → **restic** (encrypted, deduplicated, snapshots) using **rclone's Google Drive backend**. Both are free and open source.
- **Encryption first:** everything is encrypted on the laptop *before* upload, so Google only holds encrypted blobs. This matters for patient data under DPDP, since Drive servers may be outside India.
- **Schedule and retention:** superseded 2026-10-08 by §17.3 (every 15 min in lab hours + nightly; keep all for 2 days, hourly 7 days, daily 30 days, monthly 24 months, which covers NABL's 2-year retention).
- **Size estimate:** the database stays under 1 GB/year. PDFs are about 200 KB × about 2,700/month ≈ 6–7 GB/year (restic dedup trims repeats). Free Drive (15 GB) lasts about 1–2 years; Google One 100 GB costs about ₹130/month (check current price).
- **Second copy:** the same restic snapshot also goes to a USB drive plugged into the laptop, for fast restores even with no internet.
- **Rules:**
  - Use a dedicated Google account for backups (not a staff member's personal account), with 2-step verification. Use its own OAuth client ID in rclone to avoid shared rate limits.
  - Store the restic password in **two offline places** (owner + a sealed envelope). Losing it means the backups can't be read.
  - Each backup sends an "ok" ping to a monitor (Healthchecks.io free tier or Uptime Kuma later). A missed backup alerts the owner by email.
  - **Monthly restore drill:** a script restores the latest snapshot into a throwaway database and checks row counts. A backup that has never been restored doesn't count.
- **Restore runbook:** a fresh OS install, `git clone`, `docker compose up`, then `scripts/restore.sh <snapshot>`. Target: back in business within 1–2 hours on any spare laptop.

### Offline in the minimal version (no offline counter yet)
1. **The main lab runs over its LAN**, so it keeps working fully with no internet.
2. **Branches** fall back to their 4G hotspot. If even that fails, they use a **printed fallback slip** (pre-numbered paper receipt book). The front desk keys those visits in later, using the original receipt number in a "manual receipt ref" field.
3. The branch offline counter (§9 Layer 3) is the first expansion item if outages turn out to be frequent.

### Minimal feature list
| ID | Feature | In the minimal version | Deferred to expansion |
|---|---|---|---|
| M01 | Login and roles | Username + password (argon2), 4 fixed roles: **admin, front_desk, technician, signatory**, each user tied to branch(es) | 2FA, permission matrix, branch-manager role |
| M02 | Branches | Main lab + collection centres, letterhead details per branch | per-branch templates |
| M03 | Patients | Name, sex, DOB/age, phone, address, patient no; duplicate warning by phone + name | ABHA, custom fields, merge queue |
| M04 | Referrers | Simple doctor/clinic list | analytics |
| M05 | Catalog | Departments, specimen types, tests with parameters, units, sex/age reference ranges, packages, **calculated parameters** (e.g. LDL, A/G ratio, eGFR; safe formula evaluator, no `eval`), **preset comments / option lists** for text results (urine routine, smear) | LOINC/SNOMED import, interpretation library |
| M06 | Prices | One price per test/package, with an optional **branch price override**; changes keep history (valid_from/to) | multiple price lists (camp/corporate), CSV import with preview |
| M07 | Visit and billing | Add tests/packages, discount (₹ or %) **with a reason**, **bill of supply** (exempt diagnostics), payments cash/UPI/card, part payment and dues, cancel bill with reason | tax invoice and GST split, refunds/credit notes, discount approvals, credit accounts, day close |
| M08 | Labels | Barcode sample label (50×25 mm) printed from the browser | thermal-printer ZPL |
| M09 | Routing | Per test: **in-house or external lab X**, picked manually from a dropdown that shows cost and margin | ranked suggestion engine, routing strategies |
| M10 | External labs | List + cost and turnaround per test; record their accession no; upload the result PDF; optional manual value entry | email-inbox auto-match, invoice reconciliation |
| M11 | Results | Worklist per department, result entry with automatic H/L flags, **previous value shown beside each entry (simple delta view)**, **critical values highlighted + mandatory "informed whom / when / how" log** (NABL), verification | two-level verification, automatic delta-check rules, autoverification, quality control |
| M12 | Reports | A4 PDF, **combined or separate chosen per visit**, outsourced tests named, signature **image**, release by signatory only, amended versions, QR with report number | PAdES certificate signing (§7.1), email/WhatsApp delivery |
| M13 | Reports for the owner | Daily collection (by branch, payment mode), dues list, pending tests, outsourcing cost vs revenue | full management reports, Excel export |
| M14 | Admin | Own HTMX admin screens (ADR-0010) for branches, users, catalog, prices, external labs, settings | template editor, custom fields |
| M15 | Compliance floor | Append-only audit log (trigger + hash chain), consent tick at registration (incl. referral-lab sharing), no fetal-sex fields | DPDP erasure workflow, breach log |
| M17 | **Letterhead and margin setup** (§7.2) | Upload letterhead (**SVG / vector PDF preferred**; PNG/JPG/WebP auto-optimised to about 100–250 KB) per branch for **A4 report** and **A4 bill**; **digital PDF = content on top of the letterhead**, **print PDF = same layout without the letterhead** for pre-printed paper; **margin sliders** with live preview on dummy data; printable calibration page | different letterhead for continuation pages; A5/thermal bill layouts |
| M16 | Backups | Google Drive + USB via restic, 15 min–24 h interval (default 15 min, §17.3), restore drill script | — |
| M18 | **Fast front desk** (§1c) | **One-screen visit**: patient, referrer (**quick-add new doctor inline**), tests (search by code or name), price, discount / **extra charges with reason**, payment, **promised delivery time**, **footer note (printed)** and **internal note (not printed)**, on one page; keyboard shortcuts (§1c); age entered as **years / months / days** | configurable field layout |
| M19 | **Patient history** (§1c) | Search by phone, patient no, name (fuzzy, `pg_trgm`, handles spelling variants), address, date range; **cumulative result table** (same test across visits, side by side) | trend charts |
| M20 | **Report options** (§1c) | Print **selected tests only**; **with / without reference-range column**; **A4 or A5** layout (A5 for short reports); methods printed per test (**method list, several per test, one default**); barcode on report, scanning it opens the visit | per-test custom report designs |
| M21 | **Delivery tracking** (§1c) | Report status **printed / not printed**, **delivered** (to whom, how: counter / home / email / WhatsApp, by which staff); outsourced-test **timeline** (registered → sent → received → delivered, each with time and user) | — |
| M22 | **Lab status board** (§1c) | One full-screen page for a lab TV: visits colour-coded pending / partly done / completed / delivered, outsourced flag, upcoming promised deliveries, auto-refresh (HTMX polling every 30 s), click → enter results | — |
| M23 | **Currency display** (§8) | Symbol, position, Indian grouping, decimals, amount in words, round-off unit as settings; one `format_money()` helper | — |
| M24 | **Starter catalog** (§1c) | Optional import of about 300 common tests with units, adult ranges (each cited), specimen and container; reviewed by the lab's pathologist before use | more departments, paediatric ranges |
| M25 | **User manual** (§13a) | Manual pages for every minimal screen, auto-generated screenshots, in-app `?` help, screen-registry and staleness gates | translations |

### Minimal data model (subset of §5, about 28 tables)
`lab_profile`, `branch`, `app_user`, `user_branch_role` (role as enum), `setting`, `number_series`, `patient`, `patient_consent`, `referrer`, `department`, `specimen_type`, `test`, `test_parameter`, `reference_range`, `package`, `package_item`, `price` (item, branch nullable, price, valid_from/to), `external_lab`, `external_lab_rate`, `visit`, `order_item`, `order_test`, `sample`, `result`, `external_document`, `report`, `bill`, `bill_line`, `payment`, `stored_file`, `audit_log`, `critical_notification`, `comment_preset`, `letterhead_layout`, `test_method` (test_id, name, is_default), `report_delivery` (report_id, delivered_to, mode, by, at), `order_test_event` (order_test_id, event, at, by, note: the outsourcing timeline), `role_permission` (seeded; admin can toggle per role).

They keep the conventions in §5:
- app-generated UUIDs, `branch_id`, `client_ref`
- an `extra` JSONB column
- a `doc_type` on `bill` that already allows `tax_invoice`

So every expansion item is new tables or new code, never a rewrite. The minimal bill and report formats are the ones in §7 and §8, minus the tax-invoice columns and the certificate signature box.

### Minimal stack (subset of §4)
- **App:** FastAPI, SQLAlchemy 2 (sync), Alembic, Postgres 18, Jinja2 + HTMX 4 + Alpine (CSP build) + **Basecoat UI (shadcn look)**, WeasyPrint, vtracer (optional SVG tracing), **pypdf** (letterhead overlay), **pypdfium2** (preview images), python-barcode, segno, argon2-cffi, DuckDB (Parquet exports).
- **Test only:** pdfplumber (checks text positions in letterhead tests).
- **Ops:** Docker Compose (web, postgres, caddy, cloudflared), restic + rclone, systemd timer.
- **Dev:** uv, ruff, pyright, pytest + testcontainers, Playwright (one end-to-end path), GitHub Actions, gitleaks, Zensical (docs site).
- Every item above is listed with licence and maintenance status in the dependency register (§19).
- **Deferred:** Procrastinate, pyHanko, fhir.resources, imap-tools, GlitchTip.

### Minimal build order
1. **Repo + foundation:** CI, Compose, auth/roles/branches, audit log, settings, numbering, backup + restore scripts, synthetic seed data.
2. **Catalog + prices + admin screens.**
3. **Front desk:** patients, visits, billing, payments, receipt and label printing.
4. **Lab:** routing, results, external PDF upload, verification, report PDF and release.
5. **Owner reports.** Then install on the laptop, run a restore drill, and **pilot**: one week in parallel with the current system on real work, on the laptop only.

### Minimal-version verification
- Every **gate P** item in the enterprise checklist (§14a) is ticked before the pilot starts.
- `uv run pytest` green in CI (real Postgres via testcontainers).
- One Playwright end-to-end test on seed data runs the whole flow: register → bill → label → route 1 in-house + 1 external → enter/upload results → verify → release combined and separate reports → daily collection report.
- On the actual laptop: with **4 GB RAM**, 3 concurrent users + PDF rendering stays under 2 GB used. Unplug the WAN: the main lab keeps working.
- **Backup:** wait one scheduled run, confirm the snapshot appears in Drive and on USB, then restore it on another machine and get a working app.

## 1b. Ideas from popular open-source projects and market trends (researched 2026-10-05)
**Sources checked:**
- **Open-source lab systems:** OpenELIS Global 2 (very active, 25+ countries), SENAITE (+ its reflex add-on), plus the 2026-08 survey in the zip.
- **Indian commercial lab software:** what features vendors market, used as a gauge of what labs expect.
- **2026 research and trend articles:** autoverification and LLM-generated patient explanations.

**Sorting rule:** the four tables below run from "add to the minimal version" to "rejected". An idea goes in the minimal version only if it's cheap *and* a real lab day needs it.

### Pulled into the minimal version (§1a, already edited)
| Idea | Seen in | Why now |
|---|---|---|
| Calculated parameters (LDL, A/G ratio, eGFR) | OpenELIS "calculated values", every Indian lab system | Lipid and liver panels need them on day 1 |
| Preset comments / option lists for text results | SENAITE, Indian lab systems | Urine routine and smear reports are mostly text |
| Previous result shown beside entry | OpenELIS, delta-check practice | Catches sample mix-ups for almost no effort |
| Critical value highlight + "informed whom/when" log | OpenELIS critical ranges, NABL requirement | Required for accreditation; just one table: `critical_notification` (result_id, informed_to, phone, at, by, mode) |

### Next expansion (first 0.x releases after the pilot), in suggested order
| ID | Idea | Seen in | Notes for Labra |
|---|---|---|---|
| X01 | **WhatsApp report delivery** (official WhatsApp Business API, password-protected PDF = patient DOB or last 4 digits of phone) + SMS link fallback | Basic feature in every Indian lab product | `labra.notifiers` plugin; the provider is the lab's choice; needs internet, queued while offline. SMS needs TRAI DLT registration |
| X02 | **Report download via QR on the bill / a link** (OTP or DOB check) | Indian lab products ("scan the bill to download") | Needs the server reachable publicly through Cloudflare Tunnel, with rate limits; reduces front-desk load |
| X03 | **Smart report layout:** colour range bar per result, trend sparkline from previous values, summary page of abnormal results | Indian lab products' "smart reports" | Template-only change once history exists; keep a plain layout option for doctors who prefer it |
| X04 | **Referring-doctor portal** (view their patients' reports) | Indian vendors, SENAITE client portal | Read-only, per-referrer login; consent text must cover it |
| X05 | **Reagent and consumables inventory** with expiry, lot no and low-stock alerts | Common in Indian lab products; OpenELIS has inventory | Optional module; links lot no to QC later |
| X06 | **Home collection** scheduling: slot, address, phlebotomist assignment, status | Indian lab products (mid-tier plans) | Start as a booking list + mobile-friendly web page for the phlebotomist (installable web app); no native app |
| X07 | **Internal QC:** Levey-Jennings charts + Westgard rules (1-2s warn; 1-3s, 2-2s, R-4s, 4-1s, 10x reject) | OpenELIS (Westgard dashboard in 2026), SENAITE worksheets | A rejected QC run **blocks release** of that test's results until a passing run, as OpenELIS does. Needed for NABL |
| X08 | **Non-conformance / incident log** (rejected samples, complaints, corrective actions) and **External Quality Assessment (EQA) records** | OpenELIS quality module and EQA module | Simple forms + register report; NABL audit evidence |
| X09 | **Reflex rule suggestions** (e.g. TSH high → suggest FT4) | OpenELIS Rule Builder, senaite.reflex | Labra only **suggests**; front desk/doctor confirms, and the bill is updated with consent; never auto-bill |
| X10 | **Rule-based autoverification** (within range + delta OK + QC passed + no flags → auto-verify), **off by default**, per test | Clinical labs following CLSI AUTO-10 (60–80% auto-release typical) | Plain rules, fully audited, a signatory still releases the report; per-test switch |
| X11 | **Turnaround (TAT) dashboard** per test/branch/external lab | OpenELIS lab management dashboard, Indian vendors | Uses timestamps already in the model |
| X12 | Regional-language report headings / patient instructions | Indian market | Babel already planned |

### Later (needs maturity, certification or internet)
| Idea | Seen in | Notes |
|---|---|---|
| `LT01` **AI "explain my report" in plain language** (English + regional) | 2026 research: LLM explanations improve patient understanding, but hallucination and missed-abnormal risks are documented | Advisory only. Draft generated **only from the verified values**, abnormal values always listed by plain rules (not the LLM), shown to the signatory for approval, marked "not a diagnosis", per-lab switch, consent for cloud LLMs (§12). Possible CDSCO medical-device angle, so needs a legal check before enabling |
| `LT02` AI extraction of values from external lab PDFs | Indian vendors, research | A person confirms every value |
| `LT03` Bidirectional analyzer interface (orders to analyzer, results back) | OpenELIS (35+ analyzer plugins), Indian vendors | Analyzer bridge (2.x) |
| `LT04` **ABDM M1–M3**: ABHA linking, push reports to the patient's ABHA locker, **"Scan & Share" ABHA registration** at the counter | Indian vendors list ABDM M1/M2/M3 certification | Needs the ABDM certification process; FHIR layer first |
| `LT05` Multi-site analytics / compliance dashboard | Vendor trend lists | After 2+ labs run Labra |

### Rejected (and why)
| Idea | Reason |
|---|---|
| `R01` Referral doctor **commission** management | Very common in Indian lab products, but fee-splitting conflicts with NMC ethics rules; legal risk for an open-source project to promote it |
| `R02` ML/"AI" autoverification | Moves Labra toward a medical device (CDSCO/EU AI Act-style scrutiny); plain rule-based autoverification gives most of the benefit |
| `R03` White-label native mobile apps | Cost and app-store upkeep; an installable web app (PWA) covers patient, doctor and phlebotomist use |
| `R04` Digital pathology / whole-slide imaging | Out of scope for small collection-centre chains |

## 1c. Feature check against a commercial lab-software manual (2026-10-05)
The owner shared the manual of a commercial desktop lab product popular with small Indian labs. It was used **only as a checklist of what labs expect**. Hard rule: **the product, its vendor, screenshots and wording are never named or copied in the Labra repo, docs, commits or issues.** Every idea below is written in Labra's own words. (When this plan is copied into the repo as `docs/design/v1-plan.md`, this paragraph stays as worded: no name.)

| ID | Area | What labs expect | Labra decision | Gate |
|---|---|---|---|---|
| M18 | Front desk | Everything for a visit on **one screen**, keyboard-driven | Row 18: one-screen visit | **Minimal** |
| M18 | Front desk | Quick-add a new referring doctor during registration | Row 18 | **Minimal** |
| M18 | Front desk | Extra charges and concession, each with a reason | Row 18 (`order_item` kind `extra_charge`) | **Minimal** |
| M18 | Front desk | Promised delivery time per visit; walk-in vs home-collection case type | Row 18 (`visit.promised_at`; `collection_mode` exists) | **Minimal** |
| M18 | Front desk | Age in years / months / days (infants) | Row 18 (stored as DOB, estimated) | **Minimal** |
| X13 | Front desk | Regular-patient card number, lookup by card or phone | `patient_no` printed as a QR card | Next expansion |
| M01.1 (LT11) | Access | Per-action permission switches (new report, print, cancel, payment, refund, ...) | `role_permission` seeded in minimal; toggles per role on an admin screen; **per-user override** later | **Minimal** (per role) |
| M24 | Catalog | **Hundreds of tests pre-loaded** with units and ranges | **Starter catalog** (~300 common Indian tests, parameters, units, adult ranges, specimen, container) as an optional import, **authored by Labra from public references, each range cited**, to be reviewed by the lab's pathologist before use | **Minimal** (import file) |
| M20 | Catalog | Method list, several per test, one default, printed on report | Row 20, `test_method` | **Minimal** |
| X14 | Catalog | Lab-to-lab (B2B) price for samples **other labs send to us** | `price_list` kind `b2b` + `credit_account` | Next expansion |
| M05, M11 | Results | Calculated values, dropdown results, H/L flags, department order | Already rows 5 and 11 | **Minimal** |
| X15 | Results | **Culture & sensitivity**: organism, colony count, antibiotic panel, S / I / R with zone size (mm) | New tables `organism`, `antibiotic`, `antibiotic_panel(_item)`, `culture_result`, `culture_sensitivity`; report section per isolate | Next expansion **#1** (pull into minimal if culture is done in-house) |
| M19 | Results | **Cumulative patient history** across visits; fuzzy name search | Row 19 | **Minimal** |
| M20 | Reports | Print selected tests only; with/without reference column; A4/A5 | Row 20 (+ `letterhead_layout.doc_kind` adds `report_a5`) | **Minimal** |
| M17 | Reports | With / without header PDF | Already §7.2 (digital vs print PDF) | **Minimal** |
| M18 | Reports | Footer note (printed) + internal note (not printed) | Row 18 | **Minimal** |
| X16 | Reports | **Special layouts** for CBC (with analyser histograms), thyroid, HbA1c, etc., including analyser name | `test.report_template_id` override | Next expansion |
| X17 | Reports | Email several reports in one mail, extra attachments, sent history | `labra.notifiers` email + `message_log` | Next expansion (with WhatsApp, #2) |
| X01, X02 | Reports | WhatsApp via secure link | Already next-expansion items 1–2 | Next expansion |
| M21 | Tracking | Outsourced sample sent → report received → printed → delivered, with **timeline and user** | Row 21, `order_test_event` | **Minimal** |
| M21 | Tracking | Report delivered yes/no, by whom | Row 21, `report_delivery` | **Minimal** |
| M22 | Tracking | **Lab TV status board** with colour codes and upcoming deliveries | Row 22 | **Minimal** |
| X18 | Tracking | In-app notification panel (report due soon, external result received, dues, home-visit reminders) | `notification` table + bell icon; HTMX polling | Next expansion |
| X06 | Home collection | Appointment list with on-screen reminders | Next-expansion item 6 (adds reminder ticker) | Next expansion |
| X19 | Contacts | Phone book of patients, suppliers, external labs, doctors; pick when emailing | Use existing referrer / external_lab / supplier tables + a `contact` table for others | Next expansion |
| M01.2 | Staff | Staff without login (e.g. phlebotomist) selectable as "collected by / delivered by" | `app_user.can_login = false` | **Minimal** |
| X05 | Inventory | Purchase invoice entry, **kit opening**, adjustment for QC/standards, stock report, **automatic deduction per test** | Expands next-expansion item 5: `supplier`, `purchase_invoice(_line)`, `stock_lot`, `stock_move` (purchase / open / adjust / consume / expire), `test_consumption` (test → reagent qty) | Next expansion |
| X20 | Money out | Supplier payments, external-lab payments (cash/credit) and their **ledgers**, **daily expenses**, visiting-doctor fees (as expenses, not referral commission) | `expense`, `expense_category`, `supplier_payment`, `external_lab_payment`; ledgers as reports | Next expansion **#2** (owner's profit report needs it) |
| M13, X21 | Statements | Income date / month / year; dues; concessions; expenses; stock; test statistics; external-lab statement; referrer-wise **visit counts and revenue** (no commission); purchases; price list; patient ledger; external-lab ledger | Report catalogue: minimal ships income, dues, concessions, pending, outsourcing margin, test statistics, price list; rest with the modules above. Every report exports to Excel and PDF | Split |
| X22 | Analytics | Day-wise and referrer-wise ranking, cases and collection line graphs, averages, gender split | Owner dashboard page (charts via a small JS chart library, vendored) | Next expansion |
| X23 | Owner on phone | Owner/manager mobile view of today's patients, income, dues, expenses, hourly chart | **Installable web app (PWA)** dashboard, read-only; no native app | Next expansion |
| LT03 | Analyser | CBC analysers over LAN or serial (ASTM), result **data log**, manual re-receive, take units/ranges from master, name/sex validation | Analyser bridge (2.x) gains these as requirements | Later |
| R05 | Year end | **"Reset database" and "switch database" per year** | **Rejected.** Breaks the audit trail, history and NABL retention. Instead: numbering resets each financial year (already), all years stay in one database, every list has a year filter, old years can be archived to read-only partitions later | — |
| X24 | Updates | Automatic check for a new version | Opt-in check against GitHub releases; shows "new version available" on the System page; **no telemetry**, never auto-installs | **1** |
| R01 | Referrers | **Doctor commission** | **Rejected** (already in §1b: NMC fee-splitting rules) | — |

**Keyboard shortcuts** (front desk, shown in a `?` overlay, configurable later):
| Key | Action | Key | Action |
|---|---|---|---|
| `Alt+N` | New visit | `Alt+P` | Print report |
| `F2` | Open list for the focused field (doctor, test) | `Alt+L` | Print sample labels |
| `Alt+F` | Find patient / report | `Alt+R` | Receipt / bill |
| `Alt+H` | Patient history | `Alt+D` | Dues list |
| `Alt+S` | Save | `Esc` | Close dialog |
(`Ctrl+N`/`Ctrl+P`/`Ctrl+W` are avoided: browsers reserve them.)

## 1d. Result entry: test codes, reference ranges, colour flags (owner request 2026-10-05)
The owner shared screenshots of a commercial product's result screen as a workflow reference (same rule as §1c: never named or copied). **What it does:**
- Short test codes (`hb`, `esr`, `sf`), with F2 for a searchable code / name / price list.
- A confirm line showing the full name of the typed code.
- Each added test expands into parameter rows: test name, result, unit, normal range.
- Calculated rows such as VLDL and ratios.
- Drop-down results for text parameters.
- Coloured result cells.

**What Labra improves:**
- **Ranges as data:** the reference shows normal ranges as free text (`> 150 mg/dl - Suspect > 200`), which can't drive colours reliably. Labra stores numbers and bands.
- **Grouping:** the reference shows urine rows mixed in with lipid rows. Labra groups rows under a header per test.
- **Selection colour:** the reference uses blue for both the selected row and a coloured result. Labra's focus is an outline, never a fill colour.
- **Units:** the reference allows typos like `mgs/dl`. Labra picks units from a UCUM list.
- **Role split:** the reference enters results on the billing screen. In Labra they're separate screens with one shared grid component. A setting lets a one-person lab do both from the visit page.

### Where each piece of data comes from
| Data | Stored in | Source | Who maintains |
|---|---|---|---|
| Test code, name, price | `test.code`, `aliases[]`, `price` (M05, M06) | Starter catalog (M24) → the lab edits codes to match the habits of its staff | Admin screens (price history) |
| Parameters of a test (Lipid → TC, TG, HDL, LDL, VLDL, ratios) | `test_parameter` rows, `display_order` | Starter catalog | Admin |
| Unit | `test_parameter.unit_ucum` (picklist, no free text) | UCUM | Admin |
| **Normal range** | `reference_range` by sex + age (in days, so infants work), low/high either side optional | **1st: the lab's own kit insert / analyser manufacturer** (ISO 15189 makes the lab verify ranges for its own method). **Starter values:** published guidelines, each row with a `source_citation` (e.g. lipid categories from the NCEP ATP III tiers, glucose from ADA, eGFR from KDIGO, Hb from WHO anaemia cut-offs) | **Pathologist approves** (`approved_by/at`); a starter range stays "unapproved" (yellow banner in admin) until then |
| Critical limits | `critical_low/high` | The lab's critical-value policy (NABL needs one) | Pathologist |
| Absurd limits (typo guard, e.g. Hb > 25 g/dL) | `absurd_low/high` | Starter catalog | Admin |
| Interpretation tiers (Optimal / Near optimal / Borderline / High) | `reference_band` | Same guidelines as above | Pathologist |
| Option lists (Nil / Trace / +, ++) and which are abnormal | `test_parameter.options[].abnormal` | Starter catalog | Admin |
| Formula (VLDL = TG/5, LDL Friedewald, ratios, A/G, eGFR) | `test_parameter.formula` + `formula_valid_if` | Starter catalog; safe evaluator (no `eval`) | Admin |
| Optional standard code | `loinc_code` | LOINC import tool (Labra doesn't ship the file, §11) | Admin |
| **The value** | `result` | Technician entry; calculated rows; manual entry from an external PDF (M10); analyser (LT03, later) | — |

**Range selection:** the range is chosen from the patient's sex and **age at collection**. Its numbers and text are **copied into the result** when entered, so editing a range later never changes past results or reprints.

### Flag logic (one Python function, server-side only)
`compute_flag(value, range, bands, options) → (flag, band_label)`, in `results/flags.py`:
1. Empty → no flag.
2. Option result → `A` if the chosen option is marked abnormal, else `N`.
3. Numeric value outside the absurd limits → refused with "check value". Saving it needs a second confirm, which is audited.
4. ≤ critical_low → `LL`; ≥ critical_high → `HH`. This triggers the mandatory "informed whom / when / how" dialog (M11).
5. Below low → `L`; above high → `H`. A one-sided range checks only its own side (HDL low is bad; high is fine).
6. Else `N`. If bands exist, `band_label` is set, and a band with severity `borderline` colours amber even inside the printed range.
7. Calculated row: recomputed whenever an input changes. If `formula_valid_if` fails (Friedewald LDL with TG ≥ 400), the cell shows "not calculable, measure directly" instead of a wrong number.

**No JavaScript copy of the rules.** Each result cell posts on Enter/blur (`hx-post`, `hx-trigger="change"`). The server saves a draft and computes the flag and any dependent calculated rows. It returns the re-rendered rows (`hx-swap-oob` for the calculated ones). That's a LAN round trip of about 20–50 ms, and it means the colour on screen is always exactly what's stored. Results aren't part of the offline counter (§9), so no offline copy is needed.

### Colours (screen only; the printed PDF keeps bold + H/L per §7)
| State | Cell (Tailwind/Basecoat) | Badge | Meaning |
|---|---|---|---|
| Not entered | white | — | |
| Normal `N` | faint green `bg-green-50` | ✓ | inside range |
| Borderline (band) | amber `bg-amber-100` | `Borderline high` | inside or near range but a guideline tier flags it |
| Low `L` | blue `bg-sky-100 text-sky-900` | ↓ L | below range |
| High `H` | red `bg-red-100 text-red-900` | ↑ H | above range |
| Critical `LL`/`HH` | solid `bg-red-600 text-white font-bold` | ⚠ LL / HH | beyond critical limit; dialog opens |
| Abnormal text `A` | amber `bg-amber-100` | A | abnormal option chosen |
| Not calculable | grey italic | — | formula validity failed |
| Focused cell | 2 px outline ring only | | never a fill colour, so it can't be mistaken for a flag |

- **Colour is never the only signal** (WCAG 1.4.1, colour-blind staff): every coloured state also has its badge text or arrow.
- Colours are CSS tokens in one place (`flag-normal`, `flag-high`, …), so a lab can retheme them.
- A legend sits under the grid.

### Result grid mockup (worklist ▸ visit V-000123 · 45 Y / M)
```
 Test / parameter        Result          Unit    Bio. ref. interval        Prev (12-Aug)
 ── LIPID PROFILE ──────────────────────────────────────────────────────────────────────
 Total cholesterol      [ 215.0 ] ↑H     mg/dL   < 200                      198 (+9%)
 Triglycerides          [ 120.0 ] ✓      mg/dL   < 150                      140
 HDL cholesterol        [  48.0 ] ✓      mg/dL   > 40                        45
 LDL (calc.)              143.0  Near opt. mg/dL < 100 optimal  ⓘ           130
 VLDL (calc.)              24.0  ✓       mg/dL   < 30
 TC / HDL (calc.)          4.48  ✓               < 4.5
 ── URINE ROUTINE ──────────────────────────────────────────────────────────────────────
 Colour & appearance    [Straw yellow, clear ▾] ✓
 Albumin                [Nil ▾]  ✓
 Crystals               [Calcium oxalate (+) ▾] A
 Pus cells              [ 01-03 ]  ✓     /hpf    0 – 5
 ───────────────────────────────────────────────────────────────────────────────────────
 Legend: ✓ normal  ↑H high  ↓L low  ⚠HH/LL critical  A abnormal  (calc.) auto, read-only
 [Save draft]  [Submit for verification]                  0 critical · 1 high · 1 abnormal · 0 missing
```
(The `ⓘ` opens the full tier text instead of truncating it. Cells are coloured per the table above.)

### Keyboard flow (front desk add-test and result grid)
- **Test field:** an exact code match comes first, then code prefix, then fuzzy name (`pg_trgm`). The confirm line shows the full name and price before Enter adds it; F2 opens the searchable list. Adding a package/panel expands all its parameters at once.
- **Result grid:** Enter moves to the next *editable* cell, skipping calculated rows. Option cells take typeahead (`n` → Nil). Esc reverts the cell.
- **Default options** (e.g. `Nil`) appear greyed as "default, not confirmed". "Submit for verification" lists every unconfirmed default, so nothing is released by accident.

### Other suggestions folded in
- **Previous value + % change** beside each row (M11). Automatic delta-check *rules* stay deferred.
- **Missing-value counter** before submit, and partial submit per test (pending tests listed on the report, §6).
- **Draft auto-save per cell**, so a browser crash loses nothing. Every change after verification is audited, with a reason.
- **Unapproved range warning:** a starter range not yet approved by the pathologist shows a small "range unapproved" mark on screen, and report release is blocked until it's approved (setting, default on).

**Tests:**
- `compute_flag` table tests: each branch, one-sided ranges, age-in-days boundaries, bands, options, absurd refusal.
- Friedewald invalid at TG 400.
- Range copy-on-entry survives a later range edit.
- The HTMX row endpoint returns the right CSS class and badge for each state.
- A Playwright test types a lipid panel and checks the calculated rows update and the colours match.
- Print PDF contains no colour fills, only bold + H/L (pdfplumber).

## 1e. Live example: one patient through the minimal version (owner request 2026-10-05)
This walks one patient through the whole minimal version. Everything in it is **synthetic** (names, numbers, labs); the same story becomes the seed data, the Playwright end-to-end test (§1a verification) and the manual's "A day at the lab" page (§13a). Tracker IDs are shown in brackets.

**Cast:**
- **Main lab** `MAIN`; **Branch 2** `B2` (collection centre)
- **Priya:** B2 front desk
- **Suresh:** main-lab technician
- **Dr Meera Nair, MD:** signatory
- **Owner:** Anil
- **External labs:** Ext Lab A and Ext Lab B

### Step 1 · 08:40 · Branch 2 front desk: one-screen visit [M18, M03, M04, M05.1, M07]
Priya types the phone number. A patient is found by phone + name [M19], so there's no duplicate. She types `sf` and the confirm line shows "Glucose, fasting · ₹80" before Enter adds it. Then `lipid`, `ur` and `vitd`.
```
┌ New visit · B2 ───────────────────────────────────────── Alt+S save ┐
│ Patient  Arjun Rao (P-000456) · 58 Y / M · 98xxxxxx01  [History ▸]   │
│ Ref. by  [dr kum▾] Dr K. Kumar        (+ new doctor inline, F2 list) │
│ Tests    code [vitd      ]  ▸ Vitamin D (25-OH) · ₹1,200  [Enter]    │
│   sf     Glucose, fasting               80.00  in-house              │
│   lipid  Lipid profile (6 parameters)  500.00  in-house              │
│   ur     Urine routine (9 parameters)  150.00  in-house              │
│   vitd   Vitamin D (25-OH)           1,200.00  outsourced ★          │
│ Discount 10 %  reason [Senior citizen ▾]           − 193.00          │
│ Net ₹1,737.00   Paid [UPI ▾] [1000] UTR 4271…   Due ₹737.00          │
│ Promised  Sun 06-Oct 18:00 (latest test TAT)   Mode (•) Walk-in      │
│ Footer note (printed) [Fasting 12 h confirmed]  Internal [—]         │
│ [x] Consent: testing + sharing with referral lab   [Save & print ▸]  │
└──────────────────────────────────────────────────────────────────────┘
```
On Save, Labra:
- issues the bill of supply `B2/2627/00123`, the receipt and **3 barcode labels**, one per container: grey fluoride, gold SST, urine
- writes the audit log
- creates 4 `order_test` rows

### Step 2 · 08:50 · Collection [M08, M01.2, M21]
Priya scans each tube label → status `collected`, with "collected by" = the phlebotomist, who has no login [M01.2]. At 11:00 the courier takes the box to the main lab.

### Step 3 · 11:45 · Main lab intake and routing [M09, M10, M21]
Suresh scans the tubes → `received`. The in-house tests go to the Biochemistry and Clinical Pathology worklists. Vitamin D shows the routing choice, picked manually in the minimal version:
```
Vitamin D (25-OH) · patient price ₹1,200 · promised Sun 18:00
  ○ In-house       not available
  ◉ Ext Lab A      cost ₹600   margin ₹600   TAT 24 h  → ready Sun 12:00 ✓
  ○ Ext Lab B      cost ₹550   margin ₹650   TAT 48 h  → misses promise ✗
                                                        [Confirm route]
```
He picks A and enters their accession no `EXT-998877` at 12:30. The timeline logs `sent` with time and user.

### Step 4 · 14:10 · Result entry [M11, M11.1, M11.2, M05.2]
Suresh opens the visit from the worklist (or by clicking it on the lab TV board [M22]). The patient is male and 58 at collection, so Labra picks the adult-male ranges. Each Enter saves the cell and returns its colour from the server:
```
 ── GLUCOSE, FASTING ────────────────────────────────────────────────────
 Glucose (F)          [ 132 ]  ↑H Diabetic range    mg/dL  70 – 100   prev 118
 ── LIPID PROFILE ───────────────────────────────────────────────────────
 Total cholesterol    [ 215 ]  ↑H                   mg/dL  < 200      prev 198
 Triglycerides        [ 180 ]  ↑H Borderline high   mg/dL  < 150
 HDL cholesterol      [  38 ]  ↓L                   mg/dL  > 40
 VLDL (calc.)            36    ↑H                   mg/dL  < 30       = TG / 5
 LDL (calc.)            141    ↑H Borderline high   mg/dL  < 100 ⓘ    = TC − HDL − VLDL
 TC / HDL (calc.)       5.66   ↑H                          < 4.5
 ── URINE ROUTINE ───────────────────────────────────────────────────────
 Albumin              [Nil ▾]                  ✓
 Crystals             [Calcium oxalate (+) ▾]  A
 Pus cells            [ 2-3 ]                  ✓   /hpf  0 – 5
 …  5 defaults "Nil" greyed, not yet confirmed
```
Colours on screen:

| Row | Flag | Colour |
|---|---|---|
| Glucose, TC, TG, VLDL, LDL, TC/HDL | High | red |
| HDL | Low | blue |
| Crystals | Abnormal option | amber |
| Rest | Normal | faint green |

LDL is above its `high` of 100, so it is flagged High; its band label "Borderline high" shows beside the flag. Amber is only for a value whose flag is `N` and whose band is borderline (flag rule 6), and this visit has none.

The calculated rows (VLDL, LDL, TC/HDL) appeared on their own once TC, TG and HDL were in.

What the guards do:
- **Typo:** if Suresh had typed `1320` for glucose, it's beyond the absurd limit. "Check value" appears, and saving it anyway needs a second confirm, which is audited [M11.2].
- **Critical:** if glucose had been `480`, beyond the critical limit, the cell turns **solid red ⚠HH**. A dialog then requires "informed Dr K. Kumar by phone at 14:12" before he can continue [M11].
- **Submit for verification:** it lists the 5 unconfirmed "Nil" defaults. Suresh confirms them, then submits.

### Step 5 · 15:00 · Verification and partial release [M11, M12, M20]
Dr Meera's queue shows the visit with **6 high · 1 low · 1 abnormal** and the previous values. She verifies, adds the interpretation comment from presets, and clicks **Release**. Only the signatory role can do this.
- Report mode is **combined** (the default) with Vitamin D still pending, so Labra releases **report R-2026-000456, partial**. It's the digital PDF on the letterhead [M17], with:
  - bold values with H/L, no colours (§7)
  - "Pending: Vitamin D (expected Sun 12:00)"
  - QR verify code and SHA-256
- B2 prints it on letterhead paper with the **Print** button (same layout, no letterhead) [M17]. The patient collects it at 17:30, and Priya records the delivery: delivered to the patient, at the counter, by Priya [M21].

### Step 6 · Sunday 12:20 · External result arrives [M10, M21]
Ext Lab A emails a PDF. Suresh uploads it to the visit and ticks "Vitamin D". He optionally types the value `18.2 ng/mL` → **↓L Deficient** (blue), so history and trends work. The timeline logs `received`.

### Step 7 · Sunday 13:00 · Final report [M12]
Dr Meera verifies and releases **R-2026-000456 complete**:
- It's a new version that supersedes the partial one (not an "amendment", since no released value changed).
- Vitamin D is marked `*` "Performed by Ext Lab A (NABL MC-YYYY), accession EXT-998877".
- If the visit had been set to **separate**, the patient would instead get the in-house report plus Ext Lab A's PDF behind a Labra cover page.

The patient collects it and pays the ₹737 due in cash. The receipt prints, the bill status becomes `paid`, and the delivery is logged.

### Step 8 · Throughout · Lab TV board [M22]
```
 LAB STATUS · MAIN · auto-refresh 30 s              Sat 05-Oct 14:20
 ● B2-V-000123  Arjun Rao   4 tests  ◐ partly done  ★1 outsourced  due Sun 18:00
 ● B2-V-000124  …           2 tests  ○ pending                     due Sat 17:00 ⚠ soon
 ● MAIN-V-000310 …          1 test   ● completed  ✓ delivered
```

### Step 9 · 20:00 · Owner's evening check [M13]
Anil opens the reports:
```
 Daily collection · Sat 05-Oct      Cash      UPI     Card    Total     Dues
 MAIN                             8,420   12,300    1,500   22,220    1,200
 B2                               3,100    5,640        0    8,740      737  ← Arjun Rao
 B3                               2,050    3,980        0    6,030        0
 Outsourcing today: 11 tests · cost ₹6,450 · revenue ₹12,900 · margin ₹6,450 (50%)
 Pending tests: 7 (1 overdue)
```

### Step 10 · Automatic, no one clicks [M16, M15]
- **Backups:** at 18:00 the backup timer runs `pg_dump` + files → restic → Google Drive and USB, then pings the healthcheck. A missed run emails Anil.
- **Audit chain:** the nightly job re-verifies the audit-log hash chain.
- **Restore drill:** on the 1st of each month, the latest snapshot is restored into a scratch database.

### What changed hands
Every step above wrote an `audit_log` row, and every outsourcing step an `order_test_event`. So "who did what, when" for this patient is one query: what a NABL assessor asks for, and what the patient-history screen [M19] shows.

## 2. Expansion roadmap after the minimal version (SemVer 0.x)
| Release | Contents |
|---|---|
| **0.1 Foundation** | Repo hygiene (CI, pre-commit, docs site, SECURITY/CONTRIBUTING), Docker Compose, auth + roles + branches, audit log, settings, number series, backups script, synthetic seed data |
| **0.2 Front desk** | Patients, referrers, catalog (tests, parameters, ranges, packages), price lists, visits/orders, **billing** (bill of supply / tax invoice split, payments, dues, refunds, day close), receipts, sample labels |
| **0.3 Lab** | Simple sample status, **routing in-house / external with a ranked suggestion**, worklists, result entry, external PDF upload + optional value entry, verification, **reports** (combined / separate), amended reports, report signing plugin point (signature image by default; lab certificate via pyHanko as a setting, §7.1) |
| **0.4 Offline + operations** | Branch **offline counter** (§9), outage sync, pending-test and turnaround alerts, MIS reports (collection, dues, outsourcing margin), admin screens, price CSV import with preview |
| **0.5 Pilot** | Pilot at the owner's labs on synthetic → real data (real data only on the lab's machine), hardening, operator guide |
| **Later (1.x)** | Full sample tracking with manifests (LT06), email-inbox auto-match of external results (LT07), custom fields and template editor in the UI (LT08), credit accounts and statements (LT09), external lab invoice reconciliation (LT10), permission matrix UI (LT11), internal quality control (Levey-Jennings) (X07), WhatsApp/SMS delivery (X01), FHIR export (LT12), Tally export (LT13) |
| **Later (1.x, signatures)** | Labra Signer agent for personal pathologist DSCs (LT14); optional Aadhaar eSign plugin and DocuSeal/Documenso link-out for agreements (LT15) (§7.1) |
| **Later (2.x)** | Analyzer bridge (HL7 v2 / ASTM) (LT03), ABDM integration (Health Information Provider) (LT04), AI assist (advisory) (LT01, LT02) |

"Light v1" means 0.1–0.4. Everything marked **later** is designed into the data model now, as nullable fields or empty tables where cheap, but not built.

## 3. Architecture
```
            Branch PCs (browser)              Main lab PCs (browser, LAN)
                  │  Cloudflare Tunnel + Access        │
                  ▼                                    ▼
          ┌──────────────── Mini PC at main lab (Docker Compose) ───────────────┐
          │ caddy ─► labra-web (FastAPI + Jinja2/HTMX, admin at /admin)         │
          │          labra-worker (Procrastinate: PDFs, alerts, backups, mail)  │
          │          postgres 18 (data + job queue)   /data/files (PDFs, logos) │
          └──────────────────────────────┬──────────────────────────────────────┘
                                         │ nightly restic (encrypted)
                                         ▼
                                Backblaze B2 / S3 storage
```
- **One application split into modules** (`src/labra/<module>/` with `models.py`, `schemas.py`, `service.py`, `routes.py`, `templates/`). Modules: `core` (settings, numbering, files), `auth`, `org` (branches, users), `patients`, `catalog`, `pricing`, `orders`, `samples`, `routing`, `outsourcing`, `results`, `reports`, `billing`, `sync` (offline), `audit`, `admin`, `fhir` (later), `plugins`.
- **Routes stay thin:** they only handle HTTP. All rules live in `service.py`, so the offline sync path and the API share the same code.
- **Cloud variant:** the same Compose file on Lightsail Mumbai / DigitalOcean Bangalore (2 GB). There the main lab is online-only; branches still get the offline counter.

## 4. Stack and software
Rule: every piece is MIT/BSD/Apache/PSF-licensed, Python-first and light enough for a mini PC. No Redis, Kafka or Kubernetes.

| Area | Choice |
|---|---|
| Runtime | Python 3.13+, FastAPI, Pydantic v2, pydantic-settings (env/`.env` only) |
| Database | PostgreSQL 18 (supported to Nov 2030), SQLAlchemy 2.x **sync** + psycopg 3, Alembic migrations |
| Jobs | Procrastinate (job queue and scheduler that lives in Postgres) |
| UI | Jinja2 + **HTMX** + Alpine.js pages rendered on the server, styled with **Basecoat UI** (MIT): the **shadcn/ui design system rebuilt as plain Tailwind CSS classes + small vanilla JS**, with ready Jinja macros, compatible with shadcn themes. CSS vendored into `static/` (no CDN, so the LAN works offline); Tailwind standalone CLI (no Node in production) |
| Why not shadcn/ui itself | shadcn/ui is React components (Radix). Using it means a React app built with Node, a JSON API for every screen, and twice the code to maintain. Basecoat gives the same look on the HTMX stack. If a React front end is ever wanted, the `service.py` layer already supports adding a JSON API alongside |
| UI look for admin | Same Basecoat look as every other screen (ADR-0010) |
| Admin | Own HTMX screens (ADR-0010), including price import, template management and permissions |
| Auth | Session cookies, argon2-cffi (used directly, with `check_needs_rehash`), pyotp two-factor login for signatories/admins, roles scoped to branches |
| PDF | Jinja2 sandboxed templates → **WeasyPrint** |
| PDF signing | **pyHanko** (MIT): PAdES signatures with PKCS#12/PKCS#11, RFC 3161 timestamps, validation (§7.1) |
| Codes | python-barcode (Code 128 labels), segno (UPI and verification QR) |
| Mail | imap-tools (results inbox, later), smtplib (send reports) |
| Standards | fhir.resources (later); LOINC/SNOMED/UCUM as data, not libraries |
| Files | csv (import/export) + DuckDB (Parquet, M26); XlsxWriter for Excel export when X21 is built; files stored on a local volume, content-addressed by SHA-256 |
| Logs / monitoring | structlog JSON (IDs only, never patient data), Uptime Kuma, optional GlitchTip |
| Offline counter | Service worker + IndexedDB (small vanilla JS/Alpine module) |
| Ops | Docker Compose, Caddy, cloudflared, restic → B2 |
| Dev | uv, ruff, pyright, pytest + testcontainers (real Postgres) + hypothesis (money maths) + plain factory functions over Faker + Playwright, gitleaks, pip-audit, osv-scanner, GitHub Actions (pinned by SHA), Zensical docs site, Faker seed data |

**Hardware:**
- Server: **old laptop** (old-gen AMD, 4–8 GB RAM, SSD swapped in, Debian/Ubuntu Server without desktop); see §1a. A mini PC (N100 class) is an optional future upgrade.
- Branches: any PC with Chrome or Edge, a USB barcode scanner, a label printer (50×25 mm) and an A4/thermal printer.

**Conventions:**
- Time is stored in UTC and shown in IST.
- Money is `Decimal(12,2)`, calculated in one module, with each line rounded and the bill rounded off at the end (round-off unit and currency display are settings, §8).
- UI text is ready for translation (Babel).

## 5. Data model (Postgres)
**Conventions on every table:**
- **IDs:** UUID primary key `id`, generated by the app (v7, time-ordered) so offline devices can create rows safely.
- **Metadata columns:** `created_at`, `created_by`, `updated_at`, `updated_by`, `row_version` (optimistic locking).
- **Branch scoping:** business tables carry `branch_id`.
- **No hard deletes:** soft cancel or deactivate instead.
- **Offline-capable tables:** they also carry `origin_device_id` and `client_ref` (idempotency key).
- `extra JSONB` exists on patient, visit and bill for later custom fields.

### 5.1 Organisation, access, configuration
| Table | Key columns |
|---|---|
| `lab_profile` (1 row) | legal_name, display_name, logo_file_id, pan, default_state_code, support_phone |
| `branch` | code (`MAIN`, `B2`), name, kind (`main_lab`/`collection_centre`), address, state_code, phone, email, gstin, nabl_cert_no, nabl_valid_to, letterhead_template_id, is_active |
| `app_user` | username, full_name, phone, email, password_hash, totp_secret_enc, is_active, last_login_at |
| `role` | code (`front_desk`, `phlebotomist`, `technician`, `signatory`, `branch_manager`, `admin`), name, is_system |
| `role_permission` | role_id, permission_code (`bill.discount.approve`, `report.release`, `price.edit`, ...) |
| `user_branch_role` | user_id, branch_id, role_id |
| `signatory` | user_id, qualification, council_reg_no, signature_file_id, department_ids[] |
| `setting` | key, scope (`instance`/`branch`), scope_id, value JSONB; precedence branch > instance (per-case values live on the record itself) |
| `number_series` | branch_id, doc_type (`patient`,`visit`,`sample`,`bos`,`tax_inv`,`receipt`,`refund`,`credit_note`,`report`,`manifest`), format (`{BR}/{FY2}/{SEQ:5}` → `B2/2627/00123`; bill/invoice/credit-note formats are refused if they can render longer than **16 characters**, GST Rule 46/49), fin_year, next_value |
| `device` | branch_id, name, offline_enabled, last_sync_at, revoked_at |
| `number_block` | device_id, series_id, range_start, range_end, used_upto (numbers handed out in advance for offline use, §9) |

### 5.2 Patients, consent, referrers
| Table | Key columns |
|---|---|
| `patient` | patient_no, registered_branch_id, title, full_name, sex (`M`/`F`/`O`), dob, dob_is_estimated, phone, alt_phone, email, address, city, pincode, abha_number (later), extra, merged_into_id |
| `consent_notice` | version, language, body_text, effective_from |
| `patient_consent` | patient_id, notice_id, purpose (`testing`,`referral_lab_sharing`,`report_delivery`), given_at, channel, withdrawn_at |
| `referrer` | kind (`doctor`/`clinic`/`hospital`/`corporate`/`self`), name, qualification, council_reg_no, phone, is_active |

Age is stored as a DOB, estimated from the stated age if needed. Reports show the age calculated at collection time.

### 5.3 Catalog and pricing
| Table | Key columns |
|---|---|
| `department` | name (Haematology, Biochemistry, Clinical Pathology, Serology/Immunology, Microbiology, Histopathology), report_order |
| `specimen_type` | code, name, container (`EDTA lavender`, `SST gold`, `Fluoride grey`, `Citrate blue`, `Urine container`), snomed_code |
| `test` | code (unique short mnemonic, e.g. `hb`, `sf`, `lipid`), aliases[], name, short_name, department_id, specimen_type_id, kind (`single`/`panel`), method, loinc_code, default_tat_hours, in_house_available, gst_category_id, nabl_in_scope, interpretation_text, research_use, is_active |
| `test_parameter` | test_id, code, name, result_type (`numeric`/`text`/`option`/`calculated`), unit_ucum, decimals, formula, formula_valid_if (e.g. `TG < 400`), options JSONB (`[{"value": "Nil", "abnormal": false, "default": true}, ...]`), loinc_code, display_order, is_reportable |
| `reference_range` | parameter_id, sex, age_min_days, age_max_days, low, high (either may be null: one-sided limits like HDL `> 40`), critical_low, critical_high, absurd_low, absurd_high, display_text, source_citation, approved_by/at, valid_from (§1d) |
| `reference_band` | range_id, low, high, label (`Optimal`, `Near optimal`, `Borderline high`, ...), severity (`normal`/`borderline`/`abnormal`), display_order: interpretation tiers such as lipid categories (§1d) |
| `package` | code, name, description, gst_category_id, is_active |
| `package_item` | package_id, test_id |
| `gst_category` | name, kind (`exempt`/`taxable`), sac_code, rate_pct |
| `price_list` | name, kind (`walk_in`/`camp`/`corporate`/`home`), branch_id (null = all), is_default, valid_from, valid_to |
| `price_list_item` | price_list_id, item_type (`test`/`package`), item_id, price, valid_from, valid_to; price changes close the old row and add a new one, never overwrite |

### 5.4 External labs (outsourcing)
| Table | Key columns |
|---|---|
| `external_lab` | name, nabl_cert_no, contact_name, phone, email, results_email, portal_url, dpa_signed_on, is_active |
| `external_lab_rate` | external_lab_id, test_id, their_test_code, cost, tat_hours, valid_from, valid_to |

### 5.5 Visits, orders, samples
| Table | Key columns |
|---|---|
| `visit` (one patient case) | visit_no, branch_id, patient_id, referrer_id, price_list_id, collection_mode (`walk_in`/`home`), clinical_notes, provisional_dx_icd10, report_mode (`combined`/`separate`/`both`, default from setting), priority (`routine`/`urgent`), status (`open`/`completed`/`cancelled`), origin_device_id, client_ref |
| `order_item` (billable line) | visit_id, item_type, test_id/package_id, list_price, discount_amt, net_price, status (`active`/`cancelled`), cancel_reason |
| `order_test` (one test to perform; packages expand into these) | visit_id, order_item_id, test_id, sample_id, route (`in_house`/`external`), external_lab_id, external_cost, external_accession_no, route_reason, routed_by/at, status (`ordered`→`collected`→`in_lab`/`sent_out`→`resulted`→`verified`→`released`, or `cancelled`), due_at |
| `sample` | sample_no (barcode), visit_id, specimen_type_id, collected_at/by, received_at/by (main lab), status (`collected`/`received`/`rejected`/`redraw`), rejection_reason, remarks (haemolysed / lipaemic / delayed; printed on the report, §7.0) |
| `manifest` / `manifest_sample` (later; table created in 0.3) | manifest_no, from_branch_id, to_kind (`branch`/`external_lab`), to_id, dispatched_at/by, courier, received_at/by |

With full sample tracking off (the default), `sample.status` plus `order_test.status` are enough. Turning it on enables manifests, scan steps and rejection workflows.

### 5.6 Results and reports
| Table | Key columns |
|---|---|
| `result` | order_test_id, parameter_id, value_num, value_text, unit, flag (`N`,`L`,`H`,`LL`,`HH`,`A`), band_label (e.g. `Borderline high`), ref_range_text + ref_low/ref_high/crit_low/crit_high (copied at entry), source (`manual`/`external_pdf`/`import`/`analyzer`), comment, entered_by/at |
| `external_document` | visit_id, external_lab_id, file_id, sha256, received_via (`upload`/`email`), email_message_id, received_at, match_status (`matched`/`unmatched`) |
| `external_document_test` | external_document_id, order_test_id |
| `verification` | order_test_id, level (1, or 2 if configured), verified_by, verified_at, note |
| `report` | report_no, visit_id, version, kind (`combined`/`in_house`/`external_forward`), status (`draft`/`released`/`amended`/`withdrawn`), released_by (signatory), released_at, file_id, sha256, supersedes_report_id, amendment_reason, verify_token |
| `report_test` | report_id, order_test_id |
| `report_signature` | report_id, method, signer_user_id, cert_subject/serial/issuer/valid_to, signed_at, tsa_time, signed_file_id, sha256 (§7.1) |

### 5.7 Billing
| Table | Key columns |
|---|---|
| `bill` | bill_no, doc_type (`bill_of_supply`/`tax_invoice`), branch_id, visit_id, bill_to (`patient`/`account`), credit_account_id, bill_date, place_of_supply_state, gross, discount, taxable_value, cgst, sgst, igst, round_off, net, paid, due, status (`open`/`paid`/`cancelled`), origin_device_id, client_ref |
| `bill_line` | bill_id, order_item_id, description, sac_code, gst_rate, rate, discount, taxable, cgst, sgst, igst, amount |
| `discount_approval` | visit_id, requested_by, approved_by, kind (`pct`/`amount`), value, reason, approved_at |
| `payment` | receipt_no, branch_id, bill_id (null = advance), patient_id/credit_account_id, mode (`cash`/`upi`/`card`/`cheque`/`credit`), amount, reference (UTR/last-4), received_by/at, origin_device_id, client_ref |
| `refund` | refund_no, bill_id, amount, mode, reason, requested_by, approved_by, credit_note_no (for tax invoices) |
| `day_close` | branch_id, user_id, business_date, expected JSONB (per payment mode), counted JSONB, variance, note, closed_at, locked |
| `credit_account` (later UI) | name, kind (`corporate`/`tpa`/`hospital`/`clinic`), gstin, credit_limit, terms_days, price_list_id |
| `external_lab_invoice` / `_line` (later) | lab invoice header and lines, matched to `order_test` |

### 5.8 Templates, custom fields, audit, sync, files
| Table | Key columns |
|---|---|
| `template` | kind (`report`/`bill_of_supply`/`tax_invoice`/`receipt`/`label`/`manifest`/`letterhead`), branch_id (null = all), name, version, body_html, css, status (`draft`/`published`), published_by/at |
| `field_definition` (later UI) | entity, key, label, type, options, required, display_order |
| `audit_log` | id bigserial, at, user_id, branch_id, device_id, action, entity, entity_id, before JSONB, after JSONB, ip, prev_hash, hash. **Append-only:** a database trigger blocks UPDATE/DELETE, and a hash chain makes tampering detectable |
| `sync_batch` | device_id, client_ref, payload JSONB, received_at, status (`applied`/`duplicate`/`needs_review`/`failed`), result JSONB |
| `stored_file` | sha256, path, mime, size, kind, created_at |

**Fixed compliance rules (cannot be configured away):**
- the audit log
- release only by an authorised signatory
- naming the referral lab on reports
- copying reference ranges into the result at entry
- issuing an amended version instead of editing a released report
- PC-PNDT: no fetal-sex fields anywhere
- consent captured before referral-lab sharing

## 6. Key workflows
1. **Front desk (branch):**
   - Find or create the patient and capture consent.
   - Create the visit (referrer, price list), add tests/packages, apply a discount (approval if over the role's limit).
   - Bill and take payment (full, part or advance); print the receipt and sample labels (one per specimen/container).
2. **Collection:** label tubes, mark collected, and send to the main lab (a manifest if tracking is on).
3. **Main lab intake:** scan the sample and mark it received. Each `order_test` shows its **route suggestion**:
   ```
   Sample B2-2026-000123 · HbA1c          patient price ₹450
     ◉ In-house            cost  ₹90   margin ₹360   TAT 4h
     ○ Ext. lab A          cost ₹160   margin ₹290   TAT 24h
     ○ Ext. lab B          cost ₹140   margin ₹310   TAT 48h
   Strategy: best margin (Settings ▸ Routing)        [Confirm route]
   ```
   The ranking strategy is configurable (`best_margin`, `cheapest`, `fastest`, `preferred`) as a plugin point. The operator can override it, giving a reason.
4. **In-house:** department worklist → result entry (flags calculated from the copied reference range; critical values highlighted) → verification.
5. **External:**
   - Mark the test sent out, recording the lab and their accession number.
   - When the result arrives (portal download or email), upload the PDF to the visit and tick the tests it covers.
   - Optionally type in the values so history and trends work; then verify.
6. **Release:** a signatory releases the report. The report mode (combined / separate / both) defaults from settings and can be changed per visit. Partial reports are allowed, listing the pending tests.
7. **Delivery:** print, download, or email the PDF (WhatsApp later). The patient can verify a report by scanning its QR code (the verify page shows report number, version and issue date only; no results).
8. **Day close:** each counter user closes their day per payment mode; the branch manager signs it off.

## 7. Report format (A4 PDF, Jinja2 → WeasyPrint)
```
┌──────────────────────────────────────────────────────────────────────┐
│ [Logo]  <LAB DISPLAY NAME>  ·  Main Lab, <address>, <phone>           │
│         NABL Cert No. MC-XXXX (shown only when tests on the page      │
│         are in scope; per-branch letterhead template)                 │
├──────────────────────────────────────────────────────────────────────┤
│ Patient : <Name>            Age/Sex : 34 Y / F      Patient ID : P-..│
│ Visit No: B2-V-2026-000123  Ref. by : Dr <name>     ABHA : (optional)│
│ Collected: 05-Oct-26 09:10 (Branch 2)  Received: 05-Oct-26 11:02      │
│ Reported : 05-Oct-26 16:45  Sample: EDTA whole blood, Serum           │
├──────────────────────────────────────────────────────────────────────┤
│ HAEMATOLOGY                                                           │
│ Test                      Result     Unit      Bio. Ref. Interval     │
│ Haemoglobin               11.2  L    g/dL      12.0 – 15.5            │
│ Total WBC count           7,800      /µL       4,000 – 11,000         │
│ ...                                                                    │
│ BIOCHEMISTRY                                                          │
│ HbA1c *                   6.1   H    %         4.0 – 5.6              │
│ Method: HPLC                                                          │
│ Interpretation: <configured text per test>                            │
├──────────────────────────────────────────────────────────────────────┤
│ * Performed by Ext. Lab A (NABL MC-YYYY), accession EXT-998877.       │
│ Pending: Vitamin D (expected 07-Oct-26).                              │
│                                                                       │
│ [signature]  Dr <Name>, MD (Pathology), Reg. No. <council no>         │
│ ---------------------------- End of Report ------------------------- │
│ Report No R-2026-000456 v1 · Page 1 of 2 · [QR verify]                │
│ Results relate only to the sample received. Not for medico-legal use. │
└──────────────────────────────────────────────────────────────────────┘
```
- **Abnormal values** print in bold with H/L; critical values print as HH/LL.
- **Amended reports** carry a banner: "AMENDED: supersedes v1 (reason)".
- **Separate mode** issues one report for in-house tests plus the external lab's PDF forwarded as-is, with a cover page on Labra letterhead listing the referral lab.
- **Combined mode** puts everything in one report, with outsourced tests marked `*`.

### 7.0 Report layout v2 (reference review + research, 2026-10-05)
The owner shared a commercial product's printed report as a reference (never named or copied, §1c).

**Worth keeping:**
- Boxed department sections.
- Panel sub-headings (Lipid profile, Widal, Macroscopic / Microscopic).
- A barcode top right.
- A separate arrow column for flags.
- Interpretation tiers shown with the range.

**What to do better:**
| Seen in the reference | Problem | Labra |
|---|---|---|
| Triglycerides 120 printed with ↓, under a range written as "> 150 Suspect / > 200 Increased" | **Wrong flag on a normal value**: free-text ranges can't drive flags | Flags only from numeric ranges and bands (§1d); range text is generated from the same numbers |
| Every result bold | Abnormal values don't stand out | Only flagged values bold, plus H / L / HH / LL text in the flag column |
| Specimen ("SERUM") repeated on every row | Wastes a column | Specimen and method once, in the panel heading: `LIPID PROFILE · Serum · Enzymatic` |
| Five-line tier text in the range column (LDL, HDL) | Tall rows, mostly white space, more pages | One line in the column (`Optimal < 100`), full tier table in a small box under the panel, printed once |
| `mgs/dl`, `NIL (BLUE)` | Typos and reagent notes leak into results | UCUM unit picklist; option values are clean text |
| Only "date of visit / date of report" | ISO 15189 needs collection date on every page; NABL expects received and reported times | Collected / received / reported date-times on every page header |
| No signatory, method, sample ID, page x of y or end mark | Fails ISO 15189 §7.4.1.6 (j), (f), (m) | All present (checklist below) |

**ISO 15189:2022 §7.4.1.6 checklist.** The report template can't be published unless each item is placed. A test renders the dummy data and checks each one with pdfplumber.
| Item | Labra field / place |
|---|---|
| a) Unique patient ID; collection date and report date **on every page** | Running page header: name, `patient_no`, age/sex, collected, reported |
| b) Issuing lab | Letterhead / branch block; NABL no when in scope |
| c) Requester | "Ref. by" (referrer) |
| d) Primary sample type and description | Panel heading specimen; sample no; remarks |
| e) Examinations clearly identified | Test name (+ LOINC optional, not printed) |
| f) Method where relevant | `test_method` default, in the panel heading |
| g) Results with units | Result + UCUM unit |
| h) Reference intervals / decision limits | Range column + tier box |
| i) Research-use examinations marked | `test.research_use` flag → footnote |
| j) Who reviewed and released | Signatory block (name, qualification, council reg no) |
| k) Preliminary results marked | "PARTIAL REPORT" banner + pending list (§6) |
| l) Critical results indicated | `HH` / `LL` + "Critical value informed to … at …" line |
| m) All parts identifiable; end marked | `Report R-… v2 · Page 1 of 2`, "End of report" |
| §7.4.1.7 Sample quality comments | `sample.remarks` (haemolysed, lipaemic, delayed) printed above the affected panel |
| §7.4.1.8 Amendments | "AMENDED: supersedes v1 (reason)" banner, date/time/user, old version kept |

**Layout rules:**
- **Columns:** Test · Result · Flag · Unit · Bio. ref. interval. Specimen and method sit in the panel heading.
- **Page breaks:**
  - A panel is never split if it fits on one page.
  - When a panel must split, the column header repeats and the panel heading gets a "(continued)" label.
  - The signature appears only on the last page.
- **Order:** department `report_order` first, then the test's `display_order`.
- **Text-only results** (Widal, urine microscopy) skip empty unit and range cells, and use the width for the value.
- **Calculated rows** are marked `(calc.)`.
- **No colours on the printed report** (owner rule): bold and the flag letters carry the meaning. Colour stays on screen (§1d) and in the later smart layout (X03), which is decided separately.
- **Optional "Abnormal results at a glance" box** at the top of page 1 [M20.1], one line per flagged value. This is the summary-page pattern Indian chains use in their smart reports, shrunk to a box. Setting, off by default.

```
 ┌ Patient Arjun Rao · P-000456 · 58 Y / M   Ref. by Dr K. Kumar       [barcode] ┐
 │ Collected 05-Oct-26 08:50 (B2) · Received 11:45 · Reported 05-Oct-26 15:00     │
 ├────────────────────────────────────────────────────────────────────────────────┤
 │ ABNORMAL AT A GLANCE (optional): Glucose (F) 132 H · Cholesterol 215 H ·       │
 │ Triglycerides 180 H · HDL 38 L · LDL 141 (Borderline high)                      │
 ├────────────────────────────────────────────────────────────────────────────────┤
 │ BIOCHEMISTRY                                                                    │
 │ LIPID PROFILE · Serum · Enzymatic colorimetric                                  │
 │ Test                    Result   Flag  Unit    Bio. ref. interval               │
 │ Total cholesterol       **215**   H    mg/dL   < 200                            │
 │ Triglycerides           **180**   H    mg/dL   < 150                            │
 │ HDL cholesterol          **38**   L    mg/dL   > 40                             │
 │ LDL (calc.)               141          mg/dL   Optimal < 100 ¹                  │
 │ VLDL (calc.)               36    H    mg/dL   < 30                             │
 │ ¹ LDL: < 100 optimal · 100–129 near optimal · 130–159 borderline high ·         │
 │   160–189 high · ≥ 190 very high   → this result: Borderline high              │
 │ ...                                                                             │
 │ [signature]  Dr Meera Nair, MD (Pathology), Reg. No. ……                         │
 │ Report R-2026-000456 v2 · Page 1 of 2 · [QR] · End of report on page 2          │
 └────────────────────────────────────────────────────────────────────────────────┘
```

### 7.1 Digital signatures on reports
**What the law and NABL need:**
- Under the IT Act 2000, the legally recognised electronic signatures are a **DSC (Digital Signature Certificate) from a licensed Certifying Authority** and **Aadhaar eSign**.
- A scanned signature image or a click-to-sign is evidence, not an IT-Act "electronic signature".
- NABL/ISO 15189 needs a controlled, identifiable authorisation of each report. Labra's signatory release + audit log already provides that.
- Get a lawyer or CA to confirm what Labra's docs claim.

**Options compared** (assumed volume: 3 branches, about 2,000–2,700 reports/month):
| Method | What it proves | Cost | Extra infrastructure | Works offline? | Fit |
|---|---|---|---|---|---|
| **A. Signature image + release audit + QR verify** (baseline) | Who released the report (audit log); hash + QR verify page shows tampering | ₹0 | none | yes | **v1 default.** Most small Indian labs work this way |
| **B. Lab "Document Signer" certificate (Class 3, organisation)**, auto-signs every released PDF | Report came unaltered from *the lab* (PAdES signature, recognised by Adobe Reader) | about ₹10,250/yr (~₹850/month) | **pyHanko** library (MIT, no extra container). Certificate on the mini PC as a USB token/PKCS#11 or protected file; confirm the CA's storage rules (some require a hardware token or HSM) | yes (signing is local; the timestamp is added later when online) | **Recommended upgrade.** Low cost, fully automatic |
| **C. Personal Class 3 DSC per pathologist (USB token)** | *That doctor* signed this report | about ₹1,300–2,200/yr per signatory with token (₹3–4.5k/yr for 2) | Browsers can't use USB tokens, so a small **Labra Signer agent** (pyHanko + PKCS#11, packaged Windows app) runs on the signatory's PC: pulls released reports, one PIN for a batch, uploads signed PDFs. Needs token drivers (ePass2003 / ProxKey / HYP2003) | yes | Strongest per-doctor proof; pathologists often already own a DSC. **1.x** |
| **D. Aadhaar eSign through an eSign provider** | Signer identified by Aadhaar OTP | about ₹3–25 per signature, usually with monthly minimums → about **₹22k–40k/month** at this volume | Provider contract + API keys; internet and OTP for every signing | **no** | Too costly and slow for reports. Possibly for one-off consent or agreements, as a plugin |
| **E. DocuSeal / Documenso / OpenSign** (open-source DocuSign alternatives) | Click or drawn e-signatures with an audit trail; Documenso can also seal PDFs with a PKCS#12 certificate | Free self-hosted (AGPL-3.0). Hosted plans or Pro features about $20–25/user/month | **+1 container** (DocuSeal: Ruby on Rails; Documenso/OpenSign: Node), about 0.5–1 GB RAM, its own database/SMTP/updates | partly (local only) | **Not for reports.** They're for collecting signatures from other people on contracts. Useful later for **external lab data-processing agreements and staff agreements**, as a separate service (or just their cloud plans), linked by URL/API. Never embed their AGPL code in MIT Labra |

The project you forgot is most likely **Documenso** (or OpenSign); both are in the table.

**Recommendation:**
- **v1 (0.3):** A. Signature image + release audit + report SHA-256 + QR verify page, plus a `labra.report_signers` plugin point with built-in signers: `none` (default) and `pkcs12/pkcs11` (pyHanko PAdES). Option **B** is then just configuration: buy the Document Signer certificate, upload or plug it in, switch the setting.
- **1.x:** C, the Labra Signer agent for personal DSCs.
- **Optional plugins:** D (Aadhaar eSign) and E (link-out to DocuSeal/Documenso) for agreements, not reports.

**Implementation details:**
- Signing happens **after** the PDF render and **before** the report status becomes `released`, so a released report is always signed when signing is enabled.
- Use the PAdES baseline profile, a visible signature box next to the signatory block, and the full certificate chain (India CCA root) embedded.
- **RFC 3161 timestamp:** from the CA's timestamp service if the certificate includes one, else a configured timestamp server. If offline at release, the report is still signed; a background job adds the timestamp when the internet returns. A `pending_timestamp` flag shows in the UI.
- **Amended reports** are new versions, signed fresh. Earlier signed versions are kept.
- Certificate expiry warnings at 30 and 7 days. The certificate PIN/password comes from env/secret only, never stored in the database.
- **New table `report_signature`:** report_id, method (`image`/`org_cert`/`personal_dsc`/`aadhaar_esign`), signer_user_id, cert_subject, cert_serial, cert_issuer, cert_valid_to, signed_at, tsa_time, signed_file_id, sha256.
- **Tests:** sign with a test PKCS#12 made from a throwaway test certificate authority. Validate with pyHanko: signature intact, editing the signed PDF breaks validation, and an offline release gets its timestamp added later.

### 7.2 Letterhead background and margin calibration (minimal version)
**Problem:** labs print on **pre-printed letterhead paper**, but send **digital PDFs** (WhatsApp/email/download) that must look the same. The data must fit inside the blank area of the letterhead, both ways.

**One layout, two outputs:**
| Output | Letterhead | Used for |
|---|---|---|
| **Digital PDF** | Letterhead drawn behind the content | download, email, WhatsApp, the stored copy of a released report |
| **Print PDF** | No letterhead, content at **exactly the same position** | printing on pre-printed letterhead paper |
| Plain-paper print (option) | Letterhead included | labs with no pre-printed stock |

The front desk picks the output with two buttons on the report/bill screen: **[Download / Send]** (digital) and **[Print on letterhead paper]** (print). The default print mode is a per-branch setting.

**How the letterhead is applied:**
**Accepted formats and file size** (researched 2026-10-05):
- **What PDF can store:** images only as JPEG (DCT), Flate (lossless, PNG-like), JPEG 2000, JBIG2 or CCITT. **WebP doesn't exist inside a PDF.** WeasyPrint decodes any non-JPEG raster through Pillow and re-encodes it as PNG/Flate (since v54). A WebP letterhead therefore usually ends up **larger** in the PDF than the same image saved as JPEG. **WebP gives no size benefit**: accept it on upload for convenience, but always convert it (below).
- **WeasyPrint:** JPEGs are embedded as-is, not re-encoded, unless `jpeg_quality`/`dpi` is set. **SVG is rendered as vectors**, not rasterised. Size options are `optimize_images`, `jpeg_quality` (0–95) and `dpi` (maximum image resolution).
- **pypdf:** `compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)` merges duplicated objects. The pypdf docs don't say whether stamping the same letterhead on several pages duplicates the image, so Labra calls this before saving every time. A test checks the letterhead is stored **once**.

**Preference order, shown to the admin on the upload screen:**
| Rank | Format | Typical PDF overhead | Notes |
|---|---|---|---|
| 1 | **SVG** (exported from the designer's CorelDRAW/Illustrator/Inkscape file) | about 10–80 KB, sharp at any zoom and in print | Labra **sanitises** it: strips `<script>` and event handlers, and blocks external URLs with a no-network WeasyPrint fetcher. Fonts should be converted to curves/paths before export. A preview catches the rare SVG feature WeasyPrint can't draw |
| 1 | **Vector PDF** (same source file exported as PDF) | about 20–150 KB | Placed under the content with pypdf. A *scanned* PDF is really a big image and goes to rank 3 |
| 3 | **PNG / JPG / WebP** (scan or photo) | about 100–250 KB **after Labra's optimisation** | Optimised automatically on upload (below) |

**Raster optimisation on upload (Pillow):**
1. Fix orientation and strip metadata (EXIF, colour profiles except sRGB).
2. Resize to A4 at **150 dpi (1240 × 1754 px)**. That's enough for a background on screen and print, since the data text stays vector. 200 dpi is a setting.
3. Encode two candidates and **keep the smaller**: **JPEG quality 80** (progressive; best for gradients and photos), and **8-bit palette PNG** (best for flat-colour logos with few colours).
4. Store both the original (for re-processing) and the optimised file. Show **"Original 1.8 MB → used in PDF 140 KB"** with a side-by-side zoom preview, so the admin can see there's no visible loss. A "higher quality" toggle switches to 200 dpi / JPEG 90.
5. Safety net: WeasyPrint renders with `optimize_images=True` and `dpi=200`, so a large image added another way still gets capped.

**Convert to SVG: a suggestion, never automatic** (owner request 2026-10-05):
After a JPG/PNG/WebP or PDF upload, the upload screen shows a suggestion card when conversion could help:
```
┌ Suggestion ─────────────────────────────────────────────────────────┐
│ This letterhead could be smaller and sharper as SVG.                │
│   Current (optimised JPG)  142 KB      SVG (traced)  38 KB          │
│   [Preview side by side, 200% zoom]                                 │
│   [Use SVG]   [Keep current]   (tip: ask your designer for an SVG   │
│                                export of the original file: best)   │
└─────────────────────────────────────────────────────────────────────┘
```
| Source | Converter | Result quality | When Labra suggests it |
|---|---|---|---|
| **Vector PDF** (from CorelDRAW/Illustrator) | `pdftocairo -svg` (poppler-utils, run as a separate command, so its GPL licence doesn't touch Labra's MIT code) | **Exact:** same vectors, text becomes paths | Always offered; lets WeasyPrint draw the letterhead in one pass instead of the pypdf stamp step |
| **Flat-colour PNG/JPG** (logo, lines, a few colours) | **vtracer** (MIT, Python wheel, Rust inside, handles colour scans; potrace is avoided because it's GPL and black-and-white only) | Good for logos and borders; small text can look slightly rounded | Offered only if the traced SVG is **smaller** than the optimised raster **and** a pixel comparison of the two renders is close (similarity threshold in settings) |
| **Photo / gradient / scanned paper texture** | — | Tracing makes it bigger and blotchy | Not offered; the optimised raster is used |

Rules:
- The admin always sees the side-by-side preview and chooses; the original file is kept, so switching back is one click.
- A traced SVG goes through the same sanitiser as an uploaded SVG.
- Tracing runs once at upload (a few seconds on the old laptop, capped by a timeout and a maximum of 1240 × 1754 px input), never during report rendering.
- Docs and the upload screen say plainly: **the best SVG is the designer's own export**; tracing is a fallback.

**How it's applied:**
- **SVG / raster:** WeasyPrint draws it as the `@page` background, in one render.
- **Vector PDF:** WeasyPrint renders the content, then **pypdf** stamps each page on top of the letterhead page.
- **Both:** `compress_identical_objects()` runs, then the PDF is written.

**Size targets (tested):**
- Digital report of 1 page **≤ 300 KB**; 3 pages **≤ 400 KB**.
- **The letterhead is counted once:** 3-page size ≤ 1-page size + 100 KB.
- These keep reports light for WhatsApp, email and mobile data, and keep backups small.
- **Pages:** the letterhead goes on every page (default) or the first page only. A separate continuation-page letterhead comes later.
- The released report's stored copy (with SHA-256 and the QR) is the **digital** version. The print version is generated when needed from the same data and isn't stored.

**Margin calibration screen** (Admin ▸ Letterheads ▸ Report A4 / Bill A4, per branch):
```
┌──────────────── Letterhead: Main Lab · Report A4 ───────────────────┐
│ Letterhead file: [main-lab-lh.pdf ▾] [Upload new]   Pages: (•) All  ( ) First │
│                                                                      │
│ Top margin      [====|----------]  42 mm     ┌───────────────────┐   │
│ Bottom margin   [===|-----------]  30 mm     │ ▓▓ LAB LOGO ▓▓▓▓▓ │   │
│ Left margin     [=|-------------]  15 mm     │ - - - - - - - - - │   │
│ Right margin    [=|-------------]  15 mm     │ Patient: Asha D.. │   │
│ Signature area  [==|------------]  25 mm     │ CBC  Hb 11.2 L .. │   │
│   (reserved above bottom margin)             │ ...               │   │
│ Font size       [===|-----------]  10 pt     │ [sign] Dr ....    │   │
│                                              │ ▓▓ footer address │   │
│ Preview data: (•) Short report ( ) 3-page    └───────────────────┘   │
│               ( ) Long names  ( ) Bill 25 lines   live preview       │
│ [x] Show guide lines (blue: margins, red: signature area)            │
│                                                                      │
│ [Print calibration page]  [Reset]  [Save draft]  [Publish]           │
└──────────────────────────────────────────────────────────────────────┘
```
- **Live preview:**
  - Sliders (HTMX, debounced about 400 ms) re-render the preview as a PNG of page 1, plus a page selector for multi-page samples, using **pypdfium2** (Apache/BSD), which stays fast on the old laptop.
  - **Overlaid:** the letterhead plus the dummy data. **Guide lines** show the margin box and the reserved signature area.
- **Dummy data (synthetic, built into the app):**
  - a short single-page report
  - a **3-page report** (tests page breaks, header repeat, "continued" label, pending line, signature only on the last page)
  - long patient and doctor names, Unicode (Hindi/regional names)
  - a bill with 25 lines (tests page break and totals placement)
- **Print calibration page:**
  - Prints the dummy report **without** the letterhead but with thin guide boxes and corner marks, on plain paper.
  - Hold it against a letterhead sheet (against light) or print directly on one sheet of letterhead paper to check alignment.
  - Fine-tune with the sliders, then **Publish**.
- **Printer offset correction:** optional X/Y nudge (±10 mm) per branch, because some printers shift the page. Stored per branch, not in the letterhead.
- **Print guidance shown on screen:** "Print the PDF at **Actual size / 100%**, not *Fit to page*; printer margins: none." Scaling is the main cause of misalignment.
- **Draft vs published:** changes go live only on **Publish**. Each publish creates a new `letterhead_layout` version. Old reports keep the layout they were released with, so reprints of a released report still match.
- **Defaults** if no letterhead is uploaded: Labra prints its own simple header from `branch` details (name, address, NABL no, GSTIN), so it works on day 1.

**Table `letterhead_layout`:**
| Column | Meaning |
|---|---|
| branch_id, doc_kind (`report_a4` / `bill_a4`) | which layout |
| version, status (`draft` / `published`), published_by, published_at | versioning |
| original_file_id, letterhead_file_id (optimised), file_type (`svg` / `pdf` / `raster`), raster_dpi, original_bytes, optimised_bytes, converted_from (`none` / `pdf` / `raster_traced`), apply_on (`all` / `first`) | letterhead file, optimisation result and pages |
| margin_top_mm, margin_bottom_mm, margin_left_mm, margin_right_mm, signature_area_mm | layout box |
| font_size_pt, print_offset_x_mm, print_offset_y_mm | fine tuning |
| default_print_mode (`print_no_lh` / `plain_with_lh`) | branch default |

**Tests:**
- **Content box:** golden-file tests render each dummy dataset at fixed margins and check that every text box lies inside the content box. pdfplumber reads the text coordinates (MIT, test-only dependency).
- **Two outputs:** the digital and print PDFs have the **same text coordinates**; only the letterhead layer differs.
- **3-page sample:** the signature appears only on the last page.
- **Versioning:** publishing a new layout doesn't change an existing released report's stored PDF.
- **File size:**
  - A 2 MB JPG letterhead upload produces a ≤ 300 KB 1-page report.
  - A 3-page report contains exactly **one** letterhead image object, checked by counting image XObjects with pypdf.
  - A WebP upload is converted, never embedded as decoded raw data.
- **SVG safety:** an SVG containing `<script>` or an external `href` is rejected or stripped, and rendering makes no network request.
- **SVG suggestion:** a synthetic vector PDF converts to SVG with the same text positions (pdfplumber); a flat two-colour PNG gets the suggestion, a synthetic photo-like gradient doesn't; choosing "Keep current" leaves the layout unchanged.

**Other print formats:**
- **Sample label (50×25 mm):** barcode with sample_no, patient name, age/sex, container colour/code, collection time, test short names.
- **Worklist (A4, per department):** sample no, patient, tests, priority, due time.
- **Pending / turnaround list:** overdue tests are highlighted.
- **Day-close sheet:** expected vs counted per payment mode, variance, signatures.

## 8. Bill formats
Both A4/A5 and 80 mm thermal versions come from the same template data. When a visit mixes exempt and taxable items, **two documents** are generated automatically.

**Bill of supply (exempt diagnostic services):**
```
<Logo> <LEGAL NAME> · Branch 2, <address> · GSTIN 29XXXXX1Z5
                        BILL OF SUPPLY
Bill No: B2/2627/00123             Date: 05-Oct-2026 10:42
Patient: <Name> · 34/F · P-000456     Ref: Dr <name>   Visit: B2-V-..
Place of supply: Karnataka (29)       Counter: <user>
 #  Description               SAC     Rate     Disc    Amount
 1  CBC                       999316  350.00    35.00   315.00
 2  HbA1c                     999316  450.00    45.00   405.00
 3  Home collection           999316  100.00     0.00   100.00
                                        Total              820.00
                                        Round off            0.00
                                        Net payable        820.00
Amount in words: Rupees Eight Hundred Twenty only
Paid: UPI ₹500 (UTR 4271…) · Balance due: ₹320        [UPI QR for due]
Discount: camp 10% approved by <manager>
Healthcare services exempt from GST (configurable note text)
Sample IDs: B2-2026-000123, -000124          Authorised signatory
```
**Required fields (CGST Rule 49 for a bill of supply; checked by a template test) [M07.1]:**
| Rule 49 item | On Labra's bill |
|---|---|
| (a) Supplier name, address, GSTIN | Branch block (GSTIN printed only if the lab is registered) |
| (b) Serial number **≤ 16 characters**, unique per financial year, one or more series, only letters, digits, `-` and `/` | `B2/2627/00123`; the settings form refuses a format that can exceed 16 characters (offline series too) |
| (c) Date of issue | Bill date |
| (d) Recipient name/address/GSTIN if registered | Patient name; GSTIN and address for B2B / corporate bills |
| (e) HSN / SAC code | SAC per line (from `gst_category`) |
| (f) Description | Test / package name |
| (g) Value after discount | Rate, discount, amount per line |
| (h) Signature or digital signature | "Authorised signatory" on paper; not needed on an electronic bill issued under the IT Act (Rule 49 proviso) |

**Also on the bill, though not legally required:**
- patient no
- visit no
- sample IDs
- payment mode and reference
- balance due + UPI QR for the due amount
- discount reason / approver
- amount in words

A tax invoice adds the Rule 46 fields (place of supply, taxable value, rate, tax amounts). A CA must still confirm the wording (§13).

**Tax invoice (taxable items, for example wellness packages):** the same layout, titled "TAX INVOICE". It adds a taxable-value column and CGST/SGST (or IGST) rate and amount per line, the recipient GSTIN for B2B, and a tax total. The SAC and rate come from `gst_category`.

**Payment receipt / advance receipt:** receipt no, date, payer, amount, mode, reference, against which bill (or "advance").

**Refund / credit note:** a credit note number against the original tax invoice; a refund voucher for a bill of supply.

**Currency display (settings, owner request 2026-10-05):**
All money on bills, receipts, reports for the owner and screens goes through one `format_money()` helper (Babel), driven by these settings (instance-wide, overridable per branch):
| Setting | Default | Options / example |
|---|---|---|
| `currency.code` | `INR` | any ISO 4217 code (`INR`, `NPR`, `LKR`, `USD`, ...) |
| `currency.symbol` | `₹` | `₹`, `Rs.`, `INR`, `Rs`, custom text, or empty |
| `currency.symbol_position` | before | before (`₹820.00`) / after (`820.00 ₹`) / with space (`Rs. 820.00`) |
| `currency.grouping` | Indian | Indian `1,23,456.00` / international `123,456.00` |
| `currency.decimals` | 2 | 0 or 2 (with 0, amounts still store paise; only the display rounds) |
| `currency.show_in_columns` | header only | symbol in column headers only (`Amount (₹)`, cleaner tables) / on every amount |
| `currency.words` | Rupees / Paise | major/minor unit names for "Amount in words" (`Rupees … and Fifty Paise only`); Indian words (lakh, crore) or international (million) |
| `currency.round_off_to` | 1.00 | 1.00 / 0.50 / 0.10 / none |

Rules:
- **PDF font check:** the bill and report fonts must contain `₹` (U+20B9). Labra ships Noto Sans (covers `₹` and Indian scripts) and the template preview shows a warning if the chosen font is missing the symbol, since a missing glyph prints as an empty box. `Rs.` is the fallback if the warning is ignored.
- Stored amounts never change with these settings; a changed setting only changes how new and reprinted documents *look*. A released bill's stored PDF stays as issued.
- The UPI QR always uses INR amounts regardless of display settings (UPI is INR-only).
- The letterhead calibration dummy bill uses the current currency settings, so a long symbol like `INR` is checked for column overflow.
- **Tests:** `format_money()` table tests for each option (Indian grouping `1,23,45,678.50`, symbol positions, 0 decimals); amount-in-words for 0, 0.50, 99,999.99, 1,00,00,000; a bill rendered with `₹` contains the glyph in the embedded font (pdfplumber text extraction returns `₹`); this PDF test belongs to M17, where bills first become PDFs, since the front desk prints bills from HTML.

**Numbering:** gapless per series, branch and Indian financial year (April reset). Offline devices use their own series (§9). The legal wording, SAC defaults and exemption note are **configurable and must be checked by a CA**; Labra ships editable defaults, not legal advice.

## 9. Offline operation
**Layer 1: keep the internet up (cheapest, do first)**
- **Main lab:** dual internet (broadband + 4G failover router).
- **Branches:** a 4G failover router or hotspot (about ₹300–500/month).

**Layer 2: the main lab never depends on the internet**
- The mini PC serves main-lab PCs over the **LAN**. When the internet drops, the main lab keeps working fully; only branch access, email and offsite backup pause and catch up later.
- Requirements: UPS on the mini PC, router and switch; a local DNS name (`labra.lan`) and a local certificate.

**Layer 3: branch "offline counter" (0.4), for when a branch can't reach the server**
- **What works offline:**
  - search recent or cached patients and register new ones
  - create a visit, pick tests/packages
  - bill (prices from the cached price list) and take cash/UPI payments
  - print the receipt and sample labels
- **What needs the connection:** results, reports, refunds, discounts above the offline limit, and day close.
- **How it works:**
  - The branch PC is registered as a `device`. The app installs as a PWA with a service worker that caches the counter pages.
  - Cached data in IndexedDB: the catalog, the active price list and recent patients (last 90 days, configurable; encrypted at rest with a key derived from the user's login).
  - **Numbers handed out in advance:** while online, the device receives `number_block`s for samples, visits, receipts and bills in its **own offline series** (for example `B2D1BS/2627/0045`, still ≤ 16 characters). GST allows multiple series, so numbering stays gapless and unique without the server.
  - Offline records get app-generated UUIDs and a `client_ref`. On reconnect they're uploaded as `sync_batch`es. The server **replays them through the same `service.py` rules**; duplicates are ignored by `client_ref`.
- **Conflicts:**
  - Branches only *create* records offline, never edit, so conflicts are limited to duplicate patients. These go to a **merge queue** for a front-desk review; nothing merges automatically.
  - Price changes made while a device was offline: the bill keeps the price it was issued at, and the price-list version is recorded on the bill line.
- **Limits:**
  - The UI shows an "OFFLINE: n records waiting to sync" banner.
  - Offline discount cap: a setting, default 0% above the role limit.
  - The maximum offline period is a setting (default 72 h). After it, the device stops issuing bills until it syncs.
- **Cloud-hosted variant:** the same offline counter works for branches, but the main lab needs internet (or it should use the mini PC setup).

**Layer 4: backups and recovery**
- `pg_dump` + `/data/files` → restic (encrypted) → **Google Drive via rclone** every 15 min in lab hours + nightly (§17.3), plus a USB copy. Full details and retention are in §1a. B2/S3 is an alternative destination.
- A monthly automated restore test into a scratch container.
- A local copy on a second disk / USB drive for fast recovery if the internet is down.

## 10. Customisation model
| Layer | What admins change | v1 surface |
|---|---|---|
| Settings | report mode default, routing strategy, turnaround thresholds, discount limits per role, numbering formats, currency display (symbol, position, grouping, words; §8), feature toggles (sample tracking, two-level verification, offline counter), consent text | Settings screen with typed forms |
| Data | catalog, parameters, ranges, packages, price lists (versioned), external labs and rates, branches, users, roles | Admin screens + price CSV import with preview/diff |
| Templates | report, bills, receipt, label, letterhead, manifest | v1: files overridable in `/data/templates`, published as a `template` row; later: in-portal editor with preview |
| Custom fields | extra fields on patient/visit/bill | later: `field_definition` UI (JSONB `extra` already exists) |
| Plugins | Python entry points: `labra.routing_strategies`, `labra.result_importers`, `labra.report_renderers`, `labra.accounting_exporters`, `labra.notifiers` | documented API, examples in repo |

## 11. Medical standards
| Standard | Use | When |
|---|---|---|
| HL7 FHIR R4 (India NRCeS profiles) | Data model follows FHIR's structure (Patient, ServiceRequest, Specimen, Observation, DiagnosticReport, Organization); report export as a FHIR Bundle | Structure in v1, export later |
| LOINC | optional code on test/parameter, imported from CSV | field in v1 |
| UCUM | units on parameters/ranges | v1 |
| SNOMED CT (free in India via NRCeS) | specimen types, interpretations | later |
| ICD-10 | optional provisional diagnosis on visit | field in v1 |
| HL7 v2 / ASTM (CLSI LIS01/02) | analyzer bridge | 2.x |
| ABDM (ABHA, HFR, HIP, consent) | optional ABHA on patient; report push as HIP after the certification process | 2.x |
| ISO 15189:2022 / NABL 112 | audit, signatory release, referral disclosure, amended reports, later internal quality control | v1 |
| DPDP Act 2023 | consent, minimum data sent to external labs, retention/erasure workflow, breach log | consent in v1 |
| PC-PNDT | no fetal-sex data or output | v1 rule |

LOINC and SNOMED code files are licensed, so Labra ships **import tools, not the files**. This is recorded in `ATTRIBUTIONS.md`.

## 12. AI (later, advisory only)
- **Ideas:** extracting values from external result PDFs (pre-fills entry; a person confirms), drafting interpretation text, catching likely duplicate patients, turnaround and margin analytics.
- **Regulatory line:** must never auto-release, auto-diagnose or skip a human step. Results interpretation can make software a CDSCO medical device; ICMR's 2023 guidelines also apply.
- **Patient data:** only through a `labra.ai_providers` plugin with a per-lab on/off switch. Patient data goes to a cloud LLM only with explicit consent and a data-processing agreement; otherwise use a local model where the hardware allows.

## 13. Repo bootstrap and docs (from the 2026-08-18 plan, still valid)
- **Community and repo files:** README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY (no real patient data, ever), SUPPORT, issue/PR templates, CI, Dependabot/Renovate, CHANGELOG (Keep a Changelog, 0.x), ATTRIBUTIONS.
- **Decision records:** ADR-0001 (record decisions), ADR-0002 (licence: stay MIT; borrow ideas only from AGPL/GPL projects), ADR-0003 (build fresh on FastAPI + Postgres), ADR-0004 (mini PC hosting + offline layers), ADR-0005 (medical standards), ADR-0006 (customisation model).
- **Docs:** `docs/research/` (open-source survey, regulations survey from the zip, with a quarterly "still maintained?" re-check) and `docs/compliance/COMPLIANCE_CHECKLIST.md`, including the CA review items: GST on lab-to-lab B2B tests, bill wording, e-invoicing applicability.
- **Domain study:** the trial installs of OpenELIS/Bahmni/Frappe become optional, to borrow workflows and screens only.
- **One local gate script** (`scripts/ci_local.sh`-style): lint, types, tests, audit.

## 13a. User manual (kept in step with the UI)
**Audience:** lab staff and owners, not developers. Plain language, one task per page, a screenshot for every screen.

**Structure** (`docs/manual/`, built with Zensical from `mkdocs.yml` (§19.3), also exported as one PDF via WeasyPrint for printing at the counter):
1. **Features overview:** one page listing every feature, numbered by area, each linking to its page.
2. **Getting started:** logging in, roles, changing your password, the screen layout, keyboard shortcuts.
3. **Front desk:** new visit, find a patient, patient history, bills and receipts, dues and payments, labels, home visits.
4. **Lab:** worklist, entering results, calculated values, critical values, outsourcing (send, receive, timeline), lab status board.
5. **Reports:** releasing, selected tests, A4/A5, with/without reference column, print vs digital PDF, delivery, amended reports.
6. **Owner:** daily collection, dues, statements, outsourcing margin.
7. **Admin:** branches, users and permissions, catalog, methods, prices, external labs, letterhead and margins, currency, settings, backups and restore.
8. **Troubleshooting & FAQ;** **What's new** (per release, generated from the changelog's operator-facing lines).

Each page uses one template: *What it's for* → *Where to find it* (`Menu ▸ path`, shortcut) → *Steps* → *Screenshot* → *Good to know* → *Related pages*.

**Keeping it current (enforced, not optional):**
- **Screen registry:** every UI route declares `manual_page="frontdesk/new-visit"` in its route metadata. A CI test fails if a page route has no manual page or points to a missing file.
- **Automatic screenshots:** `scripts/gen_manual_screenshots.py` runs Playwright against the synthetic seed data at a fixed screen size and saves one PNG per registered screen (and named states such as "dialog open"). They're regenerated whenever the UI changes, so screenshots never go stale; synthetic data only, never real patients.
- **Staleness gate (CI + pre-commit):** if a change touches `templates/` or a route, then the matching manual page **or** its regenerated screenshot must change in the same PR, unless the PR carries a `manual: no change` line with a reason. Screenshot drift is detected by perceptual diff, so tiny anti-aliasing changes don't fail it.
- **Feature IDs:** each manual page's front matter lists the tracker IDs it documents (`features: [M07, M23]`); the features overview page is generated from those, and `check_tracker.py` flags a `done` feature with no manual page.
- **In-app help:** every screen has a `?` button opening its manual page (served locally, so it works offline).
- **Release checklist** (§14a M) includes "manual updated, What's new written, PDF rebuilt".
- The manual is versioned with the app; the System page links to the manual for the installed version.

## 14. Verification
- **Every change ships a test.** CI runs ruff, pyright, pytest (with testcontainers Postgres), pip-audit/osv-scanner and gitleaks, and builds the Docker image.
- **Money:** hypothesis property tests check that bill lines sum to the bill total, the GST split equals the line tax, round-off is within ±0.50, and an exempt + taxable visit produces exactly 2 documents.
- **Compliance rules:** tests prove UPDATE/DELETE on `audit_log` fails, a released report can't be edited (only amended), and a non-signatory can't release a report.
- **Offline:** a Playwright test cuts the network, registers and bills 3 patients, prints labels, restores the network, then checks that the sync is applied once, numbers are unique, and a duplicate patient lands in the merge queue.
- **End to end on synthetic seed data:** register → bill → collect → route (1 in-house, 1 external) → result + external PDF → verify → release combined and separate reports → day close. Compare the PDFs against snapshot files.
- **Ops:** the backup → restore drill passes; the mini PC keeps serving the LAN with the WAN unplugged.
- **Pilot (0.5):** one week of parallel running at the owner's labs before switching over.

## 14a. Enterprise-grade checklist (owner request 2026-10-05)
"Enterprise grade" here means: a lab can trust it with patient data and money every day, recover from any single failure, pass a NABL/DPDP audit, and upgrade without fear. It's sized for a small lab on an old laptop, not big-company infrastructure.

Committed to the repo as `docs/ENTERPRISE_CHECKLIST.md`. Each item has a **gate**:
- **P** = must pass before the pilot (minimal version)
- **1** = before calling it 1.0 / offering to other labs
- **L** = later

CI enforces the items marked *(CI)*. The release checklist (section M) links back here.

### A. Security
- [ ] **P** `EC-A01` Passwords hashed with argon2 (argon2-cffi, §19.3); minimum length 10, checked against a common-password list; no forced periodic resets (NIST 800-63B)
- [ ] **P** `EC-A02` Login lockout / rate limit after 5 failed tries per user + IP; audit every login, logout and failure
- [ ] **P** `EC-A03` Session cookies `HttpOnly`, `Secure`, `SameSite=Lax`; idle timeout (default 30 min, setting) and absolute timeout (12 h); "log out all sessions" for admins
- [ ] **P** `EC-A04` CSRF tokens on every form and HTMX POST
- [ ] **P** `EC-A05` Role check on **every** route by default (deny unless allowed) + branch scoping in the service layer; tests prove a front-desk user of branch B2 can't open branch B3's patient *(CI)*
- [ ] **P** `EC-A06` Security headers via Caddy: CSP (no inline scripts except nonce, no `unsafe-eval`: so Alpine's **CSP build** and htmx with `allowEval` off, §19.3), HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`
- [ ] **P** `EC-A07` Upload safety: type sniffed (not trusted from the filename), size cap, SVG sanitised, PDFs never executed, files served with `Content-Disposition` and a safe content type
- [ ] **P** `EC-A08` Jinja autoescape on; report/bill templates rendered in the **sandboxed** Jinja environment
- [ ] **P** `EC-A09` All SQL through SQLAlchemy parameters; no string-built SQL *(CI: ruff `S608`)*
- [ ] **P** `EC-A10` Secrets only from env / `.env` (mode 600) / Docker secrets; never in the database, logs, CLI args or Git *(CI: gitleaks)*
- [ ] **P** `EC-A11` Remote access only through Cloudflare Tunnel + Cloudflare Access (email OTP); no open router ports; Postgres not exposed outside Docker
- [ ] **P** `EC-A12` Disk encryption (LUKS) on the laptop, so a stolen laptop doesn't leak patient data; unlock key recorded with the restic password
- [ ] **1** `EC-A13` 2FA (TOTP) required for admin and signatory roles
- [ ] **1** `EC-A14` OWASP ASVS level 1 self-assessment written up; `SECURITY.md` with a reporting contact and response times
- [ ] **1** `EC-A15` Independent review or pentest (even a volunteer one) before offering to other labs
- [ ] **L** `EC-A16` SSO (OIDC) for multi-lab installs

### B. Data integrity and money
- [ ] **P** `EC-B01` Money as `Decimal`, one calculation module; hypothesis property tests *(CI)*
- [ ] **P** `EC-B02` Gapless, unique document numbers under concurrency (row lock on `number_series`); test with 20 parallel bills *(CI)*
- [ ] **P** `EC-B03` Optimistic locking (`row_version`) on edits; a stale edit shows "changed by X, reload"
- [ ] **P** `EC-B04` Database constraints, not just app checks: foreign keys, `CHECK` (amount ≥ 0, paid ≤ net), unique keys, `NOT NULL`
- [ ] **P** `EC-B05` Released reports and issued bills are immutable; corrections only as amendment / credit note / cancellation with reason *(CI test)*
- [ ] **P** `EC-B06` Append-only audit log with a hash chain; a nightly job verifies the chain and alerts on a break
- [ ] **P** `EC-B07` Idempotent form submits (a double click doesn't create 2 bills: `client_ref` unique)
- [ ] **1** `EC-B08` Daily reconciliation report: payments vs bills vs day close; mismatches flagged

### C. Privacy and compliance (India)
- [ ] **P** `EC-C01` Consent recorded before testing and before referral-lab sharing; consent text versioned
- [ ] **P** `EC-C02` Data sent to external labs is the minimum needed (no phone/address unless the lab requires it, setting per lab)
- [ ] **P** `EC-C03` No patient data in logs, error messages, URLs or analytics *(CI: log-scrubbing test)*
- [ ] **P** `EC-C04` PC-PNDT: no fetal-sex fields or output anywhere
- [ ] **P** `EC-C05` Retention: reports and audit kept ≥ 2 years (NABL); nothing hard-deleted
- [ ] **1** `EC-C06` DPDP: privacy notice, patient data-access export, correction workflow, erasure request handling (anonymise beyond the retention period), breach register and 72-hour notification runbook
- [ ] **1** `EC-C07` Data-processing agreement template for external labs and any cloud provider; list of sub-processors (Google Drive, Cloudflare, WhatsApp provider)
- [ ] **1** `EC-C08` `docs/compliance/COMPLIANCE_CHECKLIST.md` reviewed by a CA (GST) and a lawyer (DPDP, IT Act signatures)
- [ ] **L** `EC-C09` NABL audit pack export (audit trail, signatory list, critical-value log, QC records)

### D. Reliability, backup and disaster recovery
- [ ] **P** `EC-D01` Backups every 15 min in lab hours + nightly (configurable 15m–24h, §17.3) to Google Drive (encrypted) + USB; healthcheck alert on a missed run
- [ ] **P** `EC-D02` **Monthly restore drill**, automated, result logged; a failed drill alerts the owner
- [ ] **P** `EC-D03` Written targets: **RPO ≤ 15 min** (data loss at worst, §17.3), **RTO ≤ 2 h** (time back in business on a spare laptop); restore runbook tested once before the pilot
- [ ] **P** `EC-D04` Containers `restart: unless-stopped`; app health endpoint (`/healthz` checks the database); Docker health checks
- [ ] **P** `EC-D05` Postgres: `fsync` on, checksums on, disk-space alert at 80%
- [ ] **P** `EC-D06` UPS for laptop power path, router and switch; laptop auto-starts after power returns
- [ ] **P** `EC-D07` Main lab works with the WAN unplugged (LAN-only test before the pilot)
- [ ] **1** `EC-D08` Point-in-time recovery (WAL archiving with pgBackRest or WAL-G) if the owner wants RPO in minutes
- [ ] **L** `EC-D09` Warm standby (second laptop/mini PC with streaming replication)

### E. Observability and support
- [ ] **P** `EC-E01` Structured JSON logs (structlog) with a request ID; IDs only, never names/phones; log rotation
- [ ] **P** `EC-E02` Uptime monitor (Uptime Kuma or Healthchecks.io) for the web app, backup job and Tunnel; alerts to the owner by email/Telegram
- [ ] **P** `EC-E03` Friendly error page with an error reference number, matching a log entry, so staff can report it
- [ ] **P** `EC-E04` `Admin ▸ System` page: version, last backup, disk space, database size, pending migrations, certificate expiry
- [ ] **1** `EC-E05` Error tracking (GlitchTip, self-hosted, PII scrubbing on)
- [ ] **1** `EC-E06` Support bundle: one button exports logs (scrubbed) + versions + settings (no patient data) for troubleshooting

### F. Performance and capacity
- [ ] **P** `EC-F01` Budgets on the 4 GB laptop: page load < 1 s on LAN, search < 300 ms, report PDF < 3 s, memory < 2 GB with 3 users
- [ ] **P** `EC-F02` Indexes for every list/search screen (patient phone/name trigram, visit date, order status); `EXPLAIN` checked in a test for the 5 main queries
- [ ] **P** `EC-F03` Pagination everywhere; no unbounded lists
- [ ] **1** `EC-F04` Load test (Locust) with 10 concurrent users and 5 years of synthetic data (about 160k visits)

### G. Upgrades, migrations, versioning
- [ ] **P** `EC-G01` SemVer 0.x, `CHANGELOG.md` with dated entries; version shown in the footer and System page
- [ ] **P** `EC-G02` Alembic migrations: forward-only in production, each tested on a copy of the previous release's schema *(CI: upgrade from last tag)*
- [ ] **P** `EC-G03` Upgrade script: takes a backup → pulls the pinned image → runs migrations → health check → **automatic rollback** to the previous image + restore if the health check fails
- [ ] **P** `EC-G04` Docker images pinned by version (no `latest`)
- [ ] **1** `EC-G05` Documented upgrade path across 2+ versions; deprecation policy (§18.3): a removed setting, screen or export column keeps working for at least one minor release, shows a notice on `Admin ▸ System` naming the release it goes away in, and is listed under "Deprecated" in the changelog
- [ ] **1** `EC-G06` Zero-touch security updates for the OS (unattended-upgrades) with reboot window outside lab hours

### H. Code quality and testing
- [ ] **P** `EC-H01` Every change ships a test; coverage report in CI (target ≥ 80% on `service.py` modules) *(CI)*
- [ ] **P** `EC-H02` ruff (lint + format), pyright strict on `service` and `billing`, pytest against real Postgres (testcontainers) *(CI)*
- [ ] **P** `EC-H03` One Playwright end-to-end test of the full day; PDF snapshot tests for report and bill *(CI)*
- [ ] **P** `EC-H04` Single local gate script = same as CI (`scripts/ci_local.sh`)
- [ ] **P** `EC-H05` Branch protection on `main`: CI must pass, PR required
- [ ] **1** `EC-H06` Mutation testing on the money module (mutmut), occasional
- [ ] **1** `EC-H07` Accessibility checks (axe via Playwright) on the main screens *(CI)*

### I. Supply chain
- [ ] **P** `EC-I01` `uv.lock` committed; lock drift fails CI *(CI)*
- [ ] **P** `EC-I02` pip-audit + osv-scanner + gitleaks in CI; Dependabot/Renovate weekly *(CI)*
- [ ] **P** `EC-I03` Licence check: allowlist MIT, BSD-2/3, 0BSD, Apache-2.0, PSF, ISC, MIT-CMU (Pillow), PostgreSQL; MPL-2.0 test-only (hypothesis); **LGPL-3.0 only for psycopg**, imported unmodified (ADR-0002 note); GPL tools (poppler) only as separate commands *(CI: pip-licenses allowlist)*
- [ ] **1** `EC-I04` SBOM (CycloneDX) attached to every release; images built in GitHub Actions and signed (cosign); provenance attestation
- [ ] **1** `EC-I05` Container image vulnerability scan with osv-scanner (or grype), pinned by SHA *(CI)*. Not Trivy: its Actions and v0.69.4 binary were compromised in March 2026 (§19.2)
- [ ] **P** `EC-I06` Every GitHub Action pinned to a full commit SHA, every image to a digest, every vendored asset to a recorded SHA-256; Renovate updates the pins *(CI: check refuses a tag-only `uses:`)*
- [ ] **P** `EC-I07` Every dependency (Python, image, vendored asset, CLI tool) has a row in `docs/DEPENDENCIES.md`; the register is reviewed each quarter and before each release *(CI: `audit_deps.py --check`)*

### J. Usability and accessibility
- [ ] **P** `EC-J01` Keyboard-first front desk (barcode scanner + Enter flows, shortcuts for new patient / bill / print)
- [ ] **P** `EC-J02` Works in Chrome/Edge on a 1366×768 screen (common on branch PCs)
- [ ] **P** `EC-J03` Clear empty, loading and error states (Basecoat components); confirmation for cancel/refund/release
- [ ] **1** `EC-J04` WCAG 2.2 AA on main screens (contrast, focus, labels)
- [ ] **1** `EC-J05` UI translations (Babel) with at least one regional language

### K. Configuration and customisation safety
- [ ] **P** `EC-K01` Settings typed and validated (Pydantic); invalid values refused with a message
- [ ] **P** `EC-K02` Settings changes, price changes and template publishes are audited and versioned (who, when, before/after)
- [ ] **P** `EC-K03` Draft → preview → publish for templates and letterheads; old documents keep their version
- [ ] **1** `EC-K04` Settings export/import (JSON) for moving to a new server or copying a branch setup
- [ ] **1** `EC-K05` Plugin API documented and versioned; a broken plugin is disabled with a warning, not a crash

### L. Documentation and training
- [ ] **P** `EC-L01` Install guide for the old laptop (OS → Docker → Labra → backup setup), tested by someone other than the author
- [ ] **P** `EC-L02` User manual (§13a) covering every minimal-version screen, screenshots generated from synthetic data; screen-registry and staleness gates green *(CI)*
- [ ] **P** `EC-L03` Runbooks: restore from backup, laptop dead, internet down at a branch, forgotten admin password, certificate/Tunnel renewal, disk full
- [ ] **1** `EC-L04` Docs site (Zensical, §19.3), architecture + ADRs, API reference, contributor guide
- [ ] **1** `EC-L05` Training checklist for new staff; one-page quick-reference cards per role

### M. Release checklist (every release)
- [ ] CI green; changelog dated; version bumped
- [ ] User manual updated, screenshots regenerated, What's new written, manual PDF rebuilt
- [ ] Migration upgrade test from the previous tag passed
- [ ] Backup → upgrade → rollback rehearsed on a test laptop
- [ ] Security scan results reviewed (no unaddressed high/critical)
- [ ] Release notes say what operators must do (if anything)
- [ ] Tagged; images pinned; SBOM attached (from gate 1)

### Open-source project health (gate 1)
- [ ] `EC-O01` README with screenshots and a 10-minute demo (Docker + synthetic seed data)
- [ ] `EC-O02` CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT, issue/PR templates, GOVERNANCE (who decides)
- [ ] `EC-O03` ATTRIBUTIONS (Basecoat, vtracer, WeasyPrint, pyHanko, ...) and licence headers
- [ ] `EC-O04` Public roadmap (GitHub Projects) and a "good first issue" label
- [ ] `EC-O05` Bus factor (§18.3): repo moved to a GitHub organization (owner's go-ahead first), `MAINTAINERS.md`, `docs/dev/releasing.md` complete enough that someone else can cut a release
- [ ] `EC-O06` GitHub private vulnerability reporting on; OpenSSF Scorecard action in CI (owner's go-ahead for the GitHub setting)
- [ ] `EC-O07` Issue forms (YAML) with version, install type and a required "contains no patient data" tick; GitHub Discussions for questions, issues for bugs only
- [ ] `EC-O08` Public demo on synthetic seed data, reset nightly, on its own small server (never the standby)


## 16. Implementation runs: initialize labra + minimal version (owner request 2026-10-06)
**Context:** the owner wants:
- the repo initialized at `~/labra`
- a dev setup with AGENTS.md, rules, agents, hooks and a gate script
- the **minimal version only**, with tracker IDs on every piece of work
- AGENTS.md saying which ID tags to use
- manual pages written **in the same PR as the code they document**

**Owner decisions (2026-10-06):**
- Docker Engine inside WSL, not Docker Desktop.
- **Six runs**, one per build slice. Each run is one `/implement` session, merged and verified before the next starts.

**Standing rules for every run:**
- Never name the reference commercial product or vendor.
- No lab or staff names.
- Synthetic data only.
- Secrets via env only.
- No AI `Co-Authored-By` trailer.
- **Push and GitHub settings** (branch protection, EC-H05) need the owner's go-ahead each time.

### 16.0 Prerequisites (once, on this WSL machine)
1. **Docker:**
   - Install Docker Engine + the compose plugin from Docker's apt repo.
   - Add the user to the `docker` group.
   - Make sure `/etc/wsl.conf` has `[boot] systemd=true`.
   - Check that `docker run --rm hello-world` and `docker compose version` both work.
2. **uv:** already installed.
3. **Playwright browsers:** `uv run playwright install chromium --with-deps`, first needed by the screenshot generator (M25.2, gate P2 since §18.2).

### 16.1 Run shortlist (minimal version only; X/LT items are out of scope until the pilot)
| Run | Slice (§1a build order) | Tracker IDs | Main gate-P EC items | Manual / docs pages shipped in the same run |
|---|---|---|---|---|
| **1** | Repo, agent setup, docs site, foundation | W01, W02, W08, W08.1, W13, W14, W15, W16, W03, W04, W05 (seed framework + §1e cast), M02, M01, M01.1, M01.2, M15, **M25.1**, **M25.2** | A01–A05, A08–A10, B02, B04, B06, B07, D04, D05, E01, E03, G01, G02, G04, H01, H02, H04, I01–I03, K01, C03, C04 | `getting-started/login`, `getting-started/screen-layout`, `admin/branches`, `admin/users-and-roles`, `admin/settings`; dev docs `dev/setup.md`, `dev/workflow.md`; ADR-0001 to 0006; `docs/research/` |
| **2** | Catalog, prices, admin screens | M05, M05.1, M05.2, M06, M14, M24 (cross-checked against Appendix A; disputed ranges left unapproved for the pathologist) | B03, K02, F02 | `admin/catalog`, `admin/reference-ranges`, `admin/methods`, `admin/prices`, `admin/starter-catalog` |
| **3** | Front desk | M03, M04, M18, M07, M07.1, M23, M08 (M18.1 is gate P2 and waits) | B01, B04, B07, C01, F03, J01, J02; the bill and front-desk parts of B05 and J03, which close in Run 5 with released reports | `frontdesk/new-visit`, `frontdesk/find-patient`, `frontdesk/bills-and-receipts`, `frontdesk/dues-and-payments`, `frontdesk/labels`, `getting-started/keyboard-shortcuts`, `admin/currency` |
| **4** | Lab | M09, M10, M11, M11.1, M11.2, M11.3, M07.4, the outsourcing timeline of M21 (delivery tracking closes in Run 5), the `test.sent_out` and `test.performed` events of M26 | C02; the upload part of A07; the results part of F01 | `lab/worklist`, `lab/receiving-samples`, `lab/entering-results`, `lab/calculated-values`, `lab/critical-values`, `lab/outsourcing`, `admin/external-labs` |
| **5** | Reports + owner | M17, M17.1, M12, M12.1, M20, M20.1, M19, M13 | A06, K03, H03 (full-day Playwright + PDF snapshots) | `reports/releasing`, `reports/options`, `reports/print-vs-digital`, `reports/delivery`, `reports/amended`, `frontdesk/patient-history`, `owner/daily-collection`, `owner/dues-pending-outsourcing`, `admin/letterhead-and-margins` |
| **6** | Install, backups, pilot prep | M16, W06, W07, **M25.3**, then W09 (the pilot week itself, after the run) | A11, A12, D01–D03, D06, D07, E02, E04, F01 (laptop budgets), G03, H05, L01–L03 | `admin/backups-and-restore`, `troubleshooting/*`, runbooks (`docs/runbooks/`), `install/laptop.md`, manual PDF, "A day at the lab" (§1e) |

**New sub-items:** Run 1 splits M25 into M25.1, M25.2 and M25.3, following the §0 dotted-ID rule. Each is added to `docs/TRACKER.md` in the same commit:
- **M25.1:** manual site (Zensical), page template, `manual_page=` route registry gate, staleness gate.
- **M25.2:** Playwright screenshot generator.
- **M25.3:** in-app `?` help and the printable manual PDF.

**Rule:** an item counts as done only when its code, its tests and its manual page or update are merged together.

### 16.2 Run 1 steps
1. **Clone and seed docs** (`W01`, `W02`):
   - `git clone https://github.com/premdon009/labra.git ~/labra` (the directory is empty). Branch `chore/w01-scaffold`.
   - Unzip `~/labra-plan-and-research.zip` with Python `zipfile`: the surveys go to `docs/research/`.
   - This plan goes in as `docs/design/v1-plan.md`, with these changes:
     - §1c no-name paragraph kept as worded
   - §0 becomes the live `docs/TRACKER.md`; §14a becomes `docs/ENTERPRISE_CHECKLIST.md`.
   - Before the first commit, grep the research docs for the reference product name.
2. **Agent and dev setup** (`W01`), all written fresh:
   | File | Content |
   |---|---|
   | `AGENTS.md` | Canonical agent memory. Sections:<br>• what Labra is<br>• hard rules: synthetic data only, never name reference products, secrets via env, every change ships a test **and** its manual page, no AI trailer<br>• layout and commands<br>• **Tracker IDs and tags** (16.3)<br>• docs-in-parallel rule<br>• 0.x SemVer and dated CHANGELOG<br>• branching (trunk on `master`, short branches) |
   | `CLAUDE.md` | `@AGENTS.md` only |
   | `GEMINI.md` | symlink to `AGENTS.md` |
   | `.clinerules/` | one pointer file to `AGENTS.md` |
   | `.aiderignore`, `.cursorignore`, `.clineignore` | exclude `.env*`, `data/`, `backups/`, `*.dump` |
   | `.claude/settings.json` | Allow: `uv run pytest/ruff/pyright`, `docker compose ps/logs/up`, read-only git. Deny: reading `.env*` and `data/` |
   | `.claude/agents/Explore.md` | Haiku, read-only search |
   | `.claude/agents/Plan.md` | Plan agent |
   | `.claude/commands/implement.md` | `/implement <ID…>` workflow:<br>1. read the tracker rows<br>2. create branch `feat/<id>-<slug>`<br>3. set status `doing`<br>4. code + tests + manual page<br>5. run `scripts/ci_local.sh`<br>6. set status `done` with date and PR |
   | `.mcp.json` | serena (`--project-from-cwd`) |
   | `.github/workflows/ci.yml` | runs `scripts/ci_local.sh` |
   | issue / PR templates | PR template has `Items:` and `Manual:` lines |
3. **Python project** (`W01`):
   - Layout: `pyproject.toml` (single package `src/labra/`, Python 3.13+), `uv.lock`, ruff + pyright config.
   - Tests: pytest + testcontainers Postgres fixture.
   - Module layout per §3.
4. **Gates** (`W08`, `M25.1`):
   - **`scripts/ci_local.sh` stages, in order:**
     1. preflight: `uv lock --check`
     2. ruff check + format
     3. pyright
     4. pytest
     5. `check_tracker.py`
     6. `check_manual.py`
     7. strict docs build (`zensical build`, failing on warnings and broken links; §19.3)
     8. audit: pip-audit, osv-scanner, gitleaks, pip-licenses allowlist, `audit_deps.py --check` (register complete, actions SHA-pinned). A tool that can't run shows `WARN = unchecked`, never pass.
   - **`scripts/check_tracker.py`:** the §0 rules, plus a progress-line rewrite and a check that every commit subject on the branch carries an ID.
   - **`scripts/check_manual.py`:**
     - every page route declares `manual_page=` pointing to an existing file
     - template or route changes need a manual or screenshot change, or a `manual: no change` line with a reason
     - a `done` item needs a page with `features: [ID]`
   - **`.pre-commit-config.yaml`:**
     - ruff, ruff-format, gitleaks
     - check-tracker, check-manual
     - changelog-dated
     - commit-msg hooks: an ID required in the subject, Co-Authored-By trailer stripped
     - a **banned-terms** hook that reads its list from `~/.config/labra/banned-terms.txt`, outside the repo, so the product name is never committed; the hook skips with a warning when the file is absent
5. **Docs site** (`M25.1`): `mkdocs.yml` built by **Zensical** (§19.3), with:
   - `docs/manual/index.md`: features overview, generated from `features:` front matter
   - `docs/manual/_template.md`: §13a page template
   - `docs/dev/`, `docs/adr/`, `docs/runbooks/`
6. **Compose** (`W03`):
   - `web`, `postgres:18` (tuned per §1a), `caddy`; `cloudflared` behind a profile.
   - Images pinned by version **and digest** (W14).
   - `/healthz` checks the database.
   - `restart: unless-stopped`.
7. **Foundation** (`W04`, `M02`, `M15`, `M01`, `M01.1`, `M01.2`):
   - Core: pydantic-settings, SQLAlchemy session, Alembic baseline.
   - `setting`: typed, branch > instance precedence.
   - `number_series`: row lock, FY reset, 16-character format guard.
   - `stored_file`: SHA-256 content-addressed.
   - `audit_log`: UPDATE/DELETE blocked by trigger, hash chain, nightly verify command.
   - `branch`.
   - Auth: argon2 login, lockout, session cookies, CSRF, deny-by-default role check, `role_permission` seed, staff with `can_login=false`.
   - Basecoat base layout.
8. **Seed** (`W05`): Faker-based `labra seed` command with the §1e cast (synthetic). Later runs extend it.
9. **Screenshots** (`M25.2`): `scripts/gen_manual_screenshots.py` (Playwright, fixed viewport, seed data). Run 1 shoots the login and branch/user screens.
10. **Version and finish:**
    - `labra 0.1.0` with a dated CHANGELOG.
    - Tick the tracker rows.
    - One commit per item group (e.g. `chore(repo): W01 scaffold…`, `feat(auth): M01 M01.1 M01.2 login, roles, permissions`).
    - Merge to `master` locally. **Ask before pushing.**

### 16.3 AGENTS.md "Tracker IDs and tags" section (content to write)
| Where | Convention | Example |
|---|---|---|
| Prefixes | `W` work · `M` minimal · `X` next expansion · `LT` later · `R` rejected (never implement) · `EC-<A–O>NN` enterprise checklist · dotted `M25.1` sub-item | — |
| Branch | `<type>/<primary-id-lowercase>-<slug>` | `feat/m07-billing`, `chore/w08-ci-gate` |
| Commit subject | `<type>(<scope>): <ID>[ <ID>…] <summary>`; every commit carries at least one ID; repo tooling uses `W01` or `W08` | `feat(billing): M07 M07.1 part payment, Rule 49 fields` |
| PR | title as the commit; body `Items: M07, EC-B01` and `Manual: frontdesk/dues-and-payments` (or `manual: no change — <reason>`) | — |
| Manual page | front matter `features: [M07, M23]` | — |
| Tests | `@pytest.mark.item("M07")` on the tests that prove an item; `check_tracker.py` warns on a `done` item without one | — |
| ADR | front matter `items: [W02]` | — |
| Code | **no IDs in code comments** (they go stale); the test markers carry the traceability | — |
| Status | `todo → doing → done` (strike-through + date + PR), or `blocked` / `dropped` with a reason; updated in the same PR | — |
| New idea | next free number in its prefix, tracker row added in the same change; never renumber or reuse | — |
| Git tags | releases only: `v0.1.0`; the pilot tag is refused while any W, M or gate-P EC item is open | — |

### 16.4 Run 1 verification
- `scripts/ci_local.sh` is green on every stage, with any audit `WARN` reported as unchecked.
- `pre-commit run --all-files` is green.
- A commit without an ID is rejected.
- `docker compose up -d`, then `/healthz` returns 200. Log in as the seeded admin; a front-desk user of B2 is refused branch B3 data (EC-A05 test).
- Tests prove:
  - UPDATE/DELETE on `audit_log` fails
  - the hash-chain verify detects an edited row
  - 20 parallel number requests are gapless
- The strict Zensical build passes. Each Run 1 screen has a manual page with a generated screenshot. Removing a page makes `check_manual.py` fail.
- `docs/TRACKER.md`: the Run 1 rows are `done` with date and commit, and the progress line is updated by the script.

Runs 2–6 each get their own detailed steps when they start: one plan-mode pass per run, based on 16.1 and the row details in §1a/§1d/§7/§8.

## 17. Portability, integration, backup and export decisions (owner, 2026-10-08)
**Context:**
- **Maintenance:** Labra may have only one maintainer, so whatever doesn't have to be built here shouldn't be.
- **Hosting:** if the laptop fails, hosting must be able to move to a cheap cloud server quickly.
- **Integration:** ERPNext and Tally are not options for now. Labra should expose integration points so other open-source software can be attached later.

### 17.1 Principle: replaceable edges, stable core (new ADR-0007)
- **One app for the core flow:** visit → bill → sample → result → report stays a single application. Internal modules are not made separately swappable; that costs more to maintain than it saves.
- **Edges are replaceable,** each through one small interface:

| Edge | Built-in now | Replaceable later by | Interface |
|---|---|---|---|
| Accounting | daily export (M26) | ERPNext, Tally, any ledger | adapter reading the event outbox |
| Inventory | none | ERPNext stock, Dolibarr | `test.performed` events |
| Notifications | none | WhatsApp, SMS or email provider | `labra.notifiers` (§10) |
| Report signing | signature image | org certificate, DSC, eSign | `labra.report_signers` (§7.1) |
| File storage | local disk | S3-compatible (MinIO, B2, R2) | `FileStore` protocol |
| Backup target | Google Drive + USB | any rclone or restic backend | config only |
| Hosting | laptop | any VPS, amd64 or arm64 | Compose + env (W10, W11) |
| Data out | CSV + Parquet export | another lab system, FHIR (LT12) | M26 export |
| Analysers | none | HL7 / ASTM bridge (LT03) | `labra.result_importers` |

- **Build the integration point now, the adapter only when a real system needs it.**
- **Outsourced to an external app:** X05, X20, X21, X27, X28, LT09, LT10 and LT13 become "via an external app through M26" in `docs/TRACKER.md`. They're built inside Labra only if no external app fits; that decision gets its own ADR.

### 17.2 M26: integration point and exports
1. **`event_outbox` table:**
   - Columns: id, at, type, entity, entity_id, payload JSONB, schema_version.
   - Written **in the same transaction** as the business change.
   - Event types: `bill.issued`, `bill.cancelled`, `payment.received`, `report.released`, `test.performed`, `test.sent_out`.
   - Readers track their own cursor. Payloads carry IDs and amounts, never patient names or phones, unless an adapter's data-sharing agreement allows it (EC-C02).
2. **Daily accounting export** (`labra export accounting --date`):
   - Contents: sales per branch per payment mode, dues, discounts, cancellations, outsourcing cost.
   - Formats: CSV (opens in Excel, imports into ERPNext/Tally later) and JSON.
3. **Full data export** (`labra export all`): every table, with a generated `schema.md`. The lab is never locked in, not even to Labra.
4. **Formats:**
   - **CSV:** for people and other software.
   - **Parquet** (zstd): typed, columnar, typically 5–10x smaller than CSV, readable by DuckDB, pandas, Spark and Excel Power Query. Use it for analytics, archiving and migration.
   - **Written through DuckDB** (MIT), reading Postgres via a normal query; no `pyarrow` dependency.
   - **Closed months** are written once as `export/<table>/year=YYYY/month=MM/*.parquet` and never rewritten. They don't change, so restic deduplicates them perfectly. Only the current month is rewritten.
5. **Safety:** exports contain patient data. They're written only to the encrypted data volume, every export is audited, admin role only, and they're never served over the tunnel.

### 17.3 Backups: 15 minutes, and why backups stay `pg_dump` (not Parquet)
- **Interval:** `BACKUP_INTERVAL` takes `15m` / `30m` / `2h` / `4h` / `24h`. Default: **every 15 min during lab hours, plus nightly.** EC-D03's RPO becomes **≤ 15 min**.
- **Format:** `pg_dump` **plain format, uncompressed**. The custom (`-Fc`) format compresses internally and defeats restic's deduplication. restic does the compression (zstd, typically 5–10x on SQL text).
- **Why Parquet is not the backup:** Parquet is the **export** format only, for four reasons:
  - **Not faithful:** it loses constraints, triggers (the audit-log append-only trigger), sequences, the hash-chain guarantees, JSONB/NUMERIC exactness and roles. A restore would need custom code, which is a second thing that can break.
  - **Bigger with deduplication:** a Parquet file rewritten every 15 minutes changes almost every byte, so restic would upload it in full each time. A plain dump deduplicates down to the few MB that changed.
  - **Not smaller where it counts:** after restic's own compression, a plain dump costs about the same as Parquet, and only the changed part is added.
  - **Reports aren't touched by either:** the PDFs, which are most of the size, are already compressed.
- **Retention:**
  - every snapshot for 2 days
  - then hourly for 7 days
  - then daily for 30 days
  - then monthly for 24 months
- **Expected cost** (estimate, to be measured in Run 6):
  - about 2–5 MB added per 15-minute run
  - about 0.3–0.6 GB of extra storage at steady state
  - about 100–250 MB of upload a day
- **Parquet monthly archive:** `export all` runs monthly into the same restic repository (closed months only) as a second, format-independent copy that can be read without Labra or Postgres.
- **Sub-minute RPO later:** WAL-G or pgBackRest continuous archiving (EC-D08). It can move to gate P if the owner wants it.

### 17.4 W10: cloud standby
| Level | Cost/month | Back in business (RTO) | Use |
|---|---|---|---|
| Cold (runbook only) | ₹0 | 1–2 h | always documented; works on any provider |
| **Warm (default)** | ~₹350–1,200 | ~15 min | VPS restores the newest snapshot nightly (it doubles as the restore drill, EC-D02) and stays idle |
| Hot (EC-D09) | ₹1,200+ | minutes | later |

- **Provider order** (India region; check prices before buying):
  1. Vultr Mumbai/Delhi (2 GB, about $10)
  2. Lightsail Mumbai/Hyderabad (2 GB, about $12)
  3. DigitalOcean Bangalore (about $12)
  4. Hostinger India (4 GB promo; needs an upfront term)
- **Oracle Always Free:** a test target only. Free limits were halved in 2026, Arm capacity is scarce, and idle free instances are reclaimed. A warm standby is idle by design.
- **Failover (`scripts/failover.sh`):**
  1. Confirm the laptop is down or fenced.
  2. Restore the newest snapshot.
  3. Start the app.
  4. Start `cloudflared` with the same tunnel. Branch URLs don't change.
- **Hard rule: only one server accepts writes at a time.**
- **Failback (`scripts/failback.sh`):**
  1. Freeze the cloud server.
  2. Back it up.
  3. Restore onto the laptop.
  4. Verify the audit hash chain.
  5. Switch the tunnel back.
- **Main lab during failover:** it works over the internet, which is slower. The 4G fallback from §1a applies.

### 17.5 Run assignment (adds to §16.1)
| Item | Run |
|---|---|
| W11 multi-arch images | 1 (CI builds both) |
| `event_outbox` table + `FileStore` protocol | 1 (foundation) |
| M26 billing events | 3 |
| M26 report and test events | 4–5 |
| M26 accounting export, full export | 5 |
| M26.1 Parquet monthly archive, W10.1 warm standby | after the pilot (P2) |
| M16 15-min backups + retention, W10 standby + failover/failback drill | 6 |
| ADR-0007 | 1 |
| ADR-0008, platform ports (§17.6) | 1 |

**Verification additions:**
- Outbox events are written atomically: a rolled-back bill leaves no event.
- Exporting the same closed month twice gives byte-identical Parquet.
- The Parquet row counts equal the Postgres row counts.
- A restore drill from a 15-minute snapshot passes.
- A failover → failback rehearsal on the standby VPS leaves the hash chain intact and all numbering gapless.

### 17.6 Platform services behind ports (owner, 2026-10-09; new ADR-0008)
**Context:** auth, logging, metrics and the other platform services must not lock Labra to one product. A lab should be able to keep the built-in version or point Labra at an external service it already runs, by changing config only.

**The fixed core:** patients, visits, billing, samples, results, reports, the audit log, numbering, and **authorisation** (roles, `role_permission`, branch scoping). These don't move. Everything else is a platform service reached through a port.

| Service | Port | Built-in default | External option (open protocol) | Selected by |
|---|---|---|---|---|
| Identity (who the user is) | `IdentityProvider` | local username + argon2 password (TOTP later, EC-A13) | any OIDC provider: Keycloak, Authentik, Zitadel, Google Workspace (EC-A16) | `LABRA_AUTH_PROVIDER=local\|oidc` |
| Logs | stdout | JSON lines (structlog), rotated by Docker | any collector reading container stdout (Vector, Fluent Bit, Promtail); OTLP logs (X35) | `LABRA_LOG_FORMAT=json\|console` |
| Metrics | `GET /metrics` | Prometheus text format, internal network or bearer token only | Prometheus, VictoriaMetrics, Grafana Alloy, any OTel collector scraping; OTLP push (X35) | `LABRA_METRICS=prometheus\|off` |
| Traces | OpenTelemetry | off | any OTLP backend: Jaeger, Tempo, SigNoz (X35) | `LABRA_OTLP_ENDPOINT` |
| Errors | `ErrorReporter` | log entry + reference number on the error page (EC-E03) | GlitchTip or Sentry by DSN (EC-E05) | `LABRA_ERROR_DSN` |
| Health | `GET /healthz` (process up), `GET /readyz` (database, migrations, disk) | — | Uptime Kuma, Healthchecks.io, any HTTP monitor (EC-E02) | none |
| Job heartbeats | `Heartbeat` | log line | any ping URL, Healthchecks.io style | `LABRA_HEARTBEAT_URL_<JOB>` |
| Email | `Mailer` | console in dev, SMTP in production | any SMTP relay; provider APIs through `labra.notifiers` | `LABRA_SMTP_URL` |
| Files | `FileStore` | local disk | S3-compatible (§17.1) | `LABRA_FILESTORE=local\|s3` |
| Secrets | environment | env vars, plus `<NAME>_FILE` to read Docker secrets | Vault, SOPS or anything that writes files | none |

**Rules:**
1. **Open protocols, not vendor SDKs.** Adapters speak OIDC, OTLP, Prometheus, SMTP, S3, plain HTTP pings and the Sentry protocol, so any compliant service works without new code.
2. **Core imports ports only.** Domain code imports the protocols in `labra.core.ports`, never an adapter or a vendor library. An import-linter contract enforces this in `ci_local.sh`.
3. **Chosen at startup, fail fast.** The adapter is picked from settings when the app starts; an unknown name or a missing required setting stops startup with a clear message.
4. **Built-in adapters ship in `labra.adapters.<service>`;** third-party ones register through entry points `labra.<service>`, like the §10 plugins.
5. **Vendor libraries are optional extras** (`labra[otel]`, `labra[s3]`, `labra[sentry]`), never core dependencies, and each one gets a `docs/DEPENDENCIES.md` row.
6. **One contract test suite per port.** Every adapter passes it; domain tests use the in-memory fake.
7. **Nothing personal leaves through a port** (EC-C02): logs and error reports are scrubbed, and metric labels never carry patient, visit or user IDs (privacy and label cardinality).
8. **Changing identity provider doesn't move authorisation.** An OIDC login maps to an `app_user` by (issuer, subject); roles and branches are still assigned in Labra. Local login can be switched off per install, except one break-glass admin account.
9. **Build the port and the built-in adapter now; build an external adapter only when an install needs it** (§17.1).

**Run assignment:** ports, built-in adapters, `/metrics`, `/readyz` and the import contract in Run 1 (W15, W16); OIDC with EC-A16; GlitchTip/Sentry with EC-E05; S3 when a lab needs it; OTLP export as X35.

**Verification:** the import contract fails when a domain module imports an adapter; an unknown `LABRA_AUTH_PROVIDER` stops startup; `/metrics` refuses a request without the token from outside the internal network; a log and metrics scan of the seeded test run finds no patient names, phones or IDs.


## 18. Time estimate, pilot-first cut, and workflows borrowed from open-source projects (owner, 2026-10-08)
**Owner answers:**
- **Time:** full-time, about 40 h/week, including review and testing.
- **Scope:** the pilot-first cut (§18.2).

### 18.1 How long the minimal version takes
**Assumptions:**
- Claude Code writes most of the code and tests.
- The owner reviews each change, clicks through each screen on seed data, and makes the decisions. **Review is the slowest step, not writing the code.**
- A "day" below is one focused working day of the owner's.

| Run | Days (with the cut) | Where the time goes |
|---|---|---|
| 1 Repo, gates, foundation | 8–12 | gate scripts; auth (CSRF, lockout); audit trigger + hash chain; numbering under concurrency; Compose; multi-arch CI; release pipeline (W12); docs site; dependency register + SHA pinning (W13, W14, +1 day) |
| 2 Catalog and prices | 4–6 | a citation for every range; cross-checking against Appendix A |
| 3 Front desk | 6–9 | one-screen visit; money maths + property tests; Rule 49 bill PDF; labels |
| 4 Lab | 6–8 | HTMX result grid; flags and formulas; external PDF upload; outsourcing timeline |
| 5 Reports and owner | 7–10 | WeasyPrint layout + ISO 15189 checklist test; letterhead calibration; amendments; owner reports; exports |
| 6 Install and backups | 3–5 | restic + rclone timers; LUKS install on the laptop; runbooks; one failover rehearsal on a rented VPS |
| **Build total** | **34–50 days ≈ 7–10 weeks** | without the cut: 42–61 days ≈ 8–12 weeks |
| Pilot | 1 week parallel run + 1–2 weeks of fixes | |
| **Total to switch-over** | **≈ 9–13 weeks (2–3 months)** | |
| After-pilot P2 items | 8–11 days | built in the first release after the pilot |

**Calendar** (if Run 1 starts the week of 2026-10-12):
- Pilot starts between early and late December 2026.
- Switch-over between late December 2026 and mid-January 2027.

**Waits outside the build:** none of these are counted above. Start them early so they run in parallel.
- **Range approval:** the lab's pathologist approves the starter ranges. Release is blocked while a range is unapproved (§1d), so **this gates the pilot**. Send the list at the end of Run 2.
- **Hardware:** the SSD for the laptop and a UPS for the router.
- **Docker:** installed in WSL (§16.0).
- **Backup account:** a dedicated Google account. The restic password written down in two offline places.
- **Failover rehearsal:** one month of a small VPS, about ₹1,000.
- **Monitoring:** a Healthchecks.io account.

**What can push it out:**
- Run 5 report layout iterations against the real letterhead.
- Feedback from the first real days of the pilot.
- PDF render speed on the old laptop.

**Re-estimate after Run 1:** record actual days per run in `docs/TRACKER.md`. Run 1 is the calibration point.

### 18.2 Pilot-first cut
**Moved to gate `P2`** (§0): W10.1, M17.1, M18.1, M20.1, M22, M24.1, M25.2, M25.3, M26.1.

**What stays for the pilot:**
- The full pilot day: register, bill, sample, route, result, verify, report, delivery and owner reports.
- Keyboard shortcuts (M18).
- The starter catalog of the tests the lab already reports (M24).
- The event outbox and the daily accounting export (M26).
- 15-minute backups (M16).
- Cold standby with one failover rehearsal (W10).
- Manual pages with hand-taken screenshots of seed data (M25.1).

**Changes to the §16.1 run table:**
| Run | Change |
|---|---|
| 1 | Gains W12. M25.2 moves to P2, so Run 1 ships hand-taken screenshots. |
| 4 | M22 moves to P2. |
| 5 | M17.1, M20.1 and M26.1 move to P2. |
| 6 | W10.1 and M25.3 move to P2. W10 is the cold runbook plus one rehearsal. |

§1e Step 8 (the TV board) and the TV part of the Playwright test follow M22 into P2.

### 18.3 Workflows borrowed from popular open-source projects
**Already in the plan, no change needed:**
- trunk-based branches and conventional commits
- pre-commit
- Dependabot/Renovate
- ADRs
- Keep a Changelog
- SemVer 0.x
- upgrade test from the last tag (EC-G02)

**Adopted:**
| Seen in | Practice | Labra | ID |
|---|---|---|---|
| Home Assistant | a beta week before every monthly release | `vX.Y.0rc1` runs at the owner's lab for about a week before the final tag. The pilot is `v0.1.0rc1`. No fixed monthly cadence with one maintainer | W12 |
| Home Assistant | deprecation policy: old behaviour keeps working, users are warned in the UI, and the release it is removed in is named | a removed setting, screen or export column keeps working for ≥ 1 minor release, with a notice on `Admin ▸ System` | EC-G05 |
| Immich | images on GHCR tagged by full version, major version and `release`; compose pinned to a version; "use the compose file from the release, not `main`"; Postgres never on a rolling tag | the same scheme; the install guide says so | W12, EC-G04 |
| Paperless → Paperless-ng → Paperless-ngx | twice the single maintainer stopped and users had to fork; ngx survived as a team in a GitHub organization and stayed a drop-in replacement | GitHub organization, `MAINTAINERS.md`, a releasing guide anyone can follow. MIT keeps Labra forkable, and M26 keeps the data portable | EC-O05 |
| git-cliff (widely used) | changelog drafted from conventional commits | the draft groups commits by tracker ID; the owner edits the operator-facing wording. Runs locally and in CI, not tied to GitHub | W12 |
| Django, Ubuntu (Diátaxis) | docs split into tutorial / how-to / reference / explanation | manual pages are how-tos; "A day at the lab" (§1e) is the tutorial; settings and tracker are generated reference; ADRs and design are explanation. Folded into the M25.1 navigation | M25.1 |
| Django, Home Assistant, Immich | private vulnerability reporting; issue forms; Discussions for questions | gate 1 | EC-O06, EC-O07 |
| ERPNext, Odoo | public demo, reset nightly | synthetic seed data on its own small server | EC-O08 |

**Not adopted:**
- **release-please:** its release PRs are pushed with `GITHUB_TOKEN`, so required CI checks never run on them, and it is GitHub-only.
- **Fixed monthly releases:** one maintainer can't keep that cadence.
- **Stale-issue bot:** it closes real bugs.
- **CLA:** MIT plus plain PRs is enough.

**Sources** (for the owner; not copied into the repo):
- [Home Assistant release FAQ](https://www.home-assistant.io/faq/release/)
- [Home Assistant deprecation policy](https://developers.home-assistant.io/docs/deprecating/)
- [Immich compose file](https://github.com/immich-app/immich/blob/main/docker/docker-compose.yml)
- [Immich upgrading guide](https://docs.immich.app/install/upgrading/)
- [Immich image pinning discussion](https://github.com/immich-app/immich/discussions/10566)
- [Paperless-ng abandonment issue #1690](https://github.com/jonaswinkler/paperless-ng/issues/1690)
- [Paperless-ngx changelog](https://docs.paperless-ngx.com/changelog/)
- [PR replacing release-please with git-cliff](https://github.com/forwardsoftware/gulp-plugins/pull/138)
- [git-cliff](https://git-cliff.org/blog/)

### 18.4 Verification additions
- **Pilot tag:** `check_tracker.py` refuses the `v0.1.0rc1` tag while any gate-`P` item is open and ignores `P2`. It refuses the first tag after the pilot while any `P2` item is open.
- **Images:** an `rc` tag builds amd64 and arm64 images on GHCR with the version tags.
- **Changelog:** the git-cliff draft lists every tracker ID merged since the last tag.

## 19. Dependency pre-audit and register (owner request 2026-10-08)
**Owner's ask:**
- Before any code is written, audit every project and package Labra will use.
- Keep that list as a maintained register, recording for each one its licence, last update and maintenance status.
- Where something isn't kept up to date, record what it gives Labra and what could replace it.

**The answer has two parts:**
- **A process:** the register, a script that keeps it fresh, gates that stop anything new arriving unrecorded, and pinning (§19.1).
- **The pre-audit itself:** done 2026-10-08 from PyPI and GitHub data (§19.2). It changes six choices in the plan (§19.3).

### 19.1 The process (W13, W14, EC-I06, EC-I07)
**`docs/DEPENDENCIES.md`, the register:** one row per dependency of any kind:
- Python packages (runtime, dev and test)
- container images
- vendored JS/CSS
- CLI tools
- external services: Google Drive, Cloudflare, Healthchecks.io

Each row has these columns:
| Column | Filled by | Example |
|---|---|---|
| Component, role, where used | person | WeasyPrint · report/bill PDFs · `reports/`, `billing/` |
| Kind | person | runtime / dev / test / ops image / vendored asset / CLI / service |
| Gate | person | P, P2, 1, later (only P rows are installed in the minimal version) |
| Licence (SPDX) | script | `BSD-3-Clause` |
| Pinned version | script (from `uv.lock`, compose digests, vendor manifest) | `70.0` |
| Latest release + date | script | `70.0 · 2026-09-08` |
| Releases in last 12 months | script | 5 |
| Last commit, archived? | script | 2026-10-06 · no |
| Backing | person | foundation / company / team / single maintainer |
| **Status** | script proposes, person confirms | Active / Stable / Watch / Replace (below) |
| Why we use it (advantage) | person | only pure-Python HTML→PDF with paged-media CSS |
| Alternative + exit cost | person | Playwright print-to-PDF (Chromium, +300 MB) · medium |
| Last reviewed | person | 2026-10-08 |

**Minimum release age (owner decision 2026-10-14, W21):** no pinned version younger than 7 days. uv's `exclude-newer = "7 days"` keeps `uv lock` to such releases; `audit_deps.py --check` refuses a younger Python package (upload time in `uv.lock`) or Action, image or vendored file (release date in its Pinned cell). The only exception is a fix for a published advisory (GHSA, CVE or PYSEC ID), recorded in the register's Age exceptions table and, for Python, in `exclude-newer-package`.

**Status rules**, applied by the script and confirmed by a person:
- **Active:** a release in the last 6 months.
- **Stable:** no release for 6–24 months, but the repo still has commits *and* the job is done because the spec is frozen (QR codes, Code 128, TOTP).
- **Watch:** any of these:
  - no release for over 12 months *and* no commit for over 12 months
  - a single maintainer
  - pre-1.0 and load-bearing
  - a licence the allowlist only takes as an exception
- **Replace:** any of these:
  - archived
  - end of life announced
  - a licence change outside the allowlist
  - a supply-chain compromise without a clean recovery

  A Replace row needs an ADR and a tracker row before the next release.

**`scripts/audit_deps.py`** (stdlib + `urllib`, no new dependency):
- **Inputs:** `uv.lock`, `compose.yaml` and `static/vendor/manifest.json`.
- **Data:** PyPI JSON and GitHub REST. `GITHUB_TOKEN` comes from env when present, since unauthenticated calls hit the rate limit within one run.
- **Default run:** rewrites the script columns and prints status changes.
- **`--check`** (CI and `ci_local.sh`) fails when:
  - a dependency has no row
  - a row has no dependency behind it
  - a licence is outside the allowlist (EC-I03)
  - a `uses:` in a workflow is not a 40-character SHA (EC-I06)
  - a compose image has no digest
- **Offline:** runs with network calls write `WARN = unchecked`, never pass.

**Scheduled check:** a weekly GitHub workflow runs `audit_deps.py`. When a status changes (for example Active → Watch), it opens or updates one issue: `[W13] dependency status changed: <name>`. It never edits `master` itself.

**Gate on new dependencies:**
- Adding a package, image or vendored file without a register row fails pre-commit and CI.
- The PR body carries `Dependency: <name>, <why>, <alternative considered>`.
- Before adding one, check:
  1. Is the licence on the allowlist?
  2. Is there a release in the last 12 months, or is it Stable by the rules above?
  3. More than one maintainer, or an organization behind it?
  4. Can it be removed in under a day?
  5. Does the standard library or an existing dependency already do it?

**Reviews:**
- **Quarterly** (the §13 research re-check): a person re-reads every Watch row and the advantage and alternative columns.
- **Release checklist** (§14a M): the register must show no Replace rows without an ADR.

**Pinning (W14), the lesson from the March 2026 Trivy compromise:**
- **What happened:** attackers moved 76 existing version tags to malicious commits, so every workflow using `@v0.x` ran their code.
- **Actions:** pinned by full commit SHA with the version in a comment (`uses: actions/checkout@<sha> # v5.0.0`).
- **Images:** pinned by digest (`postgres:18.x@sha256:…`).
- **Vendored assets:** htmx, Alpine and Basecoat are kept in `static/vendor/` with their SHA-256 in `manifest.json`.
- **Updates:** Renovate bumps all three with a PR each, and CI runs on it.

### 19.2 Pre-audit result (2026-10-08)
Sources:
- **PyPI JSON:** the latest version and its date, and the number of releases since 2025-10-08.
- **GitHub API:** the last push and whether the repo is archived.
- **Project announcements:** where noted in the table.

Python-package rows are measured. Rows marked † come from the repo's last push only, because the GitHub rate limit stopped the release query. Run 1's first `audit_deps.py` run fills in those release columns.

**Runtime, minimal version (gate P):**
| Component | Licence | Latest · date | Rel. 12m | Status | Advantage / note | Alternative · exit cost |
|---|---|---|---|---|---|---|
| FastAPI | MIT | 0.142.4 · 2026-10-07 | 93 | Active | typed routes, DI; 0.x, so pin the minor | Litestar · high |
| Starlette | BSD-3 | 1.7.0 · 2026-09-23 | 22 | Active | under FastAPI | — |
| Uvicorn | BSD-3 | 0.54.0 · 2026-09-25 | 23 | Active | ASGI server | Granian · low |
| Pydantic / pydantic-settings | MIT | 2.13.5 / 2.15.0 · 2026-08 | 18 / 7 | Active | validation, typed settings (EC-K01) | — |
| SQLAlchemy | MIT | 2.1.4 · 2026-10-07 | 21 | Active | ORM + Core | — |
| Alembic | MIT | 1.20.0 · 2026-09-11 | 13 | Active | migrations | — |
| psycopg 3 | **LGPL-3.0** | 3.3.6 · 2026-09-18 | 10 | Active, licence exception | the reference Postgres driver; LGPL is fine imported unmodified, recorded in ADR-0002 | pg8000 (BSD, pure Python, slower) · low |
| PostgreSQL | PostgreSQL | 18.x † | — | Active | **18 instead of 17:** a fresh start gets one more year of support (Nov 2030) | — |
| Jinja2 | BSD-3 | 3.1.6 · 2025-03-05 | **0** | **Watch** | no release for 19 months and no commit since 2025-06-14; 3.2 has been in development since 2022. Templates + sandbox (EC-A08); also used by the docs | none at the same fit; mitigation: plain features only, sandbox tests in CI · very high |
| python-multipart | Apache-2.0 | 0.0.32 · 2026-06-04 | 12 | Active | form parsing | — |
| WeasyPrint | BSD-3 | 70.0 · 2026-09-08 | 5 | Active | paged-media CSS → PDF, no browser | Playwright print-to-PDF (+Chromium) · medium |
| pypdf | BSD-3 | 6.19.0 · 2026-09-16 | 43 | Active | letterhead overlay, dedup | — |
| pypdfium2 | BSD-3 / Apache-2.0 | 5.14.0 · 2026-10-04 | 18 | Active | fast preview PNGs | pdftoppm (GPL, as a command) · low |
| Pillow | MIT-CMU | 12.3.0 · 2026-07-01 | 5 | Active | letterhead optimisation | — |
| SQLAdmin | BSD-3 | 0.32.0 · 2026-09-20 | 15 | Dropped | not used: own HTMX admin screens instead (ADR-0010) | — |
| **pwdlib** | MIT | 0.3.1 · 2026-08-12 | 2 | **Replace** (Watch: single maintainer, 179 stars) | a thin wrapper | **argon2-cffi** directly (MIT, Hynek, active), with `check_needs_rehash` · low |
| python-barcode | MIT | 0.16.1 · 2025-08-27 | 0 | Stable | Code 128 sample labels; the spec is frozen and the repo was active in 2026-07 | own Code 128 SVG writer (~150 lines) · low |
| segno | BSD-3 | 1.6.6 · 2025-03-12 | 0 | Stable | QR codes (verify, UPI); spec frozen, repo active 2026-07 | qrcode (BSD) · low |
| Babel | BSD-3 | 2.18.0 · 2026-02-01 | 1 | Stable | Indian number grouping, translations | — |
| structlog | MIT / Apache-2.0 | 26.1.0 · 2026-06-06 | 2 | Stable | JSON logs (EC-E01) | stdlib logging + JSON formatter · low |
| DuckDB | MIT | 1.5.6 · 2026-09-28 | 90 | Active | Parquet export (M26) without pyarrow | pyarrow · low |
| vtracer (P2) | MIT | 0.6.15 · 2026-08-29 wheels | 6 | Active | raster → SVG suggestion (M17.1) | drop the feature · low |
| htmx (vendored) | 0BSD | **4.0.0 · 2026-08-28** † | — | Active | **start on 4.x** (the new major), not 2.x | — |
| Alpine.js (vendored) | MIT | 3.17.4 · 2026-09-21 † | — | Active | small UI state; **use the CSP build** (EC-A06) | plain JS · low |
| **Basecoat UI** (vendored) | MIT | 1.0.1 · 2026-06-28 † | 3 | **Watch** (single maintainer, young) | shadcn look on HTMX; vendored, so the app can't break if it stops | DaisyUI (MIT) or own Tailwind macros · medium |
| Tailwind CSS standalone CLI | MIT | repo active 2026-09-25 † | — | Active | build-time only, no Node in production | — |

**Ops (gate P):**
| Component | Licence | Activity | Status | Note / alternative |
|---|---|---|---|---|
| Docker Engine + Compose | Apache-2.0 | active | Active | Podman, containerd (nerdctl) or Incus; tested by `scripts/stack_smoke.sh` (ADR-0009) · medium |
| Caddy | Apache-2.0 | pushed 2026-10-08 † | Active | nginx, tested (`deploy/nginx/`, ADR-0009) · low |
| cloudflared | Apache-2.0 | pushed 2026-10-05 † | Active, **service lock-in** | the program is open but depends on Cloudflare's service; alternatives are Tailscale/Headscale or NetBird (Compose profiles, start tested, ADR-0009) or WireGuard via the standby VPS (an ADR-0007 edge) · medium |
| restic | BSD-2 | pushed 2026-10-01 † | Active | Borg (BSD) · medium |
| rclone | MIT | pushed 2026-10-07 † | Active | restic's own S3/B2 backends · low |
| Healthchecks.io / Uptime Kuma | BSD-3 / MIT | active † | Active | either one; Healthchecks can be self-hosted later |
| poppler-utils (`pdftocairo`) | GPL | Debian package | Stable | separate command only (EC-I03) |

**Dev and test (gate P):**
| Component | Licence | Latest · date | Rel. 12m | Status | Note / alternative |
|---|---|---|---|---|---|
| uv, ruff | MIT / Apache-2.0 | ruff 0.16.10 · 2026-10-01 | many | Active | — |
| pyright | MIT | 1.1.414 · 2026-09-10 | 8 | Active | ty (Astral) is still pre-1.0: re-check at gate 1 |
| pytest | MIT | 9.1.1 · 2026-06-19 | 6 | Active | — |
| testcontainers | Apache-2.0 | 4.15.0 · 2026-07-24 | 9 | Active | — |
| hypothesis | MPL-2.0 (test-only) | 6.168.5 · 2026-10-05 | 133 | Active | — |
| Faker | MIT | 40.41.0 · 2026-10-05 | 62 | Active | — |
| **factory-boy** | MIT | 3.3.3 · 2025-02-03 | **0** | **Replace** (Watch: 20 months, 209 open issues) | plain factory functions over Faker in `tests/factories.py` (one dependency fewer); polyfactory (MIT, active) if that grows · low |
| Playwright | Apache-2.0 | 1.63.0 · 2026-09-15 | 8 | Active | — |
| pdfplumber | MIT | 0.11.10 · 2026-06-15 | 3 | Stable | — |
| pre-commit | MIT | 4.6.2 · 2026-08-10 | 6 | Active | — |
| gitleaks / osv-scanner / pip-audit / pip-licenses | MIT / Apache / Apache / MIT | active | Active | — |
| git-cliff | MIT / Apache-2.0 | 2.14.2 · 2026-09-18 | 4 | Active | — |
| **MkDocs** | BSD-2 | 1.6.1 · 2024-08-30 | 0 (only `2.0.devN`) | **Replace** | `mkdocs/mkdocs` has had no commit since 2025-10-20. MkDocs 2.0 is a rewrite (`encode/mkdocs`, published with no licence file) that drops plugins and themes |
| **Material for MkDocs** | MIT | 9.7.7 · 2026-07-17 | 10 | **Replace** | maintenance mode since 2025-11-05, **end of life 2026-11-05**, before the pilot |
| **Zensical** (replacement) | MIT | 0.0.68 · 2026-10-05 | 65 | **Watch** (pre-1.0) | by the Material team; reads `mkdocs.yml`. Fallback: freeze MkDocs 1.6.1 + Material 9.7.x (still builds offline) · low |

**Gate 1 / later (record now, re-audit when built):**
| Component | Licence | Latest · date | Status | Note |
|---|---|---|---|---|
| pyotp | MIT | 2.10.0 · 2026-06-14 | Stable | TOTP spec frozen |
| cyclonedx-bom, cosign | Apache-2.0 | 7.5.0 · 2026-09-29 / active | Active | — |
| mutmut, locust | BSD-3 / MIT | 3.8.0 / 2.46.7 · 2026-09/10 | Active | — |
| **Trivy** | Apache-2.0 | active | **Replace (don't adopt)** | Actions tags and the v0.69.4 binary were compromised 2026-03-19 (CVE-2026-33634). Use osv-scanner image scanning (already in the stack) or grype |
| Procrastinate | MIT | 3.10.0 · 2026-09-23 | Active | — |
| pyHanko | MIT | 0.37.0 · 2026-08-31 | Active | — |
| fhir.resources | BSD-3 | 8.3.0 · 2026-07-03 | Stable | — |
| imap-tools | Apache-2.0 | 1.15.1 · 2026-10-06 | Active | — |
| **openpyxl** | MIT | 3.1.5 · 2024-06-28 | **Replace** (27 months, no release) | XlsxWriter (BSD-2, active) for Excel export when X21 is built; CSV for import |
| GlitchTip, pgBackRest / WAL-G | MIT / MIT / Apache-2.0 | active † | Active | — |

### 19.3 What the audit changes in the plan (edits applied above)
| # | Change | Where |
|---|---|---|
| 1 | **Docs site on Zensical**, not MkDocs Material: Material reaches end of life on 2026-11-05 and MkDocs 1.x is unmaintained. `mkdocs.yml` stays the config file. If Zensical's strict mode or a needed feature is missing at Run 1, freeze MkDocs 1.6.1 + Material 9.7.x and record that in an ADR | §1a stack, §4, M25.1, §16.2 steps 4–5, §16.4 |
| 2 | **htmx 4.x** (a new major since 2026-08-28) and **Alpine CSP build**; htmx `allowEval` off, so the CSP has no `unsafe-eval` | §1a stack, EC-A06 |
| 3 | **argon2-cffi directly** instead of pwdlib | §1a stack, §4 Auth |
| 4 | **Plain factory functions** instead of factory-boy | §4 Dev |
| 5 | **No openpyxl** in the minimal version; XlsxWriter when X21 is built | §4 Files |
| 6 | **No Trivy**: image scanning by osv-scanner or grype; **every Action pinned by SHA, every image by digest** | EC-I05, new EC-I06, W14 |
| 7 | **Licence allowlist** widened precisely: 0BSD (htmx), MIT-CMU (Pillow), PostgreSQL; LGPL-3.0 only for psycopg; MPL-2.0 test-only | EC-I03, ADR-0002 |
| 8 | **Postgres 18** instead of 17 | §1a, §3, §4, §16.2 step 6 |
| 9 | ~~SQLAdmin links point to `smithyhq/sqladmin`~~ (SQLAdmin dropped, ADR-0010) | register |

**Watch list to re-check each quarter:**
- **Jinja2:** no viable alternative; mitigated by sandbox tests.
- **Basecoat:** vendored, so a stop doesn't break the app.
- **Zensical:** pre-1.0.
- **psycopg:** licence exception.
- **cloudflared:** service lock-in.

### 19.4 Verification
- **Coverage:** `audit_deps.py --check` passes on Run 1's tree, and removing a row from `DEPENDENCIES.md` makes it fail.
- **Pinning:**
  - A workflow with `uses: actions/checkout@v5` fails.
  - A compose image without `@sha256:` fails.
  - Editing a vendored file without updating `manifest.json` fails.
- **Licences:** adding a GPL Python package fails the licence stage. psycopg passes only through its named exception.
- **Offline:** with no network, the script prints `WARN = unchecked` and exits non-zero in CI.
- **Scheduled run:** a dry run on a fork opens exactly one issue when a status is changed by hand.

**Sources** (for the owner; not copied into the repo):
- [Material for MkDocs: Zensical announcement and maintenance mode](https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/)
- [Material for MkDocs releases](https://github.com/squidfunk/mkdocs-material/releases)
- [Renovate's discussion of migrating to Zensical](https://github.com/renovatebot/renovate/discussions/39232)
- [Microsoft: the Trivy supply-chain compromise](https://www.microsoft.com/en-us/security/blog/2026/03/24/detecting-investigating-defending-against-trivy-supply-chain-compromise/)
- [Snyk: the Trivy GitHub Actions compromise](https://snyk.io/articles/trivy-github-actions-supply-chain-compromise/)
- [Jinja2 on PyPI](https://pypi.org/project/Jinja2/)
- [Jinja 3.2.x development docs](https://jinja.palletsprojects.com/en/latest/)

## Appendix A. The owner's current report workbook (extracted 2026-10-06; source Excel to be deleted)
**What it was:** the owner's current way of producing reports: one Excel workbook, **one sheet per test or test combination** (91 sheets). Staff overwrite the patient header and results on a sheet, then print it. It holds report templates, external-lab price lists, a bill, sales and invoice sheets, and a sample sticker.

**What was kept, what wasn't:**
- **Kept:** test and parameter names, departments, units, methods, reference text and comment/interpretation text, extracted by script exactly as printed (typos included).
- **Not kept:**
  - patient names, IDs, ages, dates, referring doctors and result values (real patient data, never stored)
  - staff and signatory names
  - external-lab price lists
  - the complaint letter
- **Not extracted at all:** the BILL, BILL PDF, SALES, invoices and STICKER sheets contain patient data and weren't read. If their column layout is wanted, the owner should note the column headers before deleting the file.
- **Repo rule:** this appendix may go into the repo with the plan, since it holds no patient data, but it must stay unattributed: no lab or staff names.

**Layout observations (feed §7.0):**
- **Header block, the same on every sheet:**
  - Name · Pt.ID
  - Age / Sex · Collected On (date + time)
  - Ref. By · Reported On
  - then `DEPARTMENT OF <X>`, between dashed rules
- **Columns:** `Test | Result | Units | Reference Value` (63 sheets). Urine routine uses `Test | Result | Reference Value | Method`.
- **Method:** printed as a line under the test (`Method : Cyanmethaemoglobin`). Labra maps this to `test_method` in the panel heading.
- **Reference text** is multi-line free text mixing sex, age and pregnancy ranges and guideline tiers. This is exactly the free text §1d replaces with `reference_range` rows (sex, age in days, plus a `condition` column, below) and `reference_band` tiers.
- **Comment / Interpretation blocks** are per-test patient-education text, repeated on every sheet that contains the test (the glucose comment appears on about 15 sheets). Labra: `test.interpretation_text`, printed once per test, with a per-report "include interpretation" switch.
- **`(**RECHECKED)`** is typed next to a value that was re-run. Labra: a `result.rechecked` flag (with an audited re-run), printed as a footnote.
- **Footer:** `End of Report`, pathologist signature on the left, technician on the right. Labra: signatory block plus "entered by" (technician) line.
- **Combinations as sheets** (Sugar F+PP+BP, ESR+uric acid male/female, Widal+MP/MF, viral markers) are really **packages**. They seed `package` rows. The male/female sheet copies go away, because ranges are chosen by sex.
- **Non-lab observations** in the same report (height, weight, BMI, blood pressure, Mantoux induration after 48 h) need `result_type` numeric with no range. BP is a two-number value (`120/80`), so the model needs a `text` parameter with a pattern check.

**Plan changes this implies** (small; fold into §5 when implementing):
- `reference_range.condition` (`pregnancy_t1/t2/t3`, `luteal`, `postmenopausal`, …), nullable. Seen on TSH, ESR and progesterone.
- `result.rechecked boolean` + audit, printed as a "Rechecked" footnote.
- Packages seeded from the sheet combinations below; starter catalog (M24) cross-checked against this list so every test the lab already reports is present.
- Flagged for the pathologist's review, not imported as-is. Several printed ranges contradict each other or current guidelines:
  - Hb has three male ranges across sheets (13–18, 13–17, 12–17)
  - triglyceride "Desirable 160" is not the NCEP < 150
  - urine "Nitrate" should be "Nitrite"
  - "Westerngreen" should be "Westergren"
  - LFT globulin and A/G have no printed formula

**Sheets → candidate packages:** HIV; urine sugar + albumin; LFT / bilirubin (adult, newborn); BMI + BP; HbA1c (+ average glucose); Hb; RBS + uric acid; urine culture & sensitivity; HBsAg + VDRL; TSH; FBS + blood group; sugar + Hb; calcium + ESR (M/F); total cholesterol + creatinine + Hb; complete urine; FBS; sugar F/PP (+BP, +urine, lunch/dinner); RBS; renal profile (adult, baby); SGOT/SGPT; Hb + grouping; TFT; calcium + TFT; urea; creatinine; uric acid; RBS + urea + creatinine; Mantoux; ESR + uric acid (M/F); CRP + ESR; ESR (M/F); GTT (2 h, 1 h + 2 h, with urine); total cholesterol; occult blood; Widal (+ MP/MF); dengue (IgG/IgM/NS1); MP/MF (QBC); CRP (+ Hb); troponin I; LDH; progesterone; viral markers; HBsAg + HCV; HCV; HBsAg + HIV; HIV ELISA; VDRL; urine pregnancy; BT/CT; grouping (+ BT/CT); CBC.

### A.1 Test catalog as printed (one row per distinct parameter name; spelling variants kept)
| Test / parameter | Department | Unit(s) | Method | Reference text as printed | Source sheet(s) |
|---|---|---|---|---|---|
| HIV 1 AND 2 Antibody | Immuno-Serology | S/Co | ( ELISA | Negative : < 1.0; Positive : > 1.0 | HBSAG&HIV (2), HIV, HIV ELISA, viral markers, viral markers (2) |
| Albumin Urine/Protein Urine | Biochemistry |  | Sulphosalicylic acid | Negative | U(C), URINE SUG,ALB |
| Glucose Urine | Biochemistry |  | Benedicts | Negative | U(C), URINE SUG,ALB |
| Total Bilirubin | Biochemistry | mg/dl |  | 0.3-1.2; Adults : 0.3 -1.2; Newborn full term; 0-1 days: 2.0-6.0; 1-2 days: 6.0-10.0; 3-5 days: 4.0-8.0 | BIL, BILIRUBIN (2), BILIRUBIN (newborn), LFT |
| Direct Bilirubin | Biochemistry | mg/dl |  | 0-0.3 | BIL, BILIRUBIN (2), LFT |
| Indirect Bilirubin | Biochemistry | mg/dl |  | 0-1.0; Female up to 36; 0.3-1.0 | BIL, BILIRUBIN (2), LFT |
| Height |  | cm |  |  | BMI |
| Weight |  | kg |  |  | BMI |
| BMI |  | kg/m² |  |  | BMI |
| BLOOD PRESSURE |  | mm/hg |  | 120/80 | BMI, SUGAR U(F) (PP) & BP |
| HbA1c - (HPLC) | Biochemistry | % | Fully Automated H.P.L.C using | Below 5.7% : Normal; 5.7% - 6.4% : Prediabetic; Boirad Variant II Turbo > = 6.5% : Diabetic | HbA1c, HbA1c (2) |
| Average Blood Glucose ( ABG) | Biochemistry | mg/dl | Derived from HBA1c Values | 90-120mg/dl : Good Control 90-120mg/dl; Calculated 121-150mg/dl : Fair Control; 151-180mg/dl : Unsatisfactory Control; >180mg/dl : Poor Control; Guidance for Known Diabetics; Below 6.5% : Good Control; >8% : Poor Control | HbA1c, HbA1c (2) |
| HAEMOGLOBIN | Biochemistry | gm%/gms% | Cyanmethaemoglobin; Non - Cyandie | Male : 13-18; Female : 12-16; Male : 13-17; Male : 12-17; Female : 12-15 | CRP&HB, HB, HB  (2), HB &GROUPING (2), RBS&HB, SUGAR  HB, SUGAR U& HB, cbc (info) |
| Blood Glucose Fasting (FBS) | Biochemistry | mg/dl |  | 70-110 | GTT ( U ), GTT (2), GTT (3), GTT 2Hrs, RBS&UREA,CREA, RBS&URIC ACID, SUGAR  HB, SUGAR ( F ) ( PP ), SUGAR U& HB, SUGAR U(F) (PP), SUGAR U(F) (PP) & BP |
| Uric Acid | Biochemistry | mg/dl |  | 2.4 - 5.4 : 1 - 10 Yrs,; 2.7 - 5.9 : 11 Years,; Adults; Male : 3.5-7.2; Female : 2.6-6.0; Newborn: 2.0-6.5 mg/dL; Women : 2.4-5.7 | ESR & URIC ACID ( MALE ), ESR & URIC ACID (FEMALE), RBS&URIC ACID, RENAL PROFILE(BABY), URIC ACID |
| Hepatitis 'B' Surface Antigen (HBsAg) | Immuno-Serology | S/Co | ( ELISA | Negative : < 1.0; Positive : > 1.0 | FBS BLD GRP (3), HBSAG & HCV ELISA, HBSAG&HIV (2), HBSAG&VDRL, viral markers, viral markers (2) |
| VDRL | Immuno-Serology |  |  |  | HBSAG&VDRL, VDRL |
| Thyroid Stimulating Hormone (TSH) |  | µIU/mL | Ultra-sensitive Chemiluminescence | 0.46 - 8.10 : 1 Yrs - 5 Years; 0.36 - 5.80 : 6 Yrs - 18 Years; 0.38 - 5.33 : 18 Yrs -88 Years; 0.50 - 8.90 : > 88 Years; Pregnancy ranges:; 1st Trimester:0.05 - 3.70; 2nd Trimester:0.31 - 4.35; 3rd Trimester:0.41 - 5.18.; 0.52 - 16.0 : 1 Day - 30 Days; 0.55 - 7.10 : 1 Mon - 5 Years; 0.37 - 6.00 : 6 Yrs - 18 Years; 0.38 - 5.33 : 18 Yrs -88Years | CALCIUM,TFT, TFT, TSH |
| Blood Glucose Fasting (FBS) | Biochemistry | mg/dl |  | 70-110 | FBS, FBS BLD GRP (3) |
| Blood Glucose (PPBS) | Biochemistry | mg/dl |  | 80-140 | SUGAR  HB, SUGAR ( F ) ( PP ), SUGAR U& HB, SUGAR U(F) (PP), SUGAR U(F) (PP) & BP |
| CALCIUM,Serum |  | mg/dl | Spectrophotometry | 8.8 - 10.6 | CALCIUM ESR ( FEMALE ), CALCIUM ESR (MALE), CALCIUM,TFT |
| ESR (1 HOUR) |  | mm/mm/hr | Westerngreen | <10; <12; Pregnancy first trimester : 48; Pregnancy Second trimester : 70; <20; Male : 5-15; Female : 5-20 | CALCIUM ESR ( FEMALE ), CALCIUM ESR (MALE), ESR & URIC ACID ( MALE ), ESR & URIC ACID (FEMALE), ESR ( FEMALE ) (2), ESR (MALE), cbc (info) |
| Colour | Clinical Pathology |  |  |  | U(C) |
| Appearance | Clinical Pathology |  |  |  | U(C) |
| pH | Clinical Pathology |  | Double indicator | 5.0-8.5 | U(C) |
| Specific Gravity | Clinical Pathology |  | Ion Exchange | 1.005-1.030; Chemical Examination | U(C) |
| Urobilinogen | Clinical Pathology |  | Ehrlichs's reagent | Negative | U(C) |
| Bile Salts | Clinical Pathology |  | Hay's Sulphur | Negative | U(C) |
| Bile Pigments | Clinical Pathology |  | Fouchets method | Negative | U(C) |
| Blood | Clinical Pathology |  | Diazonium Method | Negative | U(C) |
| ketone | Clinical Pathology |  | Rotheras method | Negative | U(C) |
| Nitrate | Clinical Pathology |  | Diazonium Method | Negative; Microscopic Examination | U(C) |
| Pus Cells(Leucocytes) | Clinical Pathology |  | Microscopy | 0-5 | U(C) |
| Epithelial Cells | Clinical Pathology |  | Microscopy | 0-5 | U(C) |
| RBCs | Clinical Pathology |  | Microscopy | Nil | U(C) |
| Casts | Clinical Pathology |  | Microscopy | Nil | U(C) |
| Crystals | Clinical Pathology |  | Microscopy | Nil | U(C) |
| Bacteria | Clinical Pathology |  | Microscopy | Absent | U(C) |
| Budding Yeast Cells | Clinical Pathology |  | Microscopy | Nil | U(C) |
| Others | Clinical Pathology |  | Microscopy | Absent | U(C) |
| URINE (F) | Biochemistry |  |  |  | SUGAR U(F) (PP), SUGAR U(F) (PP) & BP |
| URINE (PP) | Biochemistry |  |  |  | SUGAR U(F) (PP), SUGAR U(F) (PP) & BP |
| Blood Glucose Random (RBS) | Biochemistry | mg/dl |  | 80-140 | RBS&HB, SUGAR (RBS) |
| UREA | Biochemistry | mg/dl |  | 15-45; 11 - 36 : 1 Yrs- 3 Yrs,; 15 - 36 : 4 Yrs- 13 Yrs,; Adults; Male <50 : 19-45; Male >50 : 18-55; Female <50 : 13-40; Female >50 : 21-43 | RBS&UREA,CREA, RENAL PROFILE(BABY), Renal, UREA |
| CREATININE | Biochemistry | mg/dl |  | Men : 0.7-1.3; Women : 0.6-1.1; 0.2 - 0.4 : 2 - 12 Month,; 0.2 - 0.5 : 1 Yrs- 2 Yrs,; 0.3 - 0.7 : 3 Yrs- 4 Yrs,; Adults; Male : 0.7-1.3; Female : 0.6-1.1 | CREATININE, RBS&UREA,CREA, RENAL PROFILE(BABY), Renal |
| URIC ACID | Biochemistry | mg/dl |  | Female : 2.6-6.0; Newborn: 2.0-6.5 mg/dL | Renal |
| Total Cholesterol | Biochemistry | mg/dl |  | Desirable : < 200; Borderline High :200-239; High : > 240; likely to develop heart disease. | LIPID, T.CHO |
| HDL Cholesterol | Biochemistry | mg/dl |  | Low : < 30; High : > 80 | LIPID |
| Total Triglycerides | Biochemistry | mg/dl |  | Desirable level : 160; Borderline : 161-199; High : 200-499; Very High : 500 | LIPID |
| VLDL Cholesterol | Biochemistry | mg/dl |  | <=30 | LIPID |
| LDL Cholesterol | Biochemistry | mg/dl |  | <100:Optimal | LIPID |
| Non - HDL Cholesterol | Biochemistry | mg/dl |  | <130 | LIPID |
| Chol / HDL Ratio | Biochemistry |  |  | Low Risk : 3.3-4.4; Average Risk : 4.5-7.1; Moderate Risk : 7.2-11.0; High Risk : >11.0 | LIPID |
| HDL/LDL Cholesterol Ratio | Biochemistry |  |  |  | LIPID |
| LDL/HDL Ratio | Biochemistry |  |  |  | LIPID |
| SGOT / AST | Biochemistry | U/L |  | 15-37 | LFT |
| SGPT /ALT | Biochemistry | U/L |  | 16-63 | LFT, OT&PT |
| Alkaline Phosphatase | Biochemistry | U/L |  | 33-98 | LFT |
| Total Protein | Biochemistry | g/dl |  | 6.6-8.8 | LFT |
| Albumin | Biochemistry | g/dl |  | 3.5-5.2 | LFT |
| Globulin | Biochemistry | g/dl |  | 2.5-4.5 | LFT |
| A/G Ratio | Biochemistry |  |  |  | LFT |
| Gamma Glutamyl Transferase (GGT) | Biochemistry | U/L |  | Male up to 55; Female up to 36 | LFT |
| SGOT /AST | Haematology | U/L |  | 15-37 | OT&PT |
| BLOOD GROUP | Biochemistry |  |  |  | GROUPING, GROUPING & BTCT, HB &GROUPING (2) |
| Rh Typing | Biochemistry |  |  |  | GROUPING, GROUPING & BTCT, HB &GROUPING (2) |
| TriIodothyronine Total ( TT3 ) |  | ng/dl | Chemiluminescence | 80 - 253 : 1 Yr- 10 Yr,; 76 - 199 : 11 Yr- 15 Yr,; 69 - 201 : 16 Yr- 18 Yr,; 87 - 178 : > 18 years. | CALCIUM,TFT, TFT |
| Thyroxine- Total ( TT4) |  | µg/dL | Chemiluminescence | 5.9 - 21.5 : 0-31 Days,; 5.9 - 21.5 : 0-1 Month,; 6.4 - 13.9 : 2-12 Months,; 6.09 - 12.23 : >1 Yr | CALCIUM,TFT, TFT |
| PHOSPHORUS |  | mg/dl | Spectrophotometry | 2.5 - 4.5 | CALCIUM,TFT |
| Induration (mm) | Haematology | mm |  | >15mm | Mantoux |
| Result after 48 hours | Haematology |  |  |  | Mantoux |
| Urine ( F ) | Biochemistry |  |  |  | GTT ( U ), GTT 2Hrs |
| Blood Glucose (2hrs) | Biochemistry | mg/dl |  |  | GTT 2Hrs |
| Urine (2hr) | Biochemistry |  |  |  | GTT ( U ), GTT 2Hrs |
| Blood Glucose (1hr) | Biochemistry | mg/dl |  |  | GTT ( U ) |
| Urine (1hr) | Biochemistry |  |  |  | GTT ( U ) |
| Blood Glucose (2hr) | Biochemistry | mg/dl |  |  | GTT ( U ) |
| Blood Glucose (1hr) | Biochemistry | mg/dl |  |  | GTT (2) |
| Blood Glucose (2hr) | Biochemistry | mg/dl |  |  | GTT (2), GTT (3) |
| Urine (F) | Biochemistry |  |  |  | SUGAR U& HB |
| Urine (PP) | Biochemistry |  |  |  | SUGAR U& HB |
| S.Typhi O Antigen | Serology |  |  | < 1:20 Negative | WIDAL, WIDAL MPMF |
| S.Typhi H Antigen | Serology |  |  | < 1:20 Negative | WIDAL, WIDAL MPMF |
| S.Para Typhi AH Antigen | Serology |  |  | < 1:20 Negative | WIDAL, WIDAL MPMF |
| S.Para Typhi BH Antigen | Serology |  |  | < 1:20 Negative | WIDAL, WIDAL MPMF |
| MP/MF ( QBC ) |  |  |  | Clinical Significance: | MP MF, WIDAL MPMF |
| DENGUE IgG ANTIBODY, Serum | Immuno-Serology |  | ELISA | Negative: < 9.0, / Equivocal: 9.0 - 11.0, / Positive: > 11.0; Negative / Positive | DENGUE, DENGUE (2) |
| DENGUE IgM ANTIBODY, Serum | Immuno-Serology |  | ELISA | Negative: < 9.0, / Equivocal: 9.0 - 11.0, / Positive: > 11.0; Negative / Positive | DENGUE, DENGUE (2) |
| DENGUE NS-1 ANTIGEN, Serum | Immuno-Serology |  |  | Negative / Positive | DENGUE |
| CRP | Biochemistry | mg/l | Turbidometry | 0-6 | CRP&HB |
| Troponin I (hsTnI) | Biochemistry |  |  | Negative/Positive; be in the blood. | Troponin I |
| Progesterone | Biochemistry-Special | ng/ml |  | Luteal Phase: 3.34-25.56 / ng/ml; Mid Luteal Phase: 4.44-28.03 ng/ml; Postmenopausal: 0.00-0.73 / ng/ml; 1st Trimester: 11.2-90.0 / ng/ml; 2nd Trimester: 25.55-89.4 / ng/ml; 3rd Trimester: 48.4-422.5 / ng/ml | PROGESTERONE |
| Hepatitis 'C' Virus | Immuno-Serology | S/Co |  | Negative : <1.0; Positive : >1.0 | HBSAG & HCV ELISA, HCV (2), viral markers |
| URINE PREGNANCY TEST | Biochemistry |  |  |  | PREGNANCY U |
| BLEEDING TIME (BT) | Haematology |  |  | 2 - 6 Minutes | BT CT, GROUPING & BTCT |
| CLOTTING TIME (CT) | Haematology |  |  | 3 - 10 Minutes | BT CT, GROUPING & BTCT |
| Method : Automated flow cytometry | Haematology | Cells/cumm | Automated flow cytometry | 4000-11000 | cbc (info) |
| Neutrophils | Haematology | % |  | 40-75; 45-75 | cbc, cbc (info) |
| Lymphocytes | Haematology | % |  | 20-45; 30-40 | cbc, cbc (info) |
| Eosinophils | Haematology | % |  | 01-06; 1-6 | cbc, cbc (info) |
| Monocytes | Haematology | % |  | 02-10 | cbc (info) |
| Basophils | Haematology | % |  | 00-01; 0-2 | cbc, cbc (info) |
| RBC | Haematology | Millions/cmm | Electrical Impedance | Male : 4.6-6.0; Female : 4.2-5.4 | cbc (info) |
| PCV | Haematology | % | Electrical Impedance | Male : 40-50; Female : 36-46 | cbc (info) |
| PLATELET COUNT | Haematology | lakhs/cumm | Electrical Impedance | 1.5 - 4.1 | cbc (info) |
| Haemoglobin | Haematology | gm% |  | 11-15 | cbc |
| RBC Count | Haematology | Millions/cumm |  | 3.8-4.8 | cbc |
| Total WBC Count | Haematology | Cells/cumm |  | 4000-10000 | cbc |
| Platelet Count | Haematology | lakhs/cumm |  | 1.5-4.2 | cbc |
| Packed Cell Volume(PCV) | Haematology | % |  | 30-45 | cbc |
| Mean Corpuscular Volume (MCV) | Haematology | fL |  | 79-98 | cbc |
| Mean Corpuscular Hb (MCH) | Haematology | pg |  | 25-35 | cbc |
| Mean Corpuscular Hb | Haematology | g/dl |  | 32-36; Concentration (MCHC); Differential Count By Flowcytometry/Microscopy | cbc |
| monocytes | Haematology | % |  | 2-10 | cbc |

**Comment / interpretation blocks (deduplicated, typos kept as printed):**
- *Indirect Bilirubin*: Interpretation: Liver function test aid in the diagnosis of various pre hepatic, hepatic & post hepatic causes of dysfuntion in anemias, viral & alcoholic hepatitis and cholestasis of obstructive causes. The test encompasses hepatic excreatory, synthetic function and also hepatic parenchymal cell damage. LFT helps in evaluating severity, monitoring therapy and assessing prognosis of liver disease and dysfunction.
- *Average Blood Glucose ( ABG)*: Comment: Ref.for Biological Reference Intervals: American Diabetes Association.
- *Average Blood Glucose ( ABG)*: INTERPRETATION: The A1C test measures your average blood glucose for the past 2 to 3 months. Diabetes is diagnosed at an A1C of greater than or equal to
- *HAEMOGLOBIN*: Comment: Hemoglobin is a protein in your red blood cells that carries oxygen from your lungs to the rest of your body. If your hb levels are abnormal, it may be a sign that you have a blood disorder.Symptoms of anemia, which include weakness, dizziness, pale skin, and cold hands and feet
- *HAEMOGLOBIN*: INTERPRETATION: C- Reactive protein ( CRP ) is a acute phase protein that is involved in the activation of complement, acceleration of phagocytosis and detoxification of substances released from dameged tissue. As such, CRP is considered to be one of the most sensitive indicators of inflammation. In response to an inflammatory stimulus, a rise in CRP may be detected with 6 hours. CRP is a sensitive though considered to be a non-specific indicator of acute phase reactants. Measurement of C- Reactive Protein is most frequently used for the evaluation of injury to body tissue or for the detection of an inflammatory event somewhere in the body. CRP levels in serum are typically elevated in patients with arthritis or liver diseases such as Hepatitis A, Hepatitis B or billary cirrhosis and after severe infections such as septic shock.
- *Blood Glucose Fasting (FBS)*: Comment: Ref.for Biological Reference Intervals: American Diabetic Assiosation. A blood glucose test measures the glucose levels in your blood. Glucose is a type of sugar. It is your body's main source of energy. Symptoms of high blood glucose levels include increased thirst, more frequent urination, Blurred vision, Fatigue, Wounds that are
- *ESR (1 HOUR)*: Comment: Note: ESR is an acute phase reactant which indicates presence and intensity of an inflammatory process. ESR is elevated in a wide range of organic diseases. ESR is not a specific and diagnostic test for any disease. However, it is helpful in differentiating functional from organic disease.Extremely high levels are found in cases of malignancy, hematologic diseases, collagen disorders and renal diseases
- *T C & CREAT & HB*: Comment: Total cholesterol is a measure of the total amount of cholesterol in your blood, including HDL ("good"), LDL ("bad"), and VLDL components. High blood cholesterol increases the risk of cardiovascular diseases such as a heart attack.
- *T C & CREAT & HB*: Comment: Creatinine is a waste product from muscle metabolism, broken down from creatine phosphate, and is a vital indicator of kidney function.Healthy kidneys filter creatinine from the blood, high serum creatinine levels typically indicate reduced
- *UREA*: Comment: Serum urea is a measure of the amount of urea in your blood. Urea is a waste product created when your body breaks down protein. A serum urea test can help determine how well your kidneys are functioning
- *CREATININE*: Comment: Creatinine is a waste product that comes from the digestion of protein in your food and the normal breakdown of muscle tissue. It is removed from the blood through your kidneys. Everyone has some creatinine in their blood, but too much can be a sign of a possible kidney problem
- *URIC ACID*: Comment: Uric acid is a waste product formed when the body breaks down purines, which are found in body tissues and various foods, such as red meat, alcohol, and high-fructose items. Normally, it dissolves in blood and is excreted by the kidneys. High levels (hyperuricemia) can form crystals, leading to gout and kidney stones
- *Result after 48 hours*: Interpretation: Induration measuring 10 mm or more is considered positive which shows hypersensitivity to tuberculoprotein. It indicates past or present infection with Mycobacterium tuberculosis. TB Skin Test (Mantoux) Interpretation Guide
- *Total Cholesterol*: Comment: A lipid profile that measures the amount of cholesterol and fats called triglycerides in the blood. These measurements give the doctor a quick snapshot of what's going on in blood. Cholesterol and triglycerides in the blood can clog arteries, making you more
- *S.Para Typhi BH Antigen*: Comment: Widal test is an agglutination test employed for serological diagnosis of enteric fever. Single test is usually of not much value. A rise in titre between two sera specimens is more meaningful than a single test. Demonstrating four-fold rise of antibody titre in acute and convalescent sera is significant. Antibodies begin to arise during end of first week. The titres increase during second, third and fourth week after which it gradually declines. An antibody titre of 100 or more for O antigen and a titre in excess of 200 for H antigens are considered significant. The results to be interpreted with relevant clinical findings and prevailing Baseline titre of O and H agglutinin in local population. Previous typhoid vaccination may contribute to elevated agglutinins in the non-infected population. > Cross-reactions are encountered when antibody produced by non-typhoidal antigens reacts with typhoid-specific antigens. Several other diseases caused by non Salmonella organisms (malaria, dengue, miliary tuberculosis, endocarditis, chronic liver disease, brucellosis, etc) have been shown to exhibit this cross-reactivity in typhoid endemic regions may cause false positive Widal agglutination test > Prior use of antibiotics as seen with the widespread antibiotic abuse can dampen antibody response giving a low titre in the Widal test > The Widal agglutination titre varies with the geographic location based on the endemicity of the enteric fever, prevalence of non typhoid salmonellae infection and other infections which cross react with salmonella antigen. > Past infection with serotype typhi or another non-typhoidal Salmonella serotype that shares common antigens gives false positive Widal test.
- *DENGUE IgM ANTIBODY, Serum*: Comment: The presence of Dengue Non Structural Protein 1 (NS1) antigen is consistent with acute phase infection with Dengue Virus. / The NS1 antigen may be negative if specimen is collected immediately following Dengue Virus infection ( < 24 - 48 hours ) and is rarely detectable following 9 to 10 days of symptoms
- *Troponin I (hsTnI)*: Comment: A troponin test measures the levels of troponin I proteins in the blood. These proteins are released when the heart muscle has been damaged, such as occurs with a heart attack. The more damage there is to the heart, the greater the amount of troponin I there will
- *LDH*: INTERPRETATION: Increased levels are found in myocardial infarction, pulmonary diseases, hepatic diseases, hemolytic anrmia, renal diseases and muscular dystrophy Elevation in acute MI reaches a peack in 48-72 hrs. prolonged elevations (10-14 days) are useful in the late diagnosis of the
- *Hepatitis 'C' Virus*: INTERPRETATION: Hepatitis C virus (HCV) is a hepatotropic virus which is one of the major causes of liver disease and a potential cause of substantial morbidity and mortality worldwide.. HCV causes chronic hepatitis in about 80% of those infected by it . The mainstay in diagnosing infection with HCV is to initially screen high risk groups for antibodies to HCV (anti-HCV).
- *CLOTTING TIME (CT)*: Comment: This test is performed to check the level of bleeding and the amount of time taken by your blood to clot in order to stop bleeding. It is useful in detecting Coagulation Disorder, Epistaxis, Platelet Disorder.
