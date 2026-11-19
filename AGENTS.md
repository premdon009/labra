# AGENTS.md

Instructions for anyone, human or AI agent, changing this repository. Detail lives in the
files linked below.

## What Labra is
Open-source software (MIT) for small Indian diagnostic lab chains: patients, visits, billing, samples, in-house and outsourced tests, results, reports. One main lab plus a few collection centres, running on a small server (an old laptop or mini PC) at the main lab, reachable from the branches.

- Design: [`docs/design/v1-plan.md`](docs/design/v1-plan.md)
- What's left: [`docs/TRACKER.md`](docs/TRACKER.md)
- Release checklist: [`docs/ENTERPRISE_CHECKLIST.md`](docs/ENTERPRISE_CHECKLIST.md)

## Hard rules
1. **Synthetic data only.** No real patient, staff or lab names, numbers or results anywhere: code, tests, fixtures, screenshots, issues, commits.
2. **Never name the commercial lab product** that the feature checklist was taken from, or its vendor, and never copy its wording or screenshots. A local pre-commit hook checks for this. When checking for the names, report counts or file names only, never the names themselves. Don't re-analyse the product's material unless a maintainer asks.
3. **Secrets come from the environment only.** Never commit `.env*`, keys, passwords or tokens. Never read `.env*`, `data/` or backups while working.
4. **Every change ships its tests and its manual page update in the same PR.** An item isn't done until code, tests and docs are merged together.
5. **No AI attribution trailers** (`Co-Authored-By: <AI>`) in commits or PRs.
6. **No new dependency without a row** in [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md), **and no version released less than 7 days ago** unless it fixes a published advisory (an Age exceptions row there).
7. **Platform services go through ports.** Domain code uses identity, files, errors, heartbeats, mail and metrics only through `labra.core.ports` or the standard endpoints, never an adapter or vendor library directly ([ADR-0008](docs/adr/0008-platform-ports.md)). Authorisation stays in core.
8. **No personal footprint** in committed files: no home paths, usernames or machine hostnames. Write `~/…` or a placeholder.

## Working as an agent
- **Done means `scripts/ci_local.sh` is green,** not just `pytest`. A `WARN` stage is unchecked, not passed; say so when reporting.
- **Follow the plan and the [workflow](docs/dev/workflow.md):** one item group per branch, stop and ask if the plan is ambiguous, end with the diff-against-plan audit, close tracker rows in the work PR.
- **Continuing a run:** when told to continue a run of item groups, do them back to back, and commit each group locally once its gate is green.
- **One push per round:** green locally, plus `scripts/ci_portability.sh --if-needed`, before pushing; one branch and PR per round; reproduce CI failures locally ([why](docs/dev/workflow.md#one-push-per-round)).
- **The maintainer decides what leaves the machine.** Say so before any push that starts a workflow. Never open or merge a PR, or change a GitHub setting (the ruleset, Actions, secrets), without the maintainer's go; maintainers do the merge.
- **After a context compaction,** run `git status` and `git diff --stat` before editing again.
- Use repo-relative or absolute paths, and reuse earlier search results. If `rtk` is installed, read exact bytes with `rtk proxy cat` before an edit ([tooling issues](docs/dev/tooling-issues.md)).

## Commands
`uv sync` · `scripts/ci_local.sh` (all gates, same as CI) · `uv run pytest` · `docker compose up -d`.
Full table and layout: [workflow](docs/dev/workflow.md#commands).

## Tracker IDs
Every piece of work has a permanent ID in [`docs/TRACKER.md`](docs/TRACKER.md). Commit subject
`<type>(<scope>): <ID>[ <ID>…] <summary>`, branch `<type>/<id>-<slug>`, no IDs in code comments.
All conventions: [workflow](docs/dev/workflow.md#tracker-ids-and-tags).

## Docs, versions, branching
A screen and its manual page change together: each route declares its page (`manual_page=`), and
`scripts/check_manual.py` fails when a screen has no page or a page is older than its screen.
SemVer `0.x` and trunk-based on `master` via PRs: [workflow](docs/dev/workflow.md#versions).
