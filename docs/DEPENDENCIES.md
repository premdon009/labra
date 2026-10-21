# Dependency register

Every dependency Labra installs, ships or relies on has one row here, and nothing is added
without one (AGENTS.md rule 6). The process and the status rules are in
[design §19](design/v1-plan.md#19-dependency-pre-audit-and-register-owner-request-2026-10-08).

- `scripts/audit_deps.py --check` (in `scripts/ci_local.sh` and pre-commit) fails when a
  dependency has no row, a row has nothing behind it, a licence is outside the allowlist, an
  Action isn't pinned by commit SHA, an image has no digest, a vendored file doesn't match
  its recorded SHA-256, or a pinned version breaks the minimum release age below. It needs no
  network.
- `scripts/audit_deps.py --refresh` rewrites the **Pinned**, **Latest · date** and
  **Rel. 12m** columns from `uv.lock` and PyPI, and prints status changes for a person to
  confirm. A weekly workflow runs it. Without network it reports WARN, never a pass.

**Licence allowlist:** MIT, MIT-CMU, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, 0BSD,
PostgreSQL, PSF-2.0. Exceptions: LGPL-3.0 for psycopg only (imported unmodified, ADR-0002);
MPL-2.0 for tools that are never shipped; GPL programs only as separate commands, never
imported; OFL-1.1 for vendored font files only (never code, kind `font`); MPL-1.1 for pyphen
only (under WeasyPrint, imported unmodified).

**Minimum release age: 7 days.** No version is pinned until it has been public for 7 days, so a
broken or malicious release is usually found and pulled before Labra takes it. The only exception
is a fix for a published advisory, recorded under [Age exceptions](#age-exceptions).
- Python: `pyproject.toml` sets `[tool.uv] exclude-newer = "7 days"`, so `uv lock`, `uv add` and
  `uv lock --upgrade-package <name>` only pick releases old enough. `--check` reads each
  package's upload time from `uv.lock`.
- Actions, images, binaries and vendored files: the **Pinned** cell holds the version and its
  release date, `<version> · <YYYY-MM-DD>`. That's the commit date of an Action's SHA, the created
  date of an image's digest, the GitHub release date of a binary, and the npm publish date of a
  vendored file. A binary's row matches the `ARG <NAME>_VERSION` in the Dockerfile that
  downloads it, beside an `ARG <NAME>_SHA256_<ARCH>` for amd64 and arm64. Update the date whenever the
  SHA, digest or version changes. An Action's `# vX.Y.Z` comment must match its row.
- CLI tools and services aren't pinned by the repository. Install a release at least 7 days old.

**Status:** Active (release in the last 6 months) · Stable (no release for 6–24 months but
done) · Watch (no release for over 24 months, or a risk to its future such as a young single
maintainer, a pre-1.0 API or an archived upstream; looked at again before each release, and
replaced only through Replace) · Replace. A Replace row needs an ADR and a tracker row before
the next release.

| Component | Kind | Gate | Licence | Pinned | Latest · date | Rel. 12m | Status | Backing | Why we use it | Alternative · exit cost | Reviewed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `fastapi` | runtime | P | MIT | 0.142.2 | 0.156.4 · 2026-10-20 | 111 | Active | company | typed routes and dependency injection; 0.x, so the minor is pinned | Litestar · high | 2026-10-09 |
| `starlette` | runtime | P | BSD-3-Clause | 1.7.0 | 1.9.0 · 2026-10-18 | 24 | Active | team | under FastAPI | — | 2026-10-09 |
| `uvicorn` | runtime | P | BSD-3-Clause | 0.54.0 | 0.54.0 · 2026-09-25 | 22 | Active | team | ASGI server | Granian · low | 2026-10-09 |
| `pydantic` | runtime | P | MIT | 2.13.5 | 2.14.1 · 2026-10-11 | 18 | Active | company | validation, under FastAPI | — | 2026-10-09 |
| `pydantic-settings` | runtime | P | MIT | 2.15.0 | 2.16.1 · 2026-10-20 | 9 | Active | company | typed settings from the environment and secret files | own env parsing · low | 2026-10-09 |
| `sqlalchemy` | runtime | P | MIT | 2.1.3 | 2.1.5 · 2026-10-16 | 22 | Active | team | ORM and Core | — | 2026-10-09 |
| `alembic` | runtime | P | MIT | 1.20.0 | 1.20.0 · 2026-09-11 | 12 | Active | team | database migrations | — | 2026-10-09 |
| `psycopg` | runtime | P | LGPL-3.0-only | 3.3.6 | 3.3.6 · 2026-09-18 | 9 | Active | team | the reference Postgres driver; licence exception (ADR-0002) | pg8000 (BSD) · low | 2026-10-09 |
| `psycopg-binary` | runtime | P | LGPL-3.0-only | 3.3.6 | 3.3.6 · 2026-09-18 | 9 | Active | team | prebuilt psycopg with libpq | build psycopg from source · low | 2026-10-09 |
| `jinja2` | runtime | P | BSD-3-Clause | 3.1.6 | 3.1.6 · 2025-03-05 | 0 | Watch | team | page templates and the sandbox (EC-A08); no release for 19 months | none at the same fit; plain features only · very high | 2026-10-09 |
| `python-multipart` | runtime | P | Apache-2.0 | 0.0.32 | 0.0.32 · 2026-06-04 | 12 | Active | team | form parsing | — | 2026-10-09 |
| `argon2-cffi` | runtime | P | MIT | 25.1.0 | 25.1.0 · 2025-06-03 | 0 | Stable | single maintainer (long-standing) | password hashing with rehash on login (EC-A01) | hashlib.scrypt · low | 2026-10-09 |
| `structlog` | runtime | P | MIT OR Apache-2.0 | 26.1.0 | 26.1.0 · 2026-06-06 | 2 | Active | single maintainer (long-standing) | JSON logs with request ID (EC-E01) | stdlib logging + JSON formatter · low | 2026-10-09 |
| `prometheus-client` | runtime | P | Apache-2.0 AND BSD-2-Clause | 0.26.0 | 0.26.0 · 2026-07-24 | 4 | Active | foundation | `/metrics` in the format every monitor reads | OpenTelemetry SDK · low | 2026-10-09 |
| `babel` | runtime | P | BSD-3-Clause | 2.18.0 | 2.18.0 · 2026-02-01 | 1 | Stable | team | money formatting with Indian digit grouping; later UI translations | own grouping code (~40 lines) · low | 2026-10-12 |
| `python-barcode` | runtime | P | MIT | 0.16.1 | 0.16.1 · 2025-08-27 | 0 | Stable | single maintainer (long-standing) | Code 128 patterns for sample labels; drawn as SVG by our template, no Pillow | own Code 128 encoder (~150 lines) · low | 2026-10-12 |
| `weasyprint` | runtime | P | BSD-3-Clause | 70.0 | 70.0 · 2026-09-08 | 5 | Active | team | report and bill PDFs from HTML and CSS: paged media, running headers, page counters; no browser; system Pango and HarfBuzz in the image; fetches nothing from the network (own URL fetcher) | Chromium print through Playwright · medium | 2026-10-14 |
| `pyphen` | runtime | P | MPL-1.1 | 0.18.1 | 0.18.1 · 2026-08-14 | 2 | Active | single maintainer (long-standing) | hyphenation, required by WeasyPrint; tri-licensed GPL-2.0+ OR LGPL-2.1+ OR MPL-1.1, used under MPL-1.1, imported unmodified (licence exception); its 50 bundled dictionaries carry mixed licences, some GPL-only, and Labra never hyphenates | none while WeasyPrint needs it; leaves only with WeasyPrint (ADR-0012) · medium | 2026-10-14 |
| `pypdf` | runtime | P | BSD-3-Clause | 6.19.0 | 6.21.1 · 2026-10-17 | 46 | Active | team | stamps a vector PDF letterhead under each page, appends outside lab PDFs with their JavaScript and actions removed, de-duplicates objects | pikepdf (MPL-2.0) · low | 2026-10-14 |
| `pypdfium2` | runtime | P | Apache-2.0 OR BSD-3-Clause | 5.14.0 | 5.14.0 · 2026-10-04 | 18 | Active | single maintainer | PNG preview of a PDF page in the letterhead editor | the `pdftoppm` command · low | 2026-10-14 |
| `markdown` | runtime | P | BSD-3-Clause | 3.11 | 3.11.2 · 2026-10-19 | 7 | Active | team | the manual inside the app and its PDF, made from the same Markdown files as the website, with the built-in extensions only | mistune (BSD-3-Clause), or HTML built into the image from the site · medium | 2026-10-16 |
| `pillow` | runtime | P | MIT-CMU | 13.0.0 | 13.0.0 · 2026-10-16 | 5 | Active | team | re-encodes letterhead and signature images: resize, strip metadata, JPEG or palette PNG | the `vips` command · low | 2026-10-14 |
| `segno` | runtime | P | BSD-3-Clause | 1.6.6 | 1.6.6 · 2025-03-12 | 0 | Stable | single maintainer (long-standing) | QR code on reports, drawn as inline SVG | own QR encoder · medium | 2026-10-14 |
| `duckdb` | runtime | P | MIT | 1.5.6 | 1.5.6 · 2026-09-28 | 95 | Active | foundation | writes the Parquet files of the full data export; no extensions are loaded, so it never downloads anything | pyarrow · low | 2026-10-14 |
| `faker` | seed | P | MIT | 40.41.0 | 40.43.0 · 2026-10-09 | 64 | Active | team | synthetic demo data (`labra seed`) | hand-written lists · low | 2026-10-09 |
| `httpx2` | dev | P | BSD-3-Clause | 2.13.1 | 2.15.1 · 2026-10-19 | 21 | Active | team | HTTP client under Starlette's TestClient | — | 2026-10-09 |
| `pytest` | dev | P | MIT | 9.1.1 | 9.1.1 · 2026-06-19 | 6 | Active | team | tests | — | 2026-10-09 |
| `pytest-cov` | dev | P | MIT | 7.1.0 | 7.1.0 · 2026-03-21 | 1 | Stable | team | coverage (EC-H01) | coverage run · low | 2026-10-09 |
| `pytest-rerunfailures` | dev | P | MPL-2.0 | 16.7 | 16.7 · 2026-09-17 | 7 | Active | team | re-runs a failed test once in the gate, to tell flaky from broken (W08) | gate re-run logic · low | 2026-10-14 |
| `testcontainers` | dev | P | Apache-2.0 | 4.15.0 | 4.15.0 · 2026-07-24 | 9 | Active | company | real Postgres in tests | a Compose test service · low | 2026-10-09 |
| `ruff` | dev | P | MIT | 0.16.10 | 0.17.1 · 2026-10-15 | 49 | Active | company | lint and format | — | 2026-10-09 |
| `pyright` | dev | P | MIT | 1.1.414 | 1.1.414 · 2026-09-10 | 8 | Active | company | type checks; ty is pre-1.0, re-check at gate 1 | ty · low | 2026-10-09 |
| `import-linter` | dev | P | BSD-2-Clause | 2.15 | 2.15 · 2026-09-04 | 10 | Active | single maintainer | keeps domain code off adapters (ADR-0008) | a small AST check · low | 2026-10-09 |
| `pip-audit` | dev | P | Apache-2.0 | 2.10.1 | 2.10.1 · 2026-06-10 | 2 | Active | foundation | known-vulnerability scan of Python packages | osv-scanner alone · low | 2026-10-09 |
| `pre-commit` | dev | P | MIT | 4.6.2 | 4.7.0 · 2026-10-12 | 7 | Active | team | runs the gates before each commit | git hooks by hand · low | 2026-10-09 |
| `zensical` | dev | P | MIT | 0.0.68 | 0.0.71 · 2026-10-16 | 68 | Watch | company | docs and manual site (pre-1.0) | MkDocs 1.6.1 + Material 9.7 frozen · low | 2026-10-09 |
| `hypothesis` | dev | P | MPL-2.0 | 6.168.5 | 6.170.5 · 2026-10-20 | 138 | Active | team | property tests for the money module (EC-B01); test-only, never shipped | table tests only · low | 2026-10-12 |
| `playwright` | dev | P | Apache-2.0 | 1.63.0 | 1.64.0 · 2026-10-13 | 9 | Active | company | the front-desk browser test (keys, 1366×768); browsers installed separately | Selenium · medium | 2026-10-12 |
| `pdfplumber` | dev | P | MIT | 0.11.10 | 0.11.10 · 2026-06-15 | 3 | Active | single maintainer | tests read words and their positions from rendered PDFs (§7.2 content box, PDF snapshots) | pdfminer.six directly · low | 2026-10-14 |
| `hatchling` | build | P | MIT | — | — | — | Active | team | builds the wheel | setuptools · low | 2026-10-09 |
| `htmx.org` | vendored | P | 0BSD | 4.0.0 · 2026-08-28 | 4.0.0 · 2026-08-28 | — | Active | single maintainer (long-standing) | server-driven pages without a JS build | plain fetch · medium | 2026-10-09 |
| `@alpinejs/csp` | vendored | P | MIT | 3.17.4 · 2026-09-21 | 3.17.4 · 2026-09-21 | — | Active | team | small UI state; the CSP build needs no `unsafe-eval` | plain JS · low | 2026-10-09 |
| `basecoat-css` | vendored | P | MIT | 1.0.2 · 2026-07-06 | 1.0.2 | 3 | Watch | single maintainer, young | consistent components without a JS framework; vendored, so a stop can't break the app | own CSS · medium | 2026-10-09 |
| `noto-sans` | font | P | OFL-1.1 | 2.015 · 2024-11-20 | 2.015 · 2024-11-20 | — | Stable | company | report and bill text, ₹ included; the same output on every machine (`static/vendor/`, licence text beside it) | DejaVu Sans · low | 2026-10-14 |
| `noto-sans-devanagari` | font | P | OFL-1.1 | 2.007 · 2026-09-09 | 2.007 · 2026-09-09 | — | Active | company | patient names in Hindi or Marathi on reports and bills | Lohit Devanagari · low | 2026-10-14 |
| `postgres` | image | P | PostgreSQL | 18 · 2026-10-06 | 18 | — | Active | foundation | the database; 18 for support until Nov 2030. Also the backup image's base, so `pg_dump` matches the server (ADR-0013) | — | 2026-10-16 |
| `caddy` | image | P | Apache-2.0 | 2 · 2026-10-05 | 2 | — | Active | company | HTTPS, security headers, reverse proxy | nginx, tested · low | 2026-10-09 |
| `cloudflare/cloudflared` | image | P | Apache-2.0 | 2026.10.0 · 2026-10-05 | 2026.10.0 · 2026-10-05 | — | Active | company | reach the lab from branches without opening ports; service lock-in | Tailscale, NetBird or WireGuard · medium | 2026-10-09 |
| `nginx` | image | P | BSD-2-Clause | 1.30 · 2026-10-06 | 1.30 | — | Active | company | proxy alternative to Caddy (`deploy/nginx/`, ADR-0009) | Caddy · low | 2026-10-09 |
| `tailscale/tailscale` | image | P | BSD-3-Clause | v1.102.5 · 2026-09-21 | v1.102.5 | — | Active | company | branch access over a tailnet, or self-hosted Headscale (`tailscale` profile) | NetBird or WireGuard · low | 2026-10-09 |
| `netbirdio/netbird` | image | P | BSD-3-Clause | 0.80.0 · 2026-10-01 | 0.80.0 | — | Active | company | branch access over NetBird (`netbird` profile); its control plane is AGPL-3.0 and self-hostable | Tailscale or WireGuard · low | 2026-10-09 |
| `python` | image | P | PSF-2.0 | 3.14-slim · 2026-10-06 | 3.14 | — | Active | foundation | base of the Labra image | — | 2026-10-09 |
| `ghcr.io/astral-sh/uv` | image | P | MIT OR Apache-2.0 | 0.12.18 · 2026-09-22 | 0.12.18 | — | Active | company | installs locked dependencies in the image build | pip · low | 2026-10-09 |
| `restic` | binary | P | BSD-2-Clause | 0.19.1 · 2026-07-05 | 0.19.1 · 2026-07-05 | 3 | Active | team | encrypted, deduplicated backup snapshots (`deploy/backup/`, ADR-0013); release binary checked by SHA-256 | Borg · medium | 2026-10-16 |
| `rclone` | binary | P | MIT | 1.75.2 · 2026-10-09 | 1.75.2 · 2026-10-09 | many | Active | team | restic's way to Google Drive (`rclone:` backend, ADR-0013); release binary checked by SHA-256 | restic's own S3, B2 or SFTP backends · low | 2026-10-16 |
| `actions/checkout` | action | P | MIT | v5.1.0 · 2026-07-16 | — | — | Active | company | CI checkout | — | 2026-10-09 |
| `actions/upload-artifact` | action | P | MIT | v7.0.1 · 2026-04-10 | — | — | Active | company | keeps the gate's logs and JUnit report when CI fails (W08) | — | 2026-10-14 |
| `astral-sh/setup-uv` | action | P | MIT | v7.6.0 · 2026-03-16 | — | — | Active | company | CI Python and uv | — | 2026-10-09 |
| `docker/setup-qemu-action` | action | P | Apache-2.0 | v3.7.0 · 2025-11-05 | — | — | Active | company | arm64 image builds (W11) | — | 2026-10-09 |
| `docker/setup-buildx-action` | action | P | Apache-2.0 | v3.12.0 · 2025-12-16 | — | — | Active | company | multi-arch image builds (W11) | — | 2026-10-09 |
| `docker/login-action` | action | P | Apache-2.0 | v3.7.0 · 2026-01-27 | — | — | Active | company | push release images to GHCR (W12) | — | 2026-10-09 |
| `docker/build-push-action` | action | P | Apache-2.0 | v6.19.2 · 2026-02-12 | — | — | Active | company | build and push release images (W12) | — | 2026-10-09 |
| `uv` | CLI | P | MIT OR Apache-2.0 | 0.12 | 0.12.18 | many | Active | company | Python, virtualenv and lock file | pip + pip-tools · low | 2026-10-09 |
| `gitleaks` | CLI | P | MIT | — | — | — | Active | company | secret scan (`scripts/check_secrets.sh`) | trufflehog · low | 2026-10-09 |
| `osv-scanner` | CLI | P | Apache-2.0 | — | — | — | Active | company | vulnerability scan of `uv.lock` and images | grype · low | 2026-10-09 |
| `git-cliff` | CLI | P | MIT OR Apache-2.0 | — | 2.14.2 · 2026-09-18 | 4 | Active | team | changelog drafts from commit subjects (W12); `uv tool install` | hand-written changelog · low | 2026-10-09 |
| `shellcheck` | CLI | P | GPL-3.0 | — | 0.11.0 | — | Active | team | lints `scripts/*.sh` (`scripts/check_shell.sh`, W25); a dev tool, never shipped | none · low | 2026-10-16 |
| `docker` | CLI | P | Apache-2.0 | — | — | — | Active | company | runs the stack and the database tests | Podman or nerdctl, tested (ADR-0009) · low | 2026-10-09 |
| `podman` | CLI | P | Apache-2.0 | 5 | 5.8.7 | — | Active | company | daemonless, rootless runtime for the stack and tests (ADR-0009); below 5 lacks DNS on internal networks | Docker · low | 2026-10-09 |
| `Podman Desktop` | CLI | P | Apache-2.0 | — | — | — | Active | company | Podman on Windows and macOS desktops | Docker Desktop · low | 2026-10-09 |
| `podman-compose` | CLI | P | GPL-2.0-only | 1.6 | 1.6.0 | — | Active | team | Compose for Podman without the docker-compose binary; a tool only, never shipped or linked | `podman compose` with docker-compose · low | 2026-10-09 |
| `buildah` | CLI | P | Apache-2.0 | — | 1.43.4 | — | Active | company | daemonless image builds (`scripts/build_image.sh`) | Docker BuildKit · low | 2026-10-09 |
| `nerdctl` | CLI | P | Apache-2.0 | 2.4.1 | 2.4.1 | — | Active | foundation | runs the stack on containerd (Tier 2); `nerdctl-full` tarball pinned by SHA-256 | Docker · low | 2026-10-09 |
| `containerd` | CLI | P | Apache-2.0 | 2.4.1 | 2.4.1 | — | Active | foundation | the container engine under Docker and nerdctl | — | 2026-10-09 |
| `incus` | CLI | P | Apache-2.0 | 6 | 6.23 | — | Active | foundation | system containers that run the stack with Podman inside (Tier 2); LXD is AGPL-3.0 since 2023 | LXD or a VM · low | 2026-10-09 |
| `kaniko` | CLI | P | Apache-2.0 | v1.28.5 · 2026-09-20 | v1.28.5 | — | Watch | team | image builds without a daemon, in CI on a cluster; the original project was archived 2025-06-03, this is the osscontainertools fork, run as an image pinned by digest | Buildah · low | 2026-10-09 |
| `GitHub` | service | P | — | — | — | — | Active | company | code, CI, issues, container registry, docs hosting | Codeberg / Forgejo · medium | 2026-10-09 |
| `Cloudflare Tunnel` | service | P | — | — | — | — | Active | company | the tunnel cloudflared connects to | Tailscale · medium | 2026-10-09 |
| `Tailscale` | service | P | BSD-3-Clause | — | — | — | Active | company | coordination for the `tailscale` profile; Headscale (BSD-3-Clause) replaces it self-hosted | Headscale or NetBird · low | 2026-10-09 |
| `NetBird` | service | P | — | — | — | — | Active | company | control plane for the `netbird` profile; self-hostable (AGPL-3.0, run as a separate service) | Tailscale or WireGuard · low | 2026-10-09 |
| `Healthchecks.io` | service | P | BSD-3-Clause | — | — | — | Active | company | heartbeat pings after backups (`LABRA_HEARTBEAT=http`); self-hostable | Uptime Kuma · low | 2026-10-09 |
| `Google Drive` | service | P | — | — | — | — | Active | company | the off-site backup copy, encrypted by restic before it leaves the lab (ADR-0013); the lab's own account | any rclone remote: S3, B2, SFTP · low | 2026-10-16 |

## Age exceptions

A version younger than 7 days is pinned only when it fixes a published advisory and can't wait.
Each one gets a row here, and a Python package also gets an entry in `pyproject.toml`
`[tool.uv] exclude-newer-package`, set to a time just after that release. `--refresh` says when
an exception is no longer needed; then drop its row and the entry.

| Component | Version | Advisory | Why it can't wait | Added |
|---|---|---|---|---|
| `pillow` | 13.0.0 | GHSA-pchr-8j38-3x4p | 12.3.0 has the advisories fixed in 13.0.0 (two critical: stale image storage, JPEG decoder overflow); Labra decodes uploaded logos and signatures with it; the breaking changes in 13.0.0 touch nothing Labra calls | 2026-10-21 |
| `certifi` | 2026.10.19 | PYSEC-2026-4320 | 2026.7.22 has a 9.1 advisory; a development dependency only (through requests, for pip-audit and testcontainers), but the audit stage fails every gate run until it is updated | 2026-10-21 |
