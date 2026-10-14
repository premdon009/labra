# Services and how to swap them

Labra relies on a database, logs, a web proxy and a handful of other services. Each one can be
replaced or reconfigured without hunting through the code. This page lists every replaceable
part, what selects it, and the test or script that proves the swap works.
`scripts/check_services.py --check` keeps the page honest (the `services` stage of
`scripts/ci_local.sh`). The thinking behind it is in [ADR-0007](../adr/0007-replaceable-edges.md),
[ADR-0008](../adr/0008-platform-ports.md) and [ADR-0009](../adr/0009-runtime-neutral-packaging.md).

## Register

| Service | Kind | Default | Alternatives | Selected by | Proof | Status |
|---|---|---|---|---|---|---|
| Database server | setting | PostgreSQL 18: the `db` service, `postgres` image | any PostgreSQL server the lab already runs, managed or not | `LABRA_DATABASE_URL` | `tests/test_tooling.py::test_check_config_refuses_other_databases`, `tests/test_db_dialect.py::test_similar_finds_spelling_variants`, `.github/workflows/portability.yml` (the database tests against an outside server, weekly) | swappable |
| Database engine | setting | PostgreSQL, with Postgres-only code behind `labra.core.dialect` | MariaDB, then others | `LABRA_DATABASE_URL` | X40 | planned |
| Database driver | setting | psycopg 3 (`postgresql+psycopg://…`) | pg8000 | `LABRA_DATABASE_URL` | X44 | planned |
| Identity (`labra.identity`) | port | `local`: passwords hashed with argon2 | any OIDC provider (X42) | `LABRA_AUTH_PROVIDER` | `tests/test_platform.py::test_default_settings_build_every_builtin`, `tests/test_platform.py::test_unknown_adapter_fails_fast_with_choices` | swappable |
| Files (`labra.filestore`) | port | `local`: content-addressed files on disk | S3-compatible storage (X41) | `LABRA_FILESTORE`, `LABRA_FILES_DIR` | `tests/test_platform.py::test_filestore_round_trip` | swappable |
| Errors (`labra.errors`) | port | `log`: a log entry and a reference number for staff | GlitchTip or Sentry (X43) | `LABRA_ERRORS` | `tests/test_platform.py::test_error_reporter_contract` | swappable |
| Heartbeats (`labra.heartbeat`) | port | `log`: a log line per job | `http`: any ping URL, one per job in LABRA_HEARTBEAT_URL_&lt;JOB&gt; | `LABRA_HEARTBEAT` | `tests/test_platform.py::test_heartbeat_contract` | swappable |
| Mail (`labra.mailer`) | port | `console`: printed, for development | `smtp`: any SMTP relay | `LABRA_MAILER`, `LABRA_SMTP_URL` | `tests/test_platform.py::test_mailer_contract`, `tests/test_platform.py::test_smtp_mailer_from_settings` | swappable |
| Logs | setting | JSON lines on stdout, for any collector that reads container output | console lines; OTLP (X35) | `LABRA_LOG_FORMAT`, `LABRA_LOG_LEVEL` | `tests/test_platform.py::test_log_format_json_or_console` | swappable |
| Metrics | endpoint | `GET /metrics` in Prometheus format, internal networks or a token only | any Prometheus-compatible scraper; off; OTLP (X35) | `LABRA_METRICS`, `LABRA_METRICS_TOKEN` | `tests/test_web.py::test_metrics_with_token`, `tests/test_web.py::test_metrics_off` | swappable |
| Health | endpoint | `GET /healthz` and `GET /readyz` | any HTTP monitor | — | `tests/test_web.py::test_healthz_needs_no_database`, `tests/test_web.py::test_readyz_503_without_database` | swappable |
| Web proxy | compose | Caddy: the `proxy` service, `caddy` image | nginx: `deploy/nginx/compose.nginx.yaml`, `nginx` image | `LABRA_SITE`, `LABRA_HTTP_PORT`, `LABRA_HTTPS_PORT` | `scripts/stack_smoke.sh` | swappable |
| Remote access | compose | Cloudflare Tunnel: `--profile tunnel`, the `tunnel` service, `cloudflared` image | Tailscale or Headscale: `--profile tailscale`, `tailscale` image; NetBird: `--profile netbird`, `netbird` image | `LABRA_TUNNEL_TOKEN`, `LABRA_TAILSCALE_AUTHKEY`, `LABRA_NETBIRD_SETUP_KEY` | `scripts/stack_smoke.sh` | swappable |
| Container runtime | script | Docker Engine with Docker Compose | Podman 5, containerd with nerdctl, Incus ([runtimes](runtimes.md)) | the command, e.g. `podman compose up -d` | `scripts/stack_smoke.sh`, `scripts/compare_runtimes.sh` | swappable |
| Image builder | script | Docker BuildKit builds the `labra` image that `web` and `migrate` run | Podman, Buildah, Kaniko (maintained fork) | `LABRA_IMAGE` | `scripts/build_image.sh`, `scripts/check_image.sh` | swappable |
| Backups | script | restic to Google Drive and a USB disk | any restic repository | — | M16 | planned |
| PDF engine | library | WeasyPrint for A4 reports | — | — | M12 | planned |
| UI assets | vendored | `htmx.org`, `@alpinejs/csp` and `basecoat-css`, served from `src/labra/static/vendor/` | another version, recorded with its SHA-256 | `src/labra/static/vendor/manifest.json` | [ADR-0003](../adr/0003-fastapi-postgres.md) | fixed |
| Barcode | library | `python-barcode` (Code 128), imported only in `labra.web.barcode` | any Code 128 generator, changed in that one module | — | `tests/test_barcode.py::test_barcode_fits_label_width_longest_branch_code` | swappable |
| Money formatting | library | `babel`, imported only in `labra.web.money_format` | any locale library, changed in that one module | — | `tests/test_currency.py::test_format_money_table` | swappable |

