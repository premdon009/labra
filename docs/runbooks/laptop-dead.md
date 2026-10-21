---
items: [EC-L03, W07, EC-D03, EC-D06]
---

# Laptop dead or won't start

Use this when nobody can open Labra, at the main lab or the branches, because of the server
itself: it is off, won't start, has crashed, or is gone. The target is to be working again
within **2 hours** ([EC-D03](../ENTERPRISE_CHECKLIST.md)), losing at most the last 15 minutes.

Start the staff on paper straight away ([Working on paper](../manual/troubleshooting/working-on-paper.md)),
then work down the list. Most "dead" servers are one of the first three.

## 1. Is it on?

- **Power:** is the UPS on and its battery not flat? Is the laptop's charging light on? A
  power cut longer than the UPS lasts switches everything off; the laptop starts by itself
  when power returns (the install guide set **power on after power loss**), but the UPS may
  have to be switched on by hand.
- **Lid and screen:** open the lid or plug in a screen. If it asks for the **disk passphrase**
  (*Please unlock disk*), type it: the paper copy is kept with the backup password. This
  happens after a power cut on a laptop without automatic unlocking (see the install guide,
  *Disk encryption*).
- **It shows a login prompt:** the operating system is up. Go to step 2.
- **Nothing on the screen, no lights:** try another charger and another socket, hold the
  power button for 10 seconds, then press it again. Still nothing: step 4.

## 2. The server is up, Labra isn't

Sign in to the server (its keyboard, or `ssh` from a main-lab PC), go to the folder where
Labra is installed (for example `cd /opt/labra`), then:

```bash
docker compose ps                     # every service should be "Up" or "healthy"
docker compose up -d                  # start what isn't running
docker compose logs --tail 50 web     # if web keeps restarting, the reason is here
df -h /                               # a full disk stops the database
```

- **The disk is full:** [Disk full](disk-full.md).
- **`docker` itself isn't running:** `sudo systemctl restart docker`, then `docker compose up -d`.
- **The logs name the database** (`connection refused`, `could not connect`): run
  `docker compose logs --tail 50 db`. A message about damaged data or checksums means the
  disk is failing: take a backup now if one still works (`scripts/backup.sh backup`), then
  step 4 on a new disk or server.
- **After an upgrade:** `scripts/upgrade.sh` rolls back by itself; if it printed
  `THE ROLLBACK FAILED`, follow [Restore from backup](restore-from-backup.md#the-same-server).

Check with a main-lab PC that Labra opens, then let the branches know.

## 3. It starts, then stops or is very slow

- **It switches off after a while:** it is overheating or the battery is failing. Clean the
  vents, raise it off the desk, and check the charger. Order a replacement and plan step 4 for
  a quiet hour.
- **Very slow:** `free -h` and `top` show whether memory is full. Restart it
  (`sudo reboot`); Labra starts with it.

## 4. Move to a spare laptop

When the server won't start, its disk has failed, or it was stolen, put Labra on any spare
laptop or mini PC, from the backups: [Restore from backup](restore-from-backup.md#a-new-server).
You need the backup password and the disk passphrase (on paper), the USB backup disk (or the
lab's Google account), and the lab's `.env` and `secrets/` if they were kept elsewhere. Time
each step: the restore drill table there records how long it took.

## If it was stolen

The disk is encrypted, so the data on it can't be read without the passphrase. Still:

1. Tell the owner the same day. A lost device with patient data on it may have to be
   reported; the owner decides ([compliance checklist](../compliance/COMPLIANCE_CHECKLIST.md),
   breach notification).
2. Cut its access to everything outside the lab:
   - **Google Drive:** in the lab's Google account, *Security ▸ Third-party access*, remove
     rclone. The new server gets a new `rclone.conf` (step 4).
   - **Cloudflare Tunnel:** in the Cloudflare dashboard, open the tunnel and *Refresh token*
     (or delete it and create a new one), then use the new token on the new server
     ([Certificate and tunnel renewal](certificate-and-tunnel.md#the-tunnel-stopped-working)).
   - **Tailscale or NetBird:** remove the old machine in the admin console.
3. Restore on a new server (step 4). Then, as a precaution, ask every member of staff to set a
   new password at their next sign-in (an administrator resets each on the Staff screen).

## Afterwards

- Enter the paper records ([Working on paper](../manual/troubleshooting/working-on-paper.md#afterwards)).
- Note in the lab's incident log what happened, how long Labra was down and what was lost.
