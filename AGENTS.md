# AGENTS.md

Instructions for anyone, human or AI agent, changing this repository.

## What Labra is
Open-source software (MIT) for small Indian diagnostic lab chains: patients, visits, billing, samples, in-house and outsourced tests, results, reports. One main lab plus a few collection centres, running on a small server (an old laptop or mini PC) at the main lab, reachable from the branches.

- Design: [`docs/design/v1-plan.md`](docs/design/v1-plan.md)
- What's left: [`docs/TRACKER.md`](docs/TRACKER.md)
- Release checklist: [`docs/ENTERPRISE_CHECKLIST.md`](docs/ENTERPRISE_CHECKLIST.md)

## Hard rules
1. **Synthetic data only.** No real patient, staff or lab names, numbers or results anywhere: code, tests, fixtures, screenshots, issues, commits.
2. **Never name the commercial lab product** that the feature checklist was taken from, or its vendor, and never copy its wording or screenshots. A local pre-commit hook checks for this.
3. **Secrets come from the environment only.** Never commit `.env*`, keys, passwords or tokens. Never read `.env*`, `data/` or backups while working.
4. **Every change ships its tests and its manual page update in the same PR.** An item isn't done until code, tests and docs are merged together.
5. **No AI attribution trailers** (`Co-Authored-By: <AI>`) in commits or PRs.
6. **No new dependency without a row** in [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).
7. **Platform services go through ports.** Domain code uses identity, files, errors, heartbeats, mail and metrics only through `labra.core.ports` or the standard endpoints, never an adapter or vendor library directly ([ADR-0008](docs/adr/0008-platform-ports.md)). Authorisation stays in core.
8. **No personal footprint** in committed files: no home paths, usernames or machine hostnames. Write `~/…` or a placeholder.

## Working as an agent
- **Done means `scripts/ci_local.sh` is green,** not just `pytest`. A `WARN` stage is unchecked, not passed; say so when reporting.
- **End every piece of work with an audit:** re-read the tracker rows and the plan, review the full diff against them, and confirm each fix has a test that fails on the old code.
- **Follow the plan.** If it's ambiguous, stop and ask. Don't widen the scope; list unrelated improvements at the end instead.
- **After a context compaction,** run `git status` and `git diff --stat` before editing again.
- **Commands use repo-relative or absolute paths;** don't rely on an earlier `cd`.
- **Reuse search results** from earlier in the session instead of searching again.
- If `rtk` is installed, read exact file bytes with `rtk proxy cat` before an edit; its normal output is compressed. Known machine problems are in [`docs/dev/tooling-issues.md`](docs/dev/tooling-issues.md).

## Layout and commands
```
src/labra/        application package (Alembic migrations in src/labra/migrations/)
tests/            pytest (real Postgres via testcontainers)
docs/manual/      user manual (one page per screen)
docs/dev/         developer docs
docs/adr/         architecture decision records
scripts/          gates and operational scripts
```

| Task | Command |
|---|---|
| Install | `uv sync` |
| All local gates (same as CI) | `scripts/ci_local.sh` |
| Tests | `uv run pytest` |
| Lint and format | `uv run ruff check . && uv run ruff format .` |
| Types | `uv run pyright` |
| Pre-commit hooks (once per clone) | `uv run pre-commit install` |
| Dependency register | `uv run python scripts/audit_deps.py --check` (or `--refresh`) |
| Run the stack | `docker compose up -d` ([running the stack](docs/dev/running-the-stack.md)) |
| Release | [`docs/dev/releasing.md`](docs/dev/releasing.md) |

## Tracker IDs and tags
Every piece of work has a permanent ID in [`docs/TRACKER.md`](docs/TRACKER.md).

| Where | Convention | Example |
|---|---|---|
| Prefixes | `W` work · `M` minimal · `X` next expansion · `LT` later · `R` rejected (never implement) · `EC-<A–O>NN` enterprise checklist · dotted sub-item `M25.1` | — |
| Branch | `<type>/<primary-id-lowercase>-<slug>` | `feat/m07-billing`, `chore/w08-ci-gate` |
| Commit subject | `<type>(<scope>): <ID>[ <ID>…] <summary>`; every commit carries at least one ID; repo tooling uses `W01` or `W08` | `feat(billing): M07 M07.1 part payment, Rule 49 fields` |
| PR | title as the commit; body has `Items: M07, EC-B01` and `Manual: frontdesk/dues-and-payments` (or `Manual: no change — <reason>`) | — |
| Manual page | front matter `features: [M07, M23]` | — |
| Tests | `@pytest.mark.item("M07")` on the tests that prove the item | — |
| ADR | front matter `items: [W02]` | — |
| Code | **no IDs in code comments** (they go stale); test markers carry the traceability | — |
| Status | `todo → doing → done` (strike-through, date and PR), or `blocked` / `dropped` with a reason; updated in the same PR | — |
| New idea | next free number in its prefix, tracker row added in the same change; never renumber or reuse | — |
| Git tags | releases only, e.g. `v0.1.0`; the pilot tag is refused while any `W`, `M` or gate-P `EC` item is open | — |

## Docs in parallel
A screen and its manual page change together. Each route declares its page (`manual_page=`), and `scripts/check_manual.py` fails when a screen has no page or a page is older than its screen.

## Versions and changelog
SemVer `0.x` until the maintainers approve 1.0; PATCH for fixes and docs, MINOR for features (and breaking changes while on 0.x). A version bump updates `uv.lock` in the same commit. [`CHANGELOG.md`](CHANGELOG.md) follows Keep a Changelog with dated releases; git-cliff drafts it from commit subjects.

## Branching
Trunk-based on `master`. Short-lived branches, one item group each, merged after `scripts/ci_local.sh` is green.
