---
description: Implement one or more tracker items end to end
argument-hint: <ID> [<ID>…]
---

Implement tracker items: $ARGUMENTS

1. Read their rows in `docs/TRACKER.md`, the plan sections they reference and any plan written for them, all the way through. Then re-read `AGENTS.md`.
2. Create branch `feat/<primary-id-lowercase>-<slug>` (or `chore/…` for `W` items). Set each item's status to `doing`.
3. Work through the plan's phases in order. After each phase, run its checks (`scripts/ci_local.sh --only <stage>`) before moving on.
4. Write the code, the tests (`@pytest.mark.item("<ID>")`) and the manual page (`features: [<ID>]` front matter) together.
5. If the plan is ambiguous or reality doesn't match it, **stop and ask**. Don't improvise scope.
6. Run the full `scripts/ci_local.sh`. Report any `WARN` stage as unchecked.
7. Audit: re-read the rows and the plan, review the full diff, confirm each fix has a test that fails on the old code.
8. In the branch's last commit, set each item to `done` with the date and the branch's main commit, strike-through on ID and title. Never a status-only PR.

Commit subjects carry the IDs (`feat(scope): M07 …`), with no AI trailer. List improvements you noticed but didn't make at the end. Ask before pushing.
