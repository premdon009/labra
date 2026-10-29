---
items: [M16, W07]
status: accepted
date: 2026-10-16
---

# ADR-0013: Backups run from host timers in a one-shot container

## Context
Backups (M16), the monthly restore drill (W07) and the nightly checks need something to start
them on time. The stack has no scheduler and no worker process (§1a). The app image has no
`pg_dump`. Debian 13's own client is version 17, and `pg_dump` refuses to dump a newer server.

Design §17.3 fixes what a backup is: a plain, uncompressed `pg_dump` plus `/data/files`, put
into restic (encrypted, deduplicated) on Google Drive through rclone, with a second copy on a
USB disk. It runs every 15 minutes in lab hours plus nightly, and keeps snapshots for 2 days,
hourly for 7 days, daily for 30 days and monthly for 24 months. Each run pings a monitor.

## Options
**Host timers and a one-shot `backup` container (chosen by the owner, 2026-10-16).**
- systemd timers on the host run `compose --profile jobs run --rm backup …` and exit.
- Nothing runs between jobs, and the web container never holds backup credentials.
- It needs a few unit files installed on the host (`scripts/install_timers.sh`).

**A long-running container with its own cron.** Nothing to install on the host, and the same
on Docker, Podman and Incus. But it adds one more always-on process, and the plan says
"systemd timer".

**A `labra backup` command in the app image.** It would reuse the Python heartbeat and job
metrics, but the app image would grow by the Postgres client, restic and rclone, and every app
container would carry the backup secrets.

## Decision
- **Image:** `deploy/backup/Dockerfile` builds from the same `postgres:18` image as the
  database, pinned by digest, so `pg_dump` and `psql` always match the server. It adds
  restic and rclone release binaries, checked against their SHA-256 for each architecture.
- **Compose:** the `backup` service sits under the `jobs` profile, so `up -d` never starts
  it. It joins the internal `db` network and its own `egress` network, which has internet
  access. The restic password and the rclone config are Compose secrets.
- **One dump, two independent repositories.** Each run dumps the database to a file once,
  then makes one restic snapshot of that dump plus `/data/files` in each configured
  repository: Google Drive (`rclone:` backend) and the USB disk.
  - A missing USB disk fails the run, which sends the alert, but doesn't stop the Drive copy.
  - The two snapshots have different IDs but the same content.
  - `restic copy` from one repository to the other was not chosen. Copying from Drive
    downloads everything, and copying from USB leaves Drive empty whenever the disk is
    unplugged.
- **Retention:** `forget --prune` runs only in the nightly job, with `--keep-within 2d
  --keep-within-hourly 7d --keep-within-daily 30d --keep-within-monthly 24m`. Snapshots carry
  the host name `labra`, so a restore works on any machine.
- **Run log:** every job (backup, drill, verify, disk check, upgrade) adds a row to the
  append-only `ops_run` table. The shell jobs insert it with `psql`, and the System page reads
  it.
- **Heartbeats:** the shell jobs ping `LABRA_HEARTBEAT_URL_<JOB>` with `curl`, following the
  same rules as `HttpHeartbeat`: https only, `/fail` appended on failure, body capped at
  10 kB. An unreachable monitor never fails a job. Web has no route to the internet, so the
  audit and disk checks it runs are pinged from the backup image too: `scripts/labra.sh`
  passes their result to `labra-backup ping`.
- **Restore drill:** restores the newest snapshot into a scratch database that lives only for
  the drill. It checks that every table holds as many rows as the dump's `COPY` blocks, and
  runs `labra audit verify` against that database.
- **Restore:** the dump loads in one transaction whose last statement is that row-count
  check, so a mismatch rolls the whole load back. The stored files come after the commit; if
  they fail, the job exits 4 and `restore.sh` leaves Labra stopped until the restore is run
  again.

## Consequences
- **Host requirement:** the server needs systemd and the unit files from
  `scripts/install_timers.sh`. A host without systemd can run the same commands from cron.
- **Image size:** the backup image is about 450 MB. It shares no layers with the app image.
- **Pins:** restic and rclone get rows in `docs/DEPENDENCIES.md`, and their pins are updated
  like any image.
- **Alternatives** (`docs/dev/services.md`, §19.2):
  - Borg could replace restic.
  - restic's own S3, B2 or SFTP backends could replace rclone.
  - WAL archiving (EC-D08, gate 1) is the path to an RPO under a minute.
