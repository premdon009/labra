---
items: [W07, EC-D02, EC-D03]
---

# Restore from backup

Use this when the server is dead, stolen or its disk has failed, when the database is damaged,
or when a mistake changed a lot of data and has to be undone.

**Targets ([EC-D03](../ENTERPRISE_CHECKLIST.md)):**

- **At most 15 minutes of work lost (RPO).** Backups run every 15 minutes in lab hours and
  once at 23:30 ([design §17.3](../design/v1-plan.md)).
- **Back in business within 2 hours (RTO)** on any spare laptop or mini PC.

**What you need:**

- the backup password, on paper, kept with the disk encryption key;
- the USB backup disk, or internet access and the lab's Google account;
- for a new server: a laptop or mini PC with Debian 13 or Ubuntu 24.04 and Docker.

Everything written after the snapshot you restore is lost. Ask the front desk and the lab to
keep the paper trail (bills, sample labels, worksheets) from that time, so it can be entered
again.

## Pick the case

| What happened | Go to |
|---|---|
| The server is dead, stolen or won't start | [A new server](#a-new-server) |
| The server runs, but the data is damaged or a mistake has to be undone | [The same server](#the-same-server) |
| The monthly drill alert came | [When the drill fails](#when-the-drill-fails) |
| An upgrade failed and so did its rollback (`THE ROLLBACK FAILED`) | [The same server](#the-same-server), step 3 only |

## A new server

About 1–2 hours, most of it installing the operating system and Docker.

1. Install the operating system with disk encryption, then Docker, as for the first install.
2. Get Labra at the **same version** the old server ran (it is in the release notes, or on
   the System page if you have a screenshot), or a newer one:

   ```bash
   git clone https://github.com/premdon009/labra.git && cd labra
   git checkout v0.1.0      # the version the old server ran
   ```

3. Make the secrets as in [Running the stack](../dev/running-the-stack.md) (*First start*,
   step 1, and *Backups*). A **new** database password is fine, because the backup holds no
   database passwords. Two things must be the old ones:
   - `secrets/restic_password`: the backup password from the paper copy. Type it at the
     prompt, so it stays out of the shell history:

     ```bash
     read -rsp 'Backup password: ' pw && printf '%s' "$pw" > secrets/restic_password; unset pw
     chmod 644 secrets/restic_password
     ```

   - `secrets/rclone.conf`: copy the old one, or make a new one with `rclone config` and the
     lab's Google account (remote name `drive`).
4. Copy `.env` from the old server if you have it. Otherwise set at least
   `LABRA_BACKUP_REPO_DRIVE` and `LABRA_BACKUP_REPO_USB` as on the
   [Backups and restore](../manual/admin/backups-and-restore.md) page.
5. Plug in the USB disk and mount it at `/mnt/labra-backup`. If it is lost too, leave
   `LABRA_BACKUP_REPO_USB` empty and the restore uses Google Drive.
6. **Don't start Labra yet.** Check the backups can be read, then restore:

   ```bash
   scripts/backup.sh snapshots      # the newest one is at the bottom
   scripts/restore.sh               # the newest snapshot, from the USB disk if there is one
   ```

   `restore.sh` starts the database on its own, loads the snapshot in one transaction,
   checks every table holds as many rows as the backup, puts the stored files back, starts
   Labra and checks the audit log. It ends with `Restore finished.`
   - Add `--from drive` to read from Google Drive instead of the USB disk.
   - If Labra was already started on this server, its database has empty tables and the
     restore stops with "the database already has tables". Run it again with `--replace`.
7. Sign in, open today's worklist and the latest bills, and check they look right.
8. Point the lab at the new server:
   - main-lab PCs: change `labra.lan` in the router's DNS or the hosts files to the new
     address, and install the new server's certificate;
   - branches: start the tunnel with the same token as before
     (`LABRA_TUNNEL_TOKEN=… docker compose --profile tunnel up -d`), or join the new server
     to the tailnet.
9. Install the timers again (`sudo scripts/install_timers.sh`) and take a backup by hand
   (`scripts/backup.sh backup`). The old backups stay in the same repositories.
10. Tell the staff which time the data goes back to (the snapshot's time), and enter the
    paper records from after it.

## The same server

1. Find the snapshot from just before the damage or the mistake:

   ```bash
   scripts/backup.sh snapshots
   ```

   Times are in UTC: add 5 hours 30 minutes for IST. Note the snapshot's ID (the first
   column, for example `4f3e2d1c`).
2. Take one more backup first, so this restore can itself be undone:

   ```bash
   scripts/backup.sh backup --tag before-restore
   ```

3. Restore over the current data. Labra stops while it runs (a few minutes for a small lab):

   ```bash
   scripts/restore.sh --replace 4f3e2d1c
   ```

   If anything fails, the database is left as it was and the message says why.
4. Steps 7 and 10 of *A new server*.

After a failed upgrade whose rollback failed too, `scripts/upgrade.sh` names the snapshot it
took just before (for example `usb:4f3e2d1c`) and has already put the old version back in
`.env`. Skip steps 1 and 2, and restore that snapshot from that copy:
`scripts/restore.sh --replace --from usb 4f3e2d1c`.

## When the drill fails

The drill runs on the first Sunday of each month at 03:00. It reads the newest snapshot from
each repository into a scratch database (`labra_drill`), compares every table with the
backup, checks the audit log's hash chain there, then deletes the scratch database. The lab's
own data is never touched. Its result is in the alert and in the run log:

```bash
docker compose exec db psql -U labra -c \
  "select started_at, ok, detail from ops_run where kind = 'drill' order by id desc limit 3"
```

Each line of the detail names a repository (`drive` or `usb`):

| The detail says | What to do |
|---|---|
| `restore failed: … is damaged` | That repository is broken; the other one is probably fine. For the full message, run `scripts/backup.sh restore --scratch labra_drill --from usb` (or `--from drive`), then `scripts/backup.sh drop-database labra_drill`. To start a fresh repository, rename the broken one's folder on the USB disk or in Drive, then run `scripts/backup.sh init` and `scripts/backup.sh backup`. |
| `restore failed: no repository at … (is the disk mounted?)` | Plug in and mount the USB disk, then run `scripts/drill.sh` again. |
| `restore failed: the restored tables don't match the dump` | The backup is incomplete. Run `scripts/backup.sh backup`, then `scripts/drill.sh`. If it fails again, report it as a bug. |
| `AUDIT LOG DAMAGED: … row N: …` | The audit log in the backup has been changed or cut short. Run `docker compose exec web labra audit verify` on the live data and tell the owner straight away. |
| `the backup job did not start` | Docker or the backup image is missing. Run `scripts/backup.sh version` and read the error. |

After a fix, run the drill by hand and check it ends with no failure: `scripts/drill.sh`.

## Rehearsals

The restore must work before the pilot, not only on paper.

| When | Where | What | Time taken |
|---|---|---|---|
| Every release | `scripts/stack_smoke.sh` | drill of both repositories, a refused restore, a `--replace` restore, sign-in afterwards, a damaged repository | a few minutes |
| Before the pilot | the lab's laptop | *A new server*, from the USB disk and then from Drive, timed against the 2-hour target | to be filled in |
