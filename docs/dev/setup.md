---
items: [W01, W08]
---

# Developer setup

## Tools
| Tool | Needed for | Install |
|---|---|---|
| uv | Python, dependencies, running everything | <https://docs.astral.sh/uv/> |
| Docker with Compose | tests (throwaway Postgres) and the full stack | Docker Engine, or Docker Desktop with WSL integration on |
| gitleaks | secret scan in pre-commit and the gate | package manager or GitHub release |
| osv-scanner | vulnerability scan of `uv.lock` | package manager or GitHub release |
| git-cliff | changelog drafts (releases only) | `uvx git-cliff` |

`scripts/check_tools.sh` prints what's present and which versions. Missing required tools fail the gate; missing optional ones show as warnings.

## First run
```bash
uv sync                                   # creates .venv from uv.lock
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
scripts/ci_local.sh                       # all gates
uv run labra serve                        # http://127.0.0.1:8000
```

Run one stage with `scripts/ci_local.sh --only lint` (stages: preflight, hygiene, lint, types, imports, services, tests, tracker, manual, docs, audit, stack). `--dry-run` lists the stages without running them.

## Gate run logs
Every gate run keeps its logs in `.ci/runs/<UTC time>/`, and prints the directory at the end as `Logs: …`:

| File | What it holds |
|---|---|
| `<stage>.log` | everything the stage printed |
| `summary.txt` | the stage table, and the failed and flaky tests when the tests stage failed |
| `pytest.txt` | the test output, with the failed, errored, skipped and re-run tests named at the end |
| `failed-tests.txt` | one line per failed or flaky test |
| `flaky.txt` | the flaky tests' IDs, one per line (only when there are some) |
| `junit.xml` | the test results as JUnit XML, which GitLab, Forgejo, Jenkins, Allure, IDEs and most CI systems read; a re-run test is listed twice |
| `coverage.json` | coverage per file |
| `failed` | an empty marker: some stage failed |

The gate re-runs a failed test once. A test that fails both times fails the gate as before. A test that passes on its re-run is **flaky**: it still fails the gate, labelled `flaky (passed on re-run)` and listed in `flaky.txt`. Fix it; don't re-run the gate until it goes green. A plain `uv run pytest` doesn't re-run anything.

The newest 10 runs are kept, and so is the newest failed run, however old, so an intermittent failure can be found after a green run. `.ci/` is ignored by git and by the gate's own scans.

Another CI system sets `LABRA_CI_LOGS` to a directory outside the checkout and collects it as an artifact; GitHub CI does this and uploads it when the gate fails.

## Tests and Docker
Tests that need Postgres are marked `db` and start a `postgres:18` container through testcontainers. When Docker isn't reachable they're **skipped with a reason**, and the gate reports the test stage as `WARN`, never `PASS`.

One test, marked `e2e`, drives the front desk in a real browser with the keyboard. Install its browser once with `uv run playwright install chromium`. Without it the test is skipped with the reason "no browser for e2e tests" and the test stage is `WARN`.

On Windows with WSL: turn on *Settings ▸ Resources ▸ WSL integration* in Docker Desktop for your distribution, so `docker` inside WSL talks to the Docker Desktop engine.

## Settings
Process settings come from `LABRA_*` environment variables (`src/labra/core/config.py`). Any of them can instead be read from a file by setting `LABRA_<NAME>_FILE`, which is how Docker secrets are passed. Never commit `.env` files.

Platform services (login, files, errors, metrics, mail) are chosen by settings; see [ADR-0008](../adr/0008-platform-ports.md).

## Optional: agent tooling
- **Serena** (code navigation for AI agents): `uv tool install serena-agent`, once per machine. `.mcp.json` starts it per project.
- **rtk** (compresses shell output to save tokens): if installed, its `Read` output is compressed, so read exact bytes with `rtk proxy cat <file>` before editing.
