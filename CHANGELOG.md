# Changelog

All notable changes to Labra are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/) (0.x while the pilot runs). Every released version heading carries its date: `## [x.y.z] - YYYY-MM-DD`.

## [Unreleased]

### Added
- Repository scaffold: community files, agent instructions, tracker and enterprise checklist.
- Local gate `scripts/ci_local.sh` with the same stages CI runs, plus pre-commit hooks.
- Dependency register and supply-chain pinning for actions, images and vendored assets.
- Platform ports: identity, files, errors, heartbeats and mail behind small interfaces with built-in defaults.
- `/healthz`, `/readyz` and `/metrics` endpoints.
- Lab settings with branch overrides, gap-free document numbering that resets each financial year, stored files checked by SHA-256, and an event outbox.
- Append-only audit log with a hash chain, and `labra audit verify` to check it.
- Branches, sign-in with lockout and session expiry, roles with permission switches, branch scoping, and staff records without a login.
- `labra seed` loads a synthetic demo lab, with a priced catalog, referrers and patients.
- User manual site with the first pages, kept in step with the screens by a gate.
- Docker Compose stack (web, Postgres, Caddy, optional Cloudflare tunnel), amd64 and arm64 images, and the release pipeline.
- Front desk: find and register patients with a duplicate warning, and keep a referrer list.
- One-screen visit: order tests by code, discount with a reason, take a part payment, and record consent to a versioned notice.
- Bills of supply with the Rule 49 fields, receipts, a dues list, later payments, and bill cancellation with a reason and a full refund.
- Barcode sample labels, one per container, and a scan screen that marks samples as collected.
- Keyboard shortcuts for the front desk, paging on every list, and currency display settings.
- A browser test of a front-desk day; the gate reports it as unchecked when no browser is installed.
- External labs with their rates and turnaround times, and routing of each test in-house, to a branch or to an outside lab, with the cost and the margin shown.
- A receive scan at the lab for samples from another branch.
- Lab worklist and result grid: values saved as they are typed, flags by sign and colour, calculated rows, the previous value, and a guard against absurd values.
- Critical-value log that holds a test back until someone is on record as informed.
- Submit for verification, verification by the signatory only, and reopening with a reason that keeps the old values.
- Outsourcing screen: send-out sheet, mark sent with the outside lab's number, result PDF upload and download, and a timeline for each test.
- `test.sent_out` and `test.performed` events in the outbox.
- A service swap register in the developer docs: every replaceable part with the setting that selects it and the test that proves the swap, kept complete by a gate.
- Report and bill PDFs made on the server with vendored Noto fonts (₹ and Devanagari), no network fetches, and a sanitiser for uploaded SVGs.
- Letterheads per branch for reports and bills: upload (SVG, PDF or image, optimised), margins and signature area, a live preview, a calibration page, a printer offset, and draft then publish with old documents keeping their version.
- The bill of supply as a PDF on the bill letterhead, digital and print.
- Report layout with the ISO 15189 items on every page, panels that do not split, "(continued)" headings, A4 and A5, and an optional reference column.
- Report release by the signatory with a confirm screen, partial reports with a pending list, versions that supersede, and a block while a range is unapproved.
- A QR code on each report and a public page that shows only whether a report version is current.
- Reopening a released test and an amended version with a banner; outside PDFs attached to the report or forwarded with a cover page.
- Report copies to download or print, selected tests only, a hand-over log, and a tick before printing or handing over with money due.
- Patient history with results side by side, address and visit-date filters, and a scanned visit number that opens the visit.
- Owner figures: daily collection by branch and mode, bills, cancellations, dues, outsourcing margin, and pending and overdue tests.
- `labra export accounting` and `labra export all` (CSV and Parquet with a schema description), for administrators only and audited.
- `report.released` events in the outbox.
- The branch and settings screens warn when bills would print no place of supply, and the main lab's GST state code must be two digits or empty.
- Tests for the security headers and a scan of the templates for inline code; a browser test of releasing, printing and handing over; snapshot tests for the report and bill PDFs.
- Backups to Google Drive and a USB disk with restic, every 15 minutes in lab hours and nightly, run by host timers in a one-shot backup container, with a run log and an alert on a missed or failed run.
- `scripts/restore.sh` to restore a backup on the same or a new server, and a monthly restore drill that checks the tables and the audit log.
- Nightly audit log check, an hourly disk check that alerts at 80% used, and a watchdog that alerts when Labra can't be reached.
- **Admin ▸ System** page: version, last backup, drill and checks, disk space, database size, pending migrations and certificate expiry.
- `scripts/upgrade.sh` takes a backup, upgrades, and rolls back to the old image and data when the new version doesn't come up.
- The user manual inside the app: **Alt+H** or the Help link opens the screen's page, and the whole manual downloads as a PDF.
- Laptop budgets checked against a capped stack with 50,000 synthetic patients.
- Install guide for the main lab's laptop, runbooks (restore, laptop dead, branch internet down, forgotten administrator password, certificate and tunnel, disk full), troubleshooting pages and "A day at the lab".
- `labra set-password` gives someone a new password at the server.
- The runbooks are in the app's manual and its PDF, so they open with the internet down.
- Anyone signed in can change their own password from the **Password** link in the header; their other sessions end.
- `scripts/ci_portability.sh` runs the portability workflow's rows on a developer's machine before a push, each in its own lab container, and prints which passed; the workflow and the local runner share the same steps.

