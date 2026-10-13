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

### Changed
- Package and comment preset forms take tests by typed code instead of listing every test.
- Admin lists show the first page for a page number that isn't a number, and stay on the same page after a row is saved.
- Admin price headings use the currency symbol from settings.
- A UPI reference that is already on another receipt is refused until the desk confirms that one payment covers both bills.

### Fixed
- Visit screen: a test code typed while the last test is still being added is no longer lost.
- A UPI reference must contain a digit, so a word typed by mistake is refused.
- The audit log records a new visit before its bill.
- Changing a branch code is refused when one of the branch's numbers would no longer fit in 16 characters.
- Upgrade step `0005` gives branches made by older versions the number series they lack (samples, refunds).
- A form that carries a row version that isn't a number is refused as out of date instead of failing.
- Previous and Next work on the departments and specimens screen after a refused save.
