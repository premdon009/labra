---
items: [W01, W08.1, W37]
---

# Development workflow

## One item group at a time
1. Pick the tracker rows (`docs/TRACKER.md`). Set them to `doing`.
2. Branch from `master`: `<type>/<primary-id>-<slug>`.
3. Write a short plan: files, data changes, tests per item, manual pages. Larger groups get one plan, followed phase by phase.
4. Build code, tests and manual page together. Tests prove items with `@pytest.mark.item("<ID>")`.
5. `scripts/ci_local.sh` green. `pytest` alone isn't enough: types, imports, tracker and manual gates run there too. A `WARN` stage is unchecked, not passed; CI runs `scripts/ci_local.sh --strict`, where it fails ([Setup](setup.md#first-run)).
6. **End-of-work audit:** re-read the tracker rows and the plan, review the whole diff against them, and confirm every fix has a test that would fail on the old code.
7. In the branch's last commit before the push, set the rows to `done` with the date and the branch's main code commit (`2026-10-26 · 1a2b3c4`); the merge commit keeps that hash on `master`. Run `scripts/ci_portability.sh --if-needed` when the branch touches what the portability workflow watches ([Container runtimes](runtimes.md#run-the-portability-jobs-locally)), then push once, open the PR, and a maintainer merges it when CI is green. A fix for a CI failure goes into the same PR and the rows stay `done`. There is never a PR that only changes a row's status.

## `master` is protected
Changes reach `master` only through a pull request whose `gate` and `image` checks are green. Nobody pushes to it directly, administrators included, and it is never force-pushed or deleted. A GitHub ruleset on `master` enforces all of this, with nobody on its bypass list.

Merge with a merge commit, not a squash or a rebase: tracker rows record the hashes of the branch's commits, and only a merge commit keeps them. Bring `master` into a branch that has fallen behind before merging it.

A SQLAlchemy or pypdf deprecation warning fails the test that hits it (`filterwarnings` in `pyproject.toml`). Move to the replacement the warning names; don't silence it. A `ResourceWarning` fails too: close the cursor, file or response with `with` (a streamed query that may return early, such as `yield_per`, needs `with db.execute(...) as rows`).

If the plan turns out to be ambiguous, stop and ask rather than guess. A small improvement noticed along the way that isn't part of the items gets its own tracker ID and commit; larger ones go in the PR description as suggestions, not into the diff.

## Commits
- Subject: `<type>(<scope>): <ID>[ <ID>…] <summary>`. The commit-msg hook rejects a subject without a tracker ID.
- No AI attribution trailers; the commit-msg hook strips them.
- Keep commits to one item group.

## Versions
SemVer 0.x until the maintainers agree on 1.0 (the version gate refuses ≥ 1.0.0 without `LABRA_ALLOW_MAJOR=1`).

| Change | Bump |
|---|---|
| Fix, docs | PATCH |
| Feature, or a breaking change while on 0.x | MINOR |

A version bump changes `pyproject.toml` and `uv.lock` in the same commit, and `CHANGELOG.md` gets a dated heading.

## Working with AI agents
`AGENTS.md` is the shared instruction file (`CLAUDE.md` and `GEMINI.md` point to it). After an agent's context is compacted, it runs `git status` and `git diff --stat` before editing again, so it doesn't redo or undo work.