### Changed
- The app and backup image builds use a Dockerfile frontend pinned by version and digest, so a build no longer fetches whatever `docker/dockerfile:1` points to that day.
- Every container in the Compose stack keeps at most five 10 MB log files, so the install guide no longer changes Docker's own settings.
- Package and comment preset forms take tests by typed code instead of listing every test.
- Admin lists show the first page for a page number that isn't a number, and stay on the same page after a row is saved.
- Admin price headings use the currency symbol from settings.
- A bill can't be cancelled once one of its tests is sent out or has a result.
- A UPI reference that is already on another receipt is refused until the desk confirms that one payment covers both bills.
- `labra check-config` and startup refuse a database URL that isn't PostgreSQL.
- The local gate keeps the logs of its recent runs and a JUnit test report, and CI uploads them when it fails. A failed test is re-run once; one that then passes fails the gate as flaky, and `scripts/flaky_report.py` counts flaky and failed tests across runs.
- CI installs the PDF libraries the image has and runs the tests on Ubuntu 26.04, the OS the PDF snapshots were made on.
- Uploaded SVGs are parsed with Python's own XML parser, which refuses DTDs and entities; `defusedxml` is no longer a dependency.
- SQLAlchemy and pypdf deprecation warnings fail the tests, and so does a cursor, file or response left open.
- The gate and pre-commit lint the shell scripts with shellcheck.
- The demo seed draws every person's name from Faker and the letterhead preview samples show role labels, so no person's name is written in the code.
- Dependencies must be at least 7 days old before Labra adopts them, except fixes for published advisories; `uv lock` picks only such releases and `scripts/audit_deps.py --check` refuses younger ones.
- Pillow 13.0.0 and certifi 2026.10.19, for published advisories.
- Brotli 1.2.1 (used for the fonts in every PDF) and pypdf 6.21.2, for published advisories.
- The stack smoke test checks that Postgres runs with fsync and data checksums on.
- CI and release image builds use the Node 24 releases of Docker's GitHub Actions (setup-qemu, setup-buildx, login, build-push), and every job names its runner, `ubuntu-26.04`, instead of `ubuntu-latest`.
- The gate runs the tests in parallel, one worker per CPU (at most 8), each with its own database; the time-budget tests run after them on their own.
- A new push to a pull request cancels its older CI and portability runs; runs on master and on the schedule always finish.
- GitHub CI installs pinned gitleaks, osv-scanner, git-cliff and shellcheck and runs the gate with `--strict`, so the secret and vulnerability scans now run there and any stage that couldn't be checked fails the run.
- A release runs the stack smoke test (restore, upgrade, rollback) on the tagged commit before it pushes any image.
- The portability workflow also runs when `scripts/backup.sh` changes, and a test fails when a script its rows reach is missing from the paths it watches.
- An upgrade that fails says which step failed, the migrations or the new version not starting in time, in its message and in the System page's *Upgrade* row.

### Fixed
- Visit screen: a test code typed while the last test is still being added is no longer lost.
- A UPI reference must contain a digit, so a word typed by mistake is refused.
- The audit log records a new visit before its bill.
- Changing a branch code is refused when one of the branch's numbers would no longer fit in 16 characters.
- Upgrade step `0005` gives branches made by older versions the number series they lack (samples, refunds).
- A form that carries a row version that isn't a number is refused as out of date instead of failing.
- Previous and Next work on the departments and specimens screen after a refused save.
- The demo signatory's degree is printed once, as a qualification, not in the name as well.
- The System page counts the HTTPS certificate as renewing itself only when Caddy issued it, so a short certificate made by hand now warns before it runs out.
- A restore on a new server puts the stored files back: the backup image owns the folder they go into. The row counts are checked inside the restore's transaction, so a short backup leaves the database as it was, and stored files that fail after the database loaded are reported as an incomplete restore with Labra left stopped.
- On Podman 5 (`podman compose`), the web app is healthy again: its health check is now `python -m labra.probe /readyz`, as Podman 5 split the old one at its spaces. `upgrade.sh` reads the running image from one web container when nerdctl lists two.
- With podman-compose, a backup, drill or restore no longer waits forever after a restore or upgrade: the containers those started kept the job lock open.
- With nerdctl compose, the backup, restore, drill, upgrade and watchdog scripts run their jobs: nerdctl's `compose run` takes no `-T`, and without a terminal it reported every job as a success. The scripts now run jobs through `scripts/compose_run.sh`, which on nerdctl reads the job's own exit status. An upgrade's backup and rollback start the database again after stopping the web app, as nerdctl's `compose stop web` stops the database too. The upgrade's migrations run with `--no-deps`, as nerdctl's `compose run` would start a second database.
- With podman-compose, `upgrade.sh` finds the web container by its Compose label, as podman-compose's `ps` takes no service name. An upgrade whose migration fails is rolled back there too: the migrations run as a job first, and a stack that never gets healthy is given up after `LABRA_UPGRADE_WAIT` seconds instead of waited for.
- With nginx, a restore or an upgrade that recreates the web app no longer leaves the proxy answering 502: nginx looks the app up again every 10 seconds.
- The drill reads each result from the job's output, not from a warning Podman or Compose prints after it.
- Rootless nerdctl starts on Ubuntu runners again (an AppArmor profile for RootlessKit). A stack smoke test that fails now prints each container's health checks, and a drill, restore or upgrade that hangs is stopped after 10 minutes with what was still running.
