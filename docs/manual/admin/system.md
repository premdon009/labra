---
title: System
features: [EC-E04, EC-G01]
---

# System

## What it's for

One page that shows whether the server is healthy: the Labra version, the last backup and
the other scheduled jobs, disk space, the database's size, migrations not yet applied, and
when the HTTPS certificate runs out. Open it once a week, and whenever an alert comes.

## Where to find it

**Menu ▸ System**, or the **System** card on the home page. Administrators and branch
managers see it. Others can't open it.

## Steps

1. Open **System**. If anything needs attention, a message at the top says how many, and
   each one is marked in red.
2. Read the marked rows and act on them. See *Good to know*.

The page only reads. Nothing on it changes the lab's data.

## Screenshot

<!-- screenshot: admin-system.png (taken with the demo data) -->

## Good to know

| Row | Red when | What to do |
|---|---|---|
| **Version** | never | Quote it when reporting a problem. It is also at the foot of every page. |
| **Database** | a migration isn't applied | An upgrade stopped half way. Run `docker compose up -d` again; it applies migrations first. |
| **Disk space** | the disk is 80% full or more, or can't be read | See [Alerts and nightly checks](alerts-and-checks.md). |
| **HTTPS certificate** | it has run out, or a long-lived one has fewer than 30 days left | Caddy's own certificate lasts hours and is renewed by itself, so it is red only if renewal has stopped: restart the proxy (`docker compose restart proxy`). A certificate you made yourself (nginx) must be made again and installed on the main-lab PCs. |
| **Backup** | the last run failed, or the last good one started more than 12 hours ago | The *Detail* column says why. See [Backups and restore](backups-and-restore.md). |
| **Restore drill** | it failed, or hasn't run for 35 days | See [Restore from backup](../../runbooks/restore-from-backup.md#when-the-drill-fails). |
| **Audit log check** | it failed, or hasn't run for 26 hours | A failure is serious; see [Alerts and nightly checks](alerts-and-checks.md). |
| **Disk space check** | it failed, or hasn't run for 2 hours | As for *Disk space*. |
| **Upgrade** | the last upgrade failed and was rolled back | The *Detail* column says why; the lab runs the old version meanwhile. |

- **Never run** in red means the timers aren't installed: run
  `sudo scripts/install_timers.sh` on the server. A new server shows this until each job has
  run once.
- Times are in the lab's time zone and show when each run started.
- The page doesn't send alerts. The monitoring service does (see
  [Alerts and nightly checks](alerts-and-checks.md)), so a server that is off is noticed even
  though nobody can open this page.
- The certificate is read from the proxy inside the server. If it shows *Can't be read*, the
  proxy isn't running, or `LABRA_CERT_CHECK_HOST` points elsewhere. Set it empty to stop the
  check.
