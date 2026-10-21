---
items: [W12, W11, EC-G03]
---

# Releasing

Anyone with write access can cut a release by following this page. Nothing depends on one
person's machine.

## Versions and tags
- Labra stays on `0.x` until the maintainers agree on 1.0 ([Workflow](workflow.md#versions)).
- Every minor release starts as a candidate, `vX.Y.0rc1`, which runs at a pilot lab for about a
  week before the final tag. The first pilot is `v0.1.0rc1`.
- `scripts/check_tracker.py --tag <tag>` decides whether a tag may be created. The pilot tag
  is refused while any `W`, `M` or gate-P checklist item is still open.

## Steps
1. On `master`, with `scripts/ci_local.sh` green and no WARN on the tests stage (Docker must
   be running, so the database tests ran):
   ```sh
   uv run python scripts/check_tracker.py --tag v0.1.0rc1
   ```
2. Draft the changelog section, then rewrite it for lab owners: what changed for them, not
   which files changed.
   ```sh
   git cliff --unreleased --tag v0.1.0rc1
   ```
3. In one commit (`chore(release): W12 v0.1.0rc1`):
   - `version` in `pyproject.toml`, then `uv lock` so `uv.lock` matches
   - `CHANGELOG.md`: rename `[Unreleased]` to `## [0.1.0rc1] - YYYY-MM-DD` and start a new
     empty `[Unreleased]`
   - for a final release, the default images in `compose.yaml`
     (`ghcr.io/premdon009/labra:<version>` and `ghcr.io/premdon009/labra-backup:<version>`)
4. Tag and push the tag:
   ```sh
   git tag -a v0.1.0rc1 -m "v0.1.0rc1"
   git push origin master v0.1.0rc1
   ```
5. The `release` workflow checks that the tag matches `pyproject.toml`, runs the tag gate and
   the full local gate, then builds amd64 and arm64 images on GHCR, `labra` and
   `labra-backup`, with the same tags:

   | Tag | Image tags |
   |---|---|
   | `v0.1.0rc1` | `0.1.0rc1` |
   | `v0.1.0` | `0.1.0`, `0.1`, `release` |

6. Create the GitHub release from the tag, pasting the changelog section and attaching
   `compose.yaml` and `Caddyfile`.

## Labs install from a release
Labs use the `compose.yaml` attached to a release, never the one on `master`, and it names an
exact image version. Postgres is pinned by digest and never on a rolling tag.

## Labs upgrade with one command
`scripts/upgrade.sh 0.2.0` moves a running lab to another release and rolls back by itself
when the new version doesn't come up ([System](../manual/admin/system.md) has the steps for
labs):

1. Pulls the image and checks the disk. If either fails, nothing has changed.
2. Stops the web app, then takes a backup tagged `pre-upgrade`. Nothing is written after it,
   so a rollback loses no work.
3. Starts the stack on the new image: migrations, then the app, which must answer `/readyz`
   within `LABRA_UPGRADE_WAIT` seconds (default 180).
4. If that fails, restores the backup over the database (`restore --replace`, the whole
   schema in one transaction), starts the old image and checks the audit log. Exit 4.
5. If the rollback fails too, exit 5, naming the snapshot for
   [Restore from backup](../runbooks/restore-from-backup.md#the-same-server).

The image in use is written to `LABRA_IMAGE` in `.env`, so a later `docker compose up -d`
keeps it. Every upgrade, good or rolled back, is a row in the run log. A release whose
`compose.yaml` changed beyond the image tags says so in its changelog: the lab copies the
new `compose.yaml` and `scripts/` first, keeping `.env` and the secrets, then runs the
upgrade. The rollback never runs down-migrations: putting the pre-upgrade backup back is
the way back, whatever the migrations did.

`scripts/ci_local.sh --only stack` proves it: an upgrade to a rebuilt image, then one to an
image with a migration that fails, which must roll back with the data intact.
