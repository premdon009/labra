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
- `labra seed` loads a synthetic demo lab.
- User manual site with the first pages, kept in step with the screens by a gate.
- Docker Compose stack (web, Postgres, Caddy, optional Cloudflare tunnel), amd64 and arm64 images, and the release pipeline.