**Kind:** `port` is a protocol in `labra.core.ports` with adapters registered as entry points;
`setting` is chosen by a `LABRA_*` setting; `endpoint` is a standard HTTP endpoint that any
monitor can read; `compose` is a Compose service, profile or override file; `script` is a
command or script outside the app; `vendored` is a file copied into the repository; `library` is
a Python package used in one module.

**Status:** `swappable` names the tests (`file::test`) or scripts that prove the swap;
`planned` names its open tracker row; `fixed` links the ADR that decided to keep it.

**What the gate checks:**
- every port in `labra.core.ports.GROUPS` has a row naming its group, and every entry point
  registered under a `labra.*` group in `pyproject.toml` is named in that row;
- every `LABRA_*` name under "Selected by" is a setting in `labra.core.config.Settings` or a
  variable in a Compose file;
- every Compose service, profile, override file and image, and every vendored asset, is named in
  a row; Compose services are read in block style at any indentation, and services written in
  flow style (`{…}`) are refused, since the gate would not see them;
- each row's proof exists: the test function or script, an open tracker row, or the ADR;
- Postgres-only code (`sqlalchemy.dialects` imports, `func.similarity`, `pg_advisory_*`,
  `hashtextextended`, `func.array_to_string`, `func.unnest`, `distinct_on`, `.op("%")`) sits only
  in `src/labra/core/dialect.py` or `src/labra/migrations/`.

## What ties Labra to PostgreSQL

Labra supports the PostgreSQL family: any PostgreSQL 18 server, with psycopg 3 as the driver.
The `outside-postgres` job in `.github/workflows/portability.yml` runs the database tests each
week against a server Labra didn't start; run the same locally by pointing
`LABRA_TEST_DATABASE_URL` at a database whose name ends in `_test`.
Another engine is tracker row X40 and another driver is X44. This list keeps that work sized.

| Feature | Where it lives | What another engine needs |
|---|---|---|
| Trigram name search (`pg_trgm`: `similarity`, `%`) | `labra.core.dialect` (`similar`, `similarity`); GIN `gin_trgm_ops` indexes in the patient and catalog models; extension created in migration 0002 | a fuzzy match function, or `LIKE` with ranking in Python |
| Transaction-scoped advisory locks | `labra.core.dialect` (`advisory_lock`, `advisory_lock_for`) | named locks (MariaDB `GET_LOCK`) or a lock table |
| Lists in one column (`ARRAY`, `@>`, `unnest`, `array_to_string`) | `labra.core.dialect` (`StringList`, `list_contains`, `list_items`, `list_as_text`); GIN index on test aliases | a JSON array or a child table |
| JSON documents (`JSONB`) | `labra.core.dialect` (`Json`); `'{}'::jsonb` server defaults in the patient, visit and bill models | the engine's JSON type |
| One row per group in a given order (`DISTINCT ON`) | `labra.core.dialect` (`latest_per`) | a window function (`row_number() over …`) |
| Partial indexes (`postgresql_where`) | catalog, visit, bill, external lab and core models | unique constraints over generated columns, or a service check |
| `NULLS NOT DISTINCT` unique constraints | catalog and core models | a generated key column |
| Append-only and bill guards (plpgsql triggers) | migrations 0001, 0003 and 0004 | triggers in the engine's own language |
| Raw SQL in migrations | all migrations | a new migration chain for that engine (history stays as it is) |

Domain code reaches every item in the first five rows only through `labra.core.dialect`.
Models keep their `postgresql_*` index options, which other engines ignore, and migrations are
history and stay as they are.

## Adding or swapping a service

Nothing is built ahead of need ([ADR-0007](../adr/0007-replaceable-edges.md)). When a real
install needs an alternative, follow the same steps every time:

1. Add the adapter in `src/labra/adapters/` and register it as an entry point under the port's
   group in `pyproject.toml`.
2. Ship its vendor library as an optional extra (`labra[s3]`, `labra[sentry]`, …), with a row in
   [`docs/DEPENDENCIES.md`](../DEPENDENCIES.md).
3. Pass the port's contract suite in `tests/test_platform.py`, against a real service in a test
   container where one exists.
4. Name the adapter in its row here, and change the row from `planned` to `swappable` with its
   proof.
5. Add any new setting to `labra.core.config.Settings`, and document it in the install or admin
   docs.

A new kind of service, such as a new port, a Compose service or a vendored file, gets its own
row in the same change; the gate fails until it has one. New Postgres-only queries go into
`labra.core.dialect` as a named helper, with a test in `tests/test_db_dialect.py`.
