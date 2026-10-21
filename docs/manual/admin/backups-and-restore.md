---
title: Backups and restore
features: [M16, EC-D01, W16, W07, EC-D02, EC-D03]
---

# Backups and restore

## What it's for

Labra copies the lab's data off the server all day, so a dead laptop, a stolen bag or a
mistaken delete costs at most the last few minutes of work.

- **What is copied:** the whole database (patients, visits, bills, results, reports, the
  audit log) and every stored file (report PDFs, signatures, logos, scanned outside reports).
- **Where it goes:** two places, each a complete copy on its own. One is Google Drive, so
  it survives a fire or theft at the lab. The other is a USB disk plugged into the server,
  so a restore doesn't wait on the internet.
- **How it is kept safe:** both copies are encrypted with the backup password before they
  leave the server. Google can't read them, and neither can anyone who picks up the disk.
  Without that password the backups can't be opened at all, so keep it on paper with the
  disk's key (see *Good to know*).
- **When:** every 15 minutes during lab hours (07:00 to 21:00), and once more at 23:30.
- **How long:** every copy from the last 2 days, then one an hour for 7 days, one a day for
  30 days, and one a month for 2 years. The 23:30 run clears out the rest.
- **Checked every month:** on the first Sunday at 03:00, Labra restores the newest copy from
  each place into a scratch database and checks it is complete, so a broken backup is found
  long before it's needed.

## Where to find it

There is no screen yet. An administrator runs the commands on the server, in the folder
where Labra was installed. Timers on the server start the regular backups by themselves.

## Steps

### Setting it up (once)

1. Make the backup password and keep a paper copy:

   ```bash
   openssl rand -base64 24 | tr -d '\n' > secrets/restic_password
   chmod 644 secrets/restic_password
   ```

2. Connect Google Drive. On any computer with a web browser and rclone installed, run
   `rclone config`, add a remote named `drive` of type **Google Drive**, and sign in with
   the lab's Google account. Copy the `[drive]` section of the file it wrote (shown by
   `rclone config file`) into `secrets/rclone.conf` on the server, then
   `chmod 644 secrets/rclone.conf`.
3. Plug in the USB disk and mount it at `/mnt/labra-backup`, so that it mounts by itself at
   start-up (the install guide shows how). Make it writable by the account Labra runs as:
   `sudo chown 10001 /mnt/labra-backup`.
4. In the `.env` file beside `compose.yaml`, set where the copies go:

   ```bash
   LABRA_BACKUP_REPO_DRIVE=rclone:drive:labra-backup
   LABRA_BACKUP_REPO_USB=/backup/usb/labra
   ```

   `/backup/usb` is the USB disk as the backup job sees it. Set `LABRA_BACKUP_USB_DIR` if
   the disk is mounted somewhere other than `/mnt/labra-backup`.
5. Create the two backup stores: `scripts/backup.sh init`. Running it again is harmless.
6. Install the timers for the backups and the monthly check:
   `sudo scripts/install_timers.sh`. Add `--interval 30m` (or `2h`, `4h`, `24h`) for fewer
   runs, and `--lab-hours 08:00-20:00` for other hours. `24h` means the 23:30 run only. Run
   it again to change the schedule.
7. Take the first backup by hand and check it worked: `scripts/backup.sh backup`.

### Checking the backups

- `systemctl list-timers 'labra-*'` shows when the next backup runs and when the last one did.
- `scripts/backup.sh snapshots` lists the copies in both places.
- Every run is written in the run log, and a failed run sends an alert (see below).

### Taking a backup now

Run `scripts/backup.sh backup`, for example before changing the server. If a scheduled
backup is running, it waits for that one to finish first.

### The monthly check (restore drill)

The check runs by itself. It takes the newest copy from Google Drive and from the USB disk,
loads each into a scratch database, compares every table with the backup and checks the
audit log there, then deletes the scratch database. The lab's own data is never touched, and
staff can keep working.

- To run it now, for example after fixing a failed one: `scripts/drill.sh`. Each line it
  prints names a copy (`drive` or `usb`) and what was found.
- A failed check sends an alert (see *Good to know*). The
  [restore runbook](../../runbooks/restore-from-backup.md#when-the-drill-fails) says what to
  do for each message.

### Restoring the data

Restoring replaces what is in Labra with a backup, so everything entered after that backup
is lost. Follow the [restore runbook](../../runbooks/restore-from-backup.md), which covers a
new server and undoing a mistake on the same one. In short:

1. `scripts/backup.sh snapshots` lists the copies; the newest is at the bottom. Times are in
   UTC (IST is 5 hours 30 minutes ahead).
2. On the same server, take one more backup first: `scripts/backup.sh backup --tag
   before-restore`.
3. `scripts/restore.sh --replace <ID>` restores that copy (leave out the ID for the newest).
   Labra stops while it runs, then starts again and checks the audit log. It says
   `Restore finished.` at the end.

Without `--replace`, a restore only runs into an empty database, as on a new server, so data
is never overwritten by mistake. A restore that fails while loading the database leaves it as
it was. If only the stored files fail, Labra stays stopped and the message says what to do
([Restore from backup](../../runbooks/restore-from-backup.md#restore-incomplete)).

## Screenshot

There is no screen to show.

## Good to know

- **Alerts:** set `LABRA_HEARTBEAT_URL_BACKUP` in `.env` to a check's ping address on a
  monitoring service such as Healthchecks.io (it must start with `https://`). Every good run
  pings it. A failed run pings its `/fail` address with the reason, and a run that never
  happens sends no ping. Either way the service emails or messages you. Set the check's
  period to the backup interval, so a server that is off is noticed too.
  [Alerts and nightly checks](alerts-and-checks.md) sets up every check in one go.
- **Alerts for the monthly check:** set `LABRA_HEARTBEAT_URL_DRILL` the same way, with the
  check's period set to one month plus a few days' grace.
- **The USB disk isn't plugged in:** the run still copies to Google Drive, then counts as
  failed, so you get the alert. Labra never writes the backup onto the server's own disk in
  place of the USB disk. Plug it back in and the next run copies to it again.
- **No internet:** the Google Drive copy fails and you get the alert. The USB copy is still
  made. The next run with internet sends everything that changed since.
- **The backup password:** write it on paper and keep it with the disk encryption key, away
  from the server. A new server needs it to read the backups. Nobody can recover it.
- **Space:** after the first run, each run adds only what changed, usually a few megabytes.
  Google Drive's free 15 GB lasts years for a small lab.
- A backup never stops the lab working. Staff can keep using Labra while it runs.
