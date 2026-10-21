---
title: Alerts and nightly checks
features: [EC-D05, EC-B06, EC-E02]
---

# Alerts and nightly checks

## What it's for

Labra checks itself on a timer and tells the owner when something needs attention, by email
or Telegram, before the staff notice. The checks are:

| Check | When | It alerts when |
|---|---|---|
| **Backup** | every 15 minutes in lab hours, and 23:30 | a backup fails, or doesn't run at all |
| **Restore drill** | first Sunday of the month, 03:00 | a backup can't be restored completely ([Backups and restore](backups-and-restore.md)) |
| **Audit log** | every night, 02:30 | the audit log's hash chain is broken: someone changed history |
| **Disk space** | every hour | the server's disk is 80% full or more |
| **Watchdog** | every 5 minutes | Labra can't be reached: the server is off, the internet line is down, or the tunnel to the branches has stopped |

The alerts come from a monitoring service, Healthchecks.io (free for a small lab). Each check
pings it when it runs. A failed check pings its failure address and the alert goes out at
once. A check that never runs sends nothing, and the service raises the alert when the ping
is late. That is how a dead server is still noticed.

## Where to find it

There is no screen yet. The timers on the server run the checks by themselves; an
administrator sets up the alerts once, on the server and on Healthchecks.io.

## Steps

### Setting up the alerts (once)

1. Sign up at healthchecks.io with the owner's email. Under **Integrations**, add Telegram
   or a second email if wanted.
2. Add one check for each row below. Set its time zone to Asia/Kolkata, and copy its ping
   address (it starts with `https://hc-ping.com/`).

   | Check name | Schedule | Grace time |
   |---|---|---|
   | Labra backup | Cron `*/15 7-20 * * *` (or your own backup hours) | 30 minutes |
   | Labra restore drill | Simple, every 30 days | 7 days |
   | Labra audit log | Cron `30 2 * * *` | 1 hour |
   | Labra disk space | Simple, every 1 hour | 1 hour |
   | Labra watchdog | Simple, every 5 minutes | 10 minutes |

3. In the `.env` file beside `compose.yaml`, add the ping addresses and turn on sending:

   ```bash
   LABRA_HEARTBEAT=http
   LABRA_HEARTBEAT_URL_BACKUP=https://hc-ping.com/…
   LABRA_HEARTBEAT_URL_DRILL=https://hc-ping.com/…
   LABRA_HEARTBEAT_URL_AUDIT_VERIFY=https://hc-ping.com/…
   LABRA_HEARTBEAT_URL_DISK=https://hc-ping.com/…
   LABRA_HEARTBEAT_URL_WATCHDOG=https://hc-ping.com/…
   LABRA_WATCHDOG_URL=https://<the lab's public address>/healthz
   ```

   `LABRA_WATCHDOG_URL` is the address the branches use, so the watchdog checks the tunnel
   too. If the tunnel asks people to sign in (Cloudflare Access), add a rule that lets
   `/healthz` through without signing in; that page shows nothing private. Without a public
   address, leave it out and the watchdog checks the server only.
4. Apply it: `docker compose up -d`.
5. Install the timers, if not done yet: `sudo scripts/install_timers.sh`.
6. Try each check once. Each should turn green on Healthchecks.io:

   ```bash
   scripts/backup.sh backup
   scripts/labra.sh audit verify
   scripts/labra.sh check-disk
   scripts/watchdog.sh
   ```

### Running a check now

- Audit log: `scripts/labra.sh audit verify`. It ends with `Audit log intact: N rows
  checked.`
- Disk space: `scripts/labra.sh check-disk`. It prints how full the disk is. Add
  `--percent 90` to try another alert level.
- `systemctl list-timers 'labra-*'` shows when each check runs next.

## Screenshot

There is no screen to show.

## Good to know

- **Disk space alert:** find what grew. Old export files (`docker compose exec web ls -la
  /data/export`) can be copied off to an encrypted disk and deleted. Old Labra images can go
  with `docker image prune`. Don't delete anything in the database or the files folder.
  When the disk is full, Postgres stops saving, so act on this alert within days.
- **Audit log alert:** treat it as serious. It means a stored record was changed outside
  Labra, or the log was cut short. Don't try to fix it. Tell the owner, note the row number
  in the alert, and keep the server as it is until it has been looked at. The last good
  backup is listed in `scripts/backup.sh snapshots`.
- **Watchdog alert:** check in this order: is the server on and Labra open on a main-lab
  PC? Is the lab's internet working? Is the tunnel running
  (`docker compose --profile tunnel ps`)? If the main lab works but branches can't reach
  Labra, it is the internet line or the tunnel.
- The checks only read. None of them changes the lab's data, and staff can keep working
  while they run.
- Every run of the backup, the drill, the audit check and the disk check is kept in the run
  log, so a missed alert can be traced later. The watchdog isn't logged; it runs too often.
