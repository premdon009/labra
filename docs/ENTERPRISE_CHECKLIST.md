# Labra enterprise checklist
"Enterprise grade" here means: a lab can trust it with patient data and money every day, recover from any single failure, pass a NABL/DPDP audit, and upgrade without fear. It's sized for a small lab on an old laptop, not big-company infrastructure.

Committed to the repo as `docs/ENTERPRISE_CHECKLIST.md`. Each item has a **gate**:
- **P** = must pass before the pilot (minimal version)
- **1** = before calling it 1.0 / offering to other labs
- **L** = later

CI enforces the items marked *(CI)*. The release checklist (section M) links back here.

## A. Security
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

## B. Data integrity and money
- [ ] **P** `EC-B01` Money as `Decimal`, one calculation module; hypothesis property tests *(CI)*
- [ ] **P** `EC-B02` Gapless, unique document numbers under concurrency (row lock on `number_series`); test with 20 parallel bills *(CI)*
- [ ] **P** `EC-B03` Optimistic locking (`row_version`) on edits; a stale edit shows "changed by X, reload"
- [ ] **P** `EC-B04` Database constraints, not just app checks: foreign keys, `CHECK` (amount ≥ 0, paid ≤ net), unique keys, `NOT NULL`
- [ ] **P** `EC-B05` Released reports and issued bills are immutable; corrections only as amendment / credit note / cancellation with reason *(CI test)*
- [ ] **P** `EC-B06` Append-only audit log with a hash chain; a nightly job verifies the chain and alerts on a break
- [ ] **P** `EC-B07` Idempotent form submits (a double click doesn't create 2 bills: `client_ref` unique)
- [ ] **1** `EC-B08` Daily reconciliation report: payments vs bills vs day close; mismatches flagged

## C. Privacy and compliance (India)
- [ ] **P** `EC-C01` Consent recorded before testing and before referral-lab sharing; consent text versioned
- [ ] **P** `EC-C02` Data sent to external labs is the minimum needed (no phone/address unless the lab requires it, setting per lab)
- [ ] **P** `EC-C03` No patient data in logs, error messages, URLs or analytics *(CI: log-scrubbing test)*
- [ ] **P** `EC-C04` PC-PNDT: no fetal-sex fields or output anywhere
- [ ] **P** `EC-C05` Retention: reports and audit kept ≥ 2 years (NABL); nothing hard-deleted
- [ ] **1** `EC-C06` DPDP: privacy notice, patient data-access export, correction workflow, erasure request handling (anonymise beyond the retention period), breach register and 72-hour notification runbook
- [ ] **1** `EC-C07` Data-processing agreement template for external labs and any cloud provider; list of sub-processors (Google Drive, Cloudflare, WhatsApp provider)
- [ ] **1** `EC-C08` `docs/compliance/COMPLIANCE_CHECKLIST.md` reviewed by a CA (GST) and a lawyer (DPDP, IT Act signatures)
- [ ] **L** `EC-C09` NABL audit pack export (audit trail, signatory list, critical-value log, QC records)

## D. Reliability, backup and disaster recovery
- [ ] **P** `EC-D01` Backups every 15 min in lab hours + nightly (configurable 15m–24h, §17.3) to Google Drive (encrypted) + USB; healthcheck alert on a missed run
- [ ] **P** `EC-D02` **Monthly restore drill**, automated, result logged; a failed drill alerts the owner
- [ ] **P** `EC-D03` Written targets: **RPO ≤ 15 min** (data loss at worst, §17.3), **RTO ≤ 2 h** (time back in business on a spare laptop); restore runbook tested once before the pilot
- [ ] **P** `EC-D04` Containers `restart: unless-stopped`; app health endpoint (`/healthz` checks the database); Docker health checks
- [ ] **P** `EC-D05` Postgres: `fsync` on, checksums on, disk-space alert at 80%
- [ ] **P** `EC-D06` UPS for laptop power path, router and switch; laptop auto-starts after power returns
- [ ] **P** `EC-D07` Main lab works with the WAN unplugged (LAN-only test before the pilot)
- [ ] **1** `EC-D08` Point-in-time recovery (WAL archiving with pgBackRest or WAL-G) if the owner wants RPO in minutes
- [ ] **L** `EC-D09` Warm standby (second laptop/mini PC with streaming replication)

## E. Observability and support
- [ ] **P** `EC-E01` Structured JSON logs (structlog) with a request ID; IDs only, never names/phones; log rotation
- [ ] **P** `EC-E02` Uptime monitor (Uptime Kuma or Healthchecks.io) for the web app, backup job and Tunnel; alerts to the owner by email/Telegram
- [ ] **P** `EC-E03` Friendly error page with an error reference number, matching a log entry, so staff can report it
- [ ] **P** `EC-E04` `Admin ▸ System` page: version, last backup, disk space, database size, pending migrations, certificate expiry
- [ ] **1** `EC-E05` Error tracking (GlitchTip, self-hosted, PII scrubbing on)
- [ ] **1** `EC-E06` Support bundle: one button exports logs (scrubbed) + versions + settings (no patient data) for troubleshooting

## F. Performance and capacity
- [ ] **P** `EC-F01` Budgets on the 4 GB laptop: page load < 1 s on LAN, search < 300 ms, report PDF < 3 s, memory < 2 GB with 3 users
- [ ] **P** `EC-F02` Indexes for every list/search screen (patient phone/name trigram, visit date, order status); `EXPLAIN` checked in a test for the 5 main queries
- [ ] **P** `EC-F03` Pagination everywhere; no unbounded lists
- [ ] **1** `EC-F04` Load test (Locust) with 10 concurrent users and 5 years of synthetic data (about 160k visits)

## G. Upgrades, migrations, versioning
- [ ] **P** `EC-G01` SemVer 0.x, `CHANGELOG.md` with dated entries; version shown in the footer and System page
- [ ] **P** `EC-G02` Alembic migrations: forward-only in production, each tested on a copy of the previous release's schema *(CI: upgrade from last tag)*
- [ ] **P** `EC-G03` Upgrade script: takes a backup → pulls the pinned image → runs migrations → health check → **automatic rollback** to the previous image + restore if the health check fails
- [ ] **P** `EC-G04` Docker images pinned by version (no `latest`)
- [ ] **1** `EC-G05` Documented upgrade path across 2+ versions; deprecation policy (§18.3): a removed setting, screen or export column keeps working for at least one minor release, shows a notice on `Admin ▸ System` naming the release it goes away in, and is listed under "Deprecated" in the changelog
- [ ] **1** `EC-G06` Zero-touch security updates for the OS (unattended-upgrades) with reboot window outside lab hours

## H. Code quality and testing
- [ ] **P** `EC-H01` Every change ships a test; coverage report in CI (target ≥ 80% on `service.py` modules) *(CI)*
- [ ] **P** `EC-H02` ruff (lint + format), pyright strict on `service` and `billing`, pytest against real Postgres (testcontainers) *(CI)*
- [ ] **P** `EC-H03` One Playwright end-to-end test of the full day; PDF snapshot tests for report and bill *(CI)*
- [ ] **P** `EC-H04` Single local gate script = same as CI (`scripts/ci_local.sh`)
- [ ] **P** `EC-H05` Branch protection on `main`: CI must pass, PR required
- [ ] **1** `EC-H06` Mutation testing on the money module (mutmut), occasional
- [ ] **1** `EC-H07` Accessibility checks (axe via Playwright) on the main screens *(CI)*

## I. Supply chain
- [ ] **P** `EC-I01` `uv.lock` committed; lock drift fails CI *(CI)*
- [ ] **P** `EC-I02` pip-audit + osv-scanner + gitleaks in CI; Dependabot/Renovate weekly *(CI)*
- [ ] **P** `EC-I03` Licence check: allowlist MIT, BSD-2/3, 0BSD, Apache-2.0, PSF, ISC, MIT-CMU (Pillow), PostgreSQL; MPL-2.0 test-only (hypothesis); **LGPL-3.0 only for psycopg**, imported unmodified (ADR-0002 note); GPL tools (poppler) only as separate commands *(CI: pip-licenses allowlist)*
- [ ] **1** `EC-I04` SBOM (CycloneDX) attached to every release; images built in GitHub Actions and signed (cosign); provenance attestation
- [ ] **1** `EC-I05` Container image vulnerability scan with osv-scanner (or grype), pinned by SHA *(CI)*. Not Trivy: its Actions and v0.69.4 binary were compromised in March 2026 (§19.2)
- [ ] **P** `EC-I06` Every GitHub Action pinned to a full commit SHA, every image to a digest, every vendored asset to a recorded SHA-256; Renovate updates the pins *(CI: check refuses a tag-only `uses:`)*
- [ ] **P** `EC-I07` Every dependency (Python, image, vendored asset, CLI tool) has a row in `docs/DEPENDENCIES.md`; the register is reviewed each quarter and before each release *(CI: `audit_deps.py --check`)*

## J. Usability and accessibility
- [ ] **P** `EC-J01` Keyboard-first front desk (barcode scanner + Enter flows, shortcuts for new patient / bill / print)
- [ ] **P** `EC-J02` Works in Chrome/Edge on a 1366×768 screen (common on branch PCs)
- [ ] **P** `EC-J03` Clear empty, loading and error states (Basecoat components); confirmation for cancel/refund/release
- [ ] **1** `EC-J04` WCAG 2.2 AA on main screens (contrast, focus, labels)
- [ ] **1** `EC-J05` UI translations (Babel) with at least one regional language

## K. Configuration and customisation safety
- [ ] **P** `EC-K01` Settings typed and validated (Pydantic); invalid values refused with a message
- [ ] **P** `EC-K02` Settings changes, price changes and template publishes are audited and versioned (who, when, before/after)
- [ ] **P** `EC-K03` Draft → preview → publish for templates and letterheads; old documents keep their version
- [ ] **1** `EC-K04` Settings export/import (JSON) for moving to a new server or copying a branch setup
- [ ] **1** `EC-K05` Plugin API documented and versioned; a broken plugin is disabled with a warning, not a crash

## L. Documentation and training
- [ ] **P** `EC-L01` Install guide for the old laptop (OS → Docker → Labra → backup setup), tested by someone other than the author
- [ ] **P** `EC-L02` User manual (§13a) covering every minimal-version screen, screenshots generated from synthetic data; screen-registry and staleness gates green *(CI)*
- [ ] **P** `EC-L03` Runbooks: restore from backup, laptop dead, internet down at a branch, forgotten admin password, certificate/Tunnel renewal, disk full
- [ ] **1** `EC-L04` Docs site (Zensical, §19.3), architecture + ADRs, API reference, contributor guide
- [ ] **1** `EC-L05` Training checklist for new staff; one-page quick-reference cards per role

## M. Release checklist (every release)
- [ ] CI green; changelog dated; version bumped
- [ ] User manual updated, screenshots regenerated, What's new written, manual PDF rebuilt
- [ ] Migration upgrade test from the previous tag passed
- [ ] Backup → upgrade → rollback rehearsed on a test laptop
- [ ] Security scan results reviewed (no unaddressed high/critical)
- [ ] Release notes say what operators must do (if anything)
- [ ] Tagged; images pinned; SBOM attached (from gate 1)

## Open-source project health (gate 1)
- [ ] `EC-O01` README with screenshots and a 10-minute demo (Docker + synthetic seed data)
- [ ] `EC-O02` CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT, issue/PR templates, GOVERNANCE (who decides)
- [ ] `EC-O03` ATTRIBUTIONS (Basecoat, vtracer, WeasyPrint, pyHanko, ...) and licence headers
- [ ] `EC-O04` Public roadmap (GitHub Projects) and a "good first issue" label
- [ ] `EC-O05` Bus factor (§18.3): repo moved to a GitHub organization (owner's go-ahead first), `MAINTAINERS.md`, `docs/dev/releasing.md` complete enough that someone else can cut a release
- [ ] `EC-O06` GitHub private vulnerability reporting on; OpenSSF Scorecard action in CI (owner's go-ahead for the GitHub setting)
- [ ] `EC-O07` Issue forms (YAML) with version, install type and a required "contains no patient data" tick; GitHub Discussions for questions, issues for bugs only
- [ ] `EC-O08` Public demo on synthetic seed data, reset nightly, on its own small server (never the standby)
