# Contributing to Labra

Thanks for helping. Labra is maintained by a small team, so the rules below keep changes easy to review.

## Before you start
- Find or add the item in [`docs/TRACKER.md`](docs/TRACKER.md). Every change carries a tracker ID.
- Read [`AGENTS.md`](AGENTS.md). Its hard rules apply to everyone, human or AI.
- For anything larger than a fix, open an issue first so the approach can be agreed.

## Never include real patient data
Not in code, tests, fixtures, screenshots, issues or logs. Use `labra seed` data. If you report a bug from a real lab, describe it with made-up values.

## Setup
See [`docs/dev/setup.md`](docs/dev/setup.md). In short: `uv sync`, then `uv run pre-commit install --hook-type pre-commit --hook-type commit-msg`.

## Making a change
1. Branch from `master`: `<type>/<id>-<slug>`, for example `feat/m07-billing`.
2. Write the code, its tests (`@pytest.mark.item("M07")`) and the manual page update together.
3. Run `scripts/ci_local.sh` until it's green. CI runs the same script.
4. Commit with the ID in the subject: `feat(billing): M07 part payment`.
5. Open a PR using the template: list the `Items:` and the `Manual:` page.

The full workflow, including how tracker rows move from `todo` to `done`, is in [`docs/dev/workflow.md`](docs/dev/workflow.md).

## Dependencies
No new dependency without a row in [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md): licence, last release, maintainers and the fallback if it's abandoned. `scripts/audit_deps.py --check` enforces this.

## Code of conduct
Taking part means following [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
