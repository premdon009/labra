---
items: [W06, EC-L01, EC-A11, EC-A12, EC-D06, EC-D07]
---

# Installing Labra on the lab's server

This guide sets up Labra on one small computer at the main lab (an old laptop or a mini PC),
from a blank disk to a running lab with backups, alerts and branch access. Follow it in order;
each step ends with a check. It takes about half a day, most of it waiting for installs.

You need someone who is comfortable typing commands. Nothing here needs programming.

## What you need

| Item | Minimum | Why |
|---|---|---|
| The server | 2 CPU cores, 4 GB RAM, a 128 GB **SSD** (256 GB better), a wired network port | Labra, the database and the stored reports. A spinning disk is too slow. |
| A UPS | Enough for the server, the router and the network switch for 30 minutes | Power cuts must not stop the main lab or corrupt the disk |
| A USB disk | 500 GB or more, used only for Labra | The second backup copy, on site |
| A Google account | The lab's own, not a person's | The off-site backup copy, in Google Drive |
| A domain name and a Cloudflare account | For example `labra.example-lab.in` | Branches reach Labra through Cloudflare Tunnel, with no open ports |
| A Healthchecks.io account | Free | Alerts to the owner when a backup or a check doesn't run |
| An envelope and a pen | — | The disk passphrase and the backup password, on paper, kept by the owner |

The server's disk will be wiped. Copy anything you want to keep from it first.

## 1. The server's BIOS

Restart the server and open its setup screen (usually **F2**, **F10**, **Del** or **Esc** while
it starts). The names differ by maker; look for:

1. **Power on after AC loss** (also called *AC power recovery*, *Restore on AC power loss* or
   *After power failure*): set it to **On** (or *Power on*). The server then starts by itself
   when power comes back after the UPS runs out. Many laptops don't have it; for those, the
   UPS and a person pressing the power button are the plan.
2. **Wake on LAN**: on, if offered. It lets someone at the lab start the server from a phone.
3. **TPM** (*TPM 2.0*, *PTT* on Intel, *fTPM* on AMD): on, if offered. It is used in step 2 to
   unlock the disk by itself.
4. **Secure Boot**: leave it as it is.
5. Boot order: the USB stick first, for the install.

**Check:** with the server off, pull its power plug, wait ten seconds and put it back. If the
option is there, the server starts by itself.

## 2. Debian with disk encryption

Labra runs on Debian 13 (*trixie*), 64-bit. Download the *netinst* image from debian.org and
write it to a USB stick (with Rufus or balenaEtcher on a Windows PC).

Install it with these choices; leave the rest at their defaults:

| Installer screen | Choose |
|---|---|
| Hostname | `labra` |
| Domain name | leave empty |
| Root password | leave **empty**, so the first user can use `sudo` |
| User | a name for the person who looks after the server, with a strong password |
| Partitioning | **Guided – use entire disk and set up encrypted LVM** |
| Encryption passphrase | a long phrase of five or six words; **write it on the paper for the envelope** |
| Software selection | only **SSH server** and **standard system utilities** (no desktop) |

Disk encryption protects the patients' data if the server is stolen. Without the passphrase,
nobody can read the disk; not even the lab, so the paper copy matters.

**Check:** after the install, the server asks for the passphrase while starting, then shows a
`labra login:` prompt. Sign in with the user you made.

### Unlocking after a power cut

An encrypted disk needs its passphrase every time the server starts, so after a long power cut
the server waits at the passphrase prompt until someone types it. There are two ways to live
with that:

- **The TPM unlocks it** (if the server has TPM 2.0). The disk unlocks by itself on this
  server only; taken out and put in another computer, it still needs the passphrase.
- **Someone types the passphrase** after every start. With a working UPS that is rare, and the
  watchdog alert (step 8) tells the owner when the server is down.

To let the TPM unlock it, after step 3:

```bash
sudo apt install systemd-cryptsetup tpm2-tools dracut
lsblk -o NAME,TYPE,FSTYPE | grep crypto_LUKS            # the encrypted partition, e.g. sda3
sudo systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 /dev/sda3
```

Then add `tpm2-device=auto` to the options (the last column) of the line in `/etc/crypttab`,
for example `luks,discard,tpm2-device=auto`, and rebuild the start-up image with
`sudo dracut -f`. Restart. The server should start without asking. If it still asks, type the
passphrase: it keeps working whatever the TPM does. A BIOS update or a change to Secure Boot
can make the TPM refuse, and the passphrase prompt comes back; run the `systemd-cryptenroll`
line again with `--wipe-slot=tpm2` added.

Write on the envelope's paper which way this server unlocks.

## 3. The basics

Sign in on the server (or over SSH from a PC: `ssh <user>@<the server's address>`) and run:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git curl ca-certificates unattended-upgrades parted
sudo timedatectl set-timezone Asia/Kolkata
```

### Security updates by themselves

```bash
sudo dpkg-reconfigure -plow unattended-upgrades      # answer Yes
```

Debian then installs security updates every day by itself. Some of them (the kernel) only take
effect after a restart:

- If the TPM unlocks the disk, let it restart by itself at night: put
  `Unattended-Upgrade::Automatic-Reboot "true";` and
  `Unattended-Upgrade::Automatic-Reboot-Time "01:30";` in
  `/etc/apt/apt.conf.d/52unattended-upgrades-local`.
- If someone has to type the passphrase, don't: restart by hand once a month, on a morning when
  someone is at the server (`sudo reboot`).

### No sleeping, lid closed

A laptop must keep running with its lid shut and never go to sleep:

```bash
sudo mkdir -p /etc/systemd/logind.conf.d
printf '[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\nHandleLidSwitchDocked=ignore\n' \
  | sudo tee /etc/systemd/logind.conf.d/labra.conf
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
sudo systemctl restart systemd-logind
```

Put the laptop somewhere with air around it, not in a closed drawer. Lid closed, the keyboard
no longer cools it.

### A fixed address and the name `labra.lan`

The main-lab PCs find the server by its name, `labra.lan`, so its address must never change.

1. Find the server's address and network card: `ip -br addr` (for example `192.168.1.20`
   on `enp1s0`) and `ip link` (its MAC address, `aa:bb:cc:…`).
2. In the router's settings, under **DHCP** (*Address reservation*, *Static lease*), reserve
   that address for that MAC address.
3. If the router has a **local DNS** setting, add `labra.lan` → that address. Otherwise each
   main-lab PC gets a line in its hosts file (step 6).

**Check:** restart the server (`sudo reboot`); `ip -br addr` shows the same address.

## 4. Docker

Install Docker from Docker's own package source (Debian's own package is older):

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian trixie stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Sign out and in again, so that your user can use Docker without `sudo`.

There is nothing to set for the containers' logs: each of Labra's containers keeps at most
five files of 10 MB, so the logs can't fill the disk.

**Check:** `docker run --rm hello-world` prints *Hello from Docker!*. Docker starts by itself
when the server starts.

## 5. Labra

Get Labra into `/opt/labra`, at the newest release:

```bash
sudo mkdir -p /opt/labra && sudo chown "$USER": /opt/labra
git clone https://github.com/premdon009/labra.git /opt/labra
cd /opt/labra
git tag --sort=-v:refname | head -3       # the newest releases
git checkout v0.1.0                       # the newest one
```

Every command from here on runs in `/opt/labra`.

1. **Images.** Until the first release is published, build Labra's images on the server (15
   to 30 minutes): `docker compose --profile jobs build`. After that, `docker compose pull`
   fetches them instead.
2. **Secrets.** Make the database password and its connection string as in
   [Running the stack](../dev/running-the-stack.md#first-start), step 1. They stay in
   `/opt/labra/secrets`, readable only by your user; never copy them anywhere else.
3. **Start it,** then make the main lab and the first administrator:

   ```bash
   docker compose up -d
   scripts/labra.sh add-branch --code MAIN --name "Main lab" --kind main_lab
   docker compose exec web labra create-admin --username admin --full-name "Lab Admin"
   ```

   `create-admin` asks for the password twice. Use a strong one and give it to the owner.
   Add each collection centre with `add-branch --kind collection_centre` (its own code and
   name) the same way.

4. Make a second administrator for the lab manager later, on the Staff screen, so that one
   forgotten password never locks everyone out
   ([Forgotten administrator password](../runbooks/forgotten-admin-password.md)).

**Check:** `docker compose ps` lists `db`, `web` and `proxy` as running (`healthy`), and
`curl -sk --resolve labra.lan:443:127.0.0.1 https://labra.lan/healthz` prints
`{"status":"ok",…}`. `docker compose exec web labra check-config`
reports no problems.

Labra's containers start by themselves whenever the server starts.

## 6. The main-lab PCs

On each PC at the main lab:

1. If the router has no local DNS (step 3), open Notepad **as administrator**, open
   `C:\Windows\System32\drivers\etc\hosts`, and add a line with the server's address and the
   name: `192.168.1.20 labra.lan`. Save.
2. Install the server's certificate, so that the browser trusts `https://labra.lan`. Copy it
   off the server once, to a USB stick:

   ```bash
   docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./labra-root.crt
   ```

   then on the PC, follow [Certificate and tunnel renewal](../runbooks/certificate-and-tunnel.md)
   (*With Caddy*, installing the root certificate on a PC).
3. Open `https://labra.lan` in Chrome or Edge, sign in, and make it a shortcut on the desktop.
   Set up the printers: the label printer ([Sample labels and collection](../manual/frontdesk/labels.md))
   and the report printer ([Letterhead and margins](../manual/admin/letterhead-and-margins.md)).

**Check:** `https://labra.lan` opens with a padlock and no warning, on every PC.

## 7. Backups

Every 15 minutes in lab hours, Labra copies its database and stored files to Google Drive and
to the USB disk ([Backups and restore](../manual/admin/backups-and-restore.md)).

1. **The USB disk.** Plug it in and format it for Linux (this erases it):

   ```bash
   lsblk -o NAME,SIZE,MODEL           # find it, e.g. sdb, by its size
   sudo mkfs.ext4 -L labra-backup /dev/sdb1
   sudo mkdir -p /mnt/labra-backup
   echo 'LABEL=labra-backup /mnt/labra-backup ext4 defaults,nofail,x-systemd.device-timeout=10s 0 2' \
     | sudo tee -a /etc/fstab
   sudo mount /mnt/labra-backup
   ```

   If the disk has no partition yet (only `sdb`), make one first:
   `sudo parted /dev/sdb --script mklabel gpt mkpart labra ext4 0% 100%`. `nofail` lets the
   server start without the disk; the next backup then fails loudly, and the owner gets the
   alert.

2. **The rest** is on the [Backups and restore](../manual/admin/backups-and-restore.md) page,
   *Setting it up (once)*: the backup password (**write it on the envelope's paper too**),
   Google Drive, the `.env` lines, `scripts/backup.sh init`, the timers
   (`sudo scripts/install_timers.sh`) and the first backup.

**Check:** `scripts/backup.sh snapshots` lists the first backup, and `systemctl list-timers
'labra-*'` lists the backup, drill, audit, disk and watchdog timers with their next run.

## 8. Alerts

Follow [Alerts and nightly checks](../manual/admin/alerts-and-checks.md), *Setting up the alerts
(once)*. Do it after step 9 if the lab has branches, so that the watchdog checks the public
address.

**Check:** all five checks are green on healthchecks.io. Then stop the web app for ten minutes
(`docker compose stop web`): the owner gets the watchdog alert. Start it again
(`docker compose start web`).

## 9. Branches: Cloudflare Tunnel and Access

The branches reach Labra over the internet through Cloudflare Tunnel. The server makes an
outgoing connection to Cloudflare, so **the router needs no open ports** and the server's
address stays private. Cloudflare Access then lets in only the staff's email addresses, before
they ever see Labra's sign-in screen.

1. Add the lab's domain to Cloudflare (the free plan), and change its name servers at the
   registrar as Cloudflare asks. Turn on automatic renewal of the domain at the registrar.
2. **The tunnel.** In the Cloudflare dashboard, **Zero Trust ▸ Networks ▸ Tunnels ▸ Create a
   tunnel**, type *Cloudflared*, name `labra`. Copy the token from the install command it shows
   (the long string after `--token`); don't run that command.
3. Under the tunnel's **Public hostname**, add the lab's address (for example
   `labra.example-lab.in`), service type **HTTP**, URL `proxy:8080`.
4. On the server, add to `.env` beside `compose.yaml`:

   ```bash
   LABRA_TUNNEL_TOKEN=eyJ…
   COMPOSE_PROFILES=tunnel
   ```

   `COMPOSE_PROFILES` makes every `docker compose up -d` start the tunnel too. Start it:
   `docker compose up -d`. The tunnel shows **Healthy** in the dashboard within a minute.
5. **Access.** **Zero Trust ▸ Access ▸ Applications ▸ Add an application ▸ Self-hosted**, with
   the lab's address. Add two policies, in this order:
   1. *Health check*: action **Bypass**, include **Everyone**, on the path `/healthz` only (a
      second application for `labra.example-lab.in/healthz` if the dashboard asks for one).
      The watchdog uses it; the page shows nothing private.
   2. *Staff*: action **Allow**, include **Emails**, listing each branch member's email.
   Under **Settings ▸ Authentication**, use **One-time PIN**: staff get a code by email.
6. Set `LABRA_WATCHDOG_URL=https://labra.example-lab.in/healthz` in `.env` and run
   `docker compose up -d` (step 8).

Branch PCs then open `https://labra.example-lab.in`, type their email and the code, and sign in
to Labra as usual. Their certificate comes from Cloudflare, so they need no certificate step.

**Check, from a phone on mobile data (not the lab's Wi-Fi):**

- `https://labra.example-lab.in` asks for an email, and an email not on the list gets no code.
- `https://labra.example-lab.in/healthz` shows `{"status":"ok",…}` without asking.
- Nothing on the server is reachable from outside: the router's **Port forwarding** (or
  *Virtual server*, *NAT*) page is empty, and `https://<the lab's public IP address>` from the
  phone doesn't open. The database is never published at all; only the proxy's ports 80 and
  443 are, on the lab's own network.

To use Tailscale or NetBird instead, see [Running the stack](../dev/running-the-stack.md#branches).

## 10. Power: the UPS checklist

- [ ] The server, the router and the network switch are all on the UPS. A front-desk PC that
      must keep billing during a power cut is too.
- [ ] The UPS's battery lasts at least 30 minutes with that load. Test it: switch off the
      mains at the wall and time it, on a quiet afternoon.
- [ ] The BIOS starts the server when power returns (step 1), or the staff know to press the
      power button, and who types the passphrase if the TPM doesn't unlock it (step 2).
- [ ] The UPS's own beeping alarm is on, so that someone notices a power cut.
- [ ] The UPS battery's replacement date is written on it (usually every 2 to 3 years).

**Check, a full power cut:** with nobody using Labra, switch off the UPS itself. Switch it on
again. Within five minutes, without anyone touching the server (or after the passphrase only),
`https://labra.lan` opens on a main-lab PC and `docker compose ps` shows everything healthy.

## 11. The internet goes down

The main lab must keep working with no internet at all.

**Check:** on a quiet afternoon, unplug the router's internet cable (the WAN port, or the fibre
box's cable), not the cables to the PCs. Then, on a main-lab PC:

- [ ] `https://labra.lan` opens; make a test visit, enter a result, print a report.
- [ ] The branches can't reach Labra (expected); they carry on [on paper](../manual/troubleshooting/working-on-paper.md).
- [ ] Within ten minutes the owner gets the watchdog alert, once the alert service notices the
      missing pings.

Plug the cable back in. The tunnel reconnects by itself, the next backup copies everything to
Google Drive, and the checks turn green again. Cancel the test visit's bill afterwards
([Bills and receipts](../manual/frontdesk/bills-and-receipts.md)), with the reason *installation
test*.

## 12. Before the first patient

- [ ] A restore works: follow the drill in [Backups and restore](../manual/admin/backups-and-restore.md)
      (*The monthly check*) once by hand: `scripts/drill.sh`.
- [ ] The **System** page (Menu ▸ System) shows the last backup, drill and audit check as
      recent and green ([System](../manual/admin/system.md)).
- [ ] The envelope holds, on paper: the disk passphrase and how the disk unlocks, the backup
      password, the server's address, the first administrator's username, the Google account
      used for the backups, and where this guide and the
      [runbooks](../runbooks/laptop-dead.md) are. The owner keeps it somewhere safe, away from
      the server.
- [ ] The printed troubleshooting pages are at each front desk and in the lab
      ([Labra won't open](../manual/troubleshooting/labra-wont-open.md),
      [Working on paper](../manual/troubleshooting/working-on-paper.md)).
- [ ] The staff have their own usernames and roles ([Staff and roles](../manual/admin/users-and-roles.md)),
      and have walked through [A day at the lab](../manual/getting-started/a-day-at-the-lab.md)
      on a training copy.

## Rehearsals

Each time this guide is followed from start to end, add a row. A step that didn't work as
written is fixed in this guide in the same change.

| Date | Where | Result | Notes |
|---|---|---|---|
| 2026-10-21 | Debian 13.7 VM (2 CPU, 4 GB, a second 20 GB disk as the USB disk) | Steps 3–5 and 7 as written; a backup on its timer, the drill, both restores in the backup runbook, the System page, and a hard reset all worked | `parted` was missing from step 3, now added. Not rehearsed: steps 1–2 (BIOS, encryption, TPM), 6 (no second PC), 8–9 (need the lab's accounts), 10–11. Images were loaded rather than built, and the VM's containers had no internet throughout, so the main lab working offline was shown too. Since then step 4's `daemon.json` log cap has gone: `compose.yaml` caps each container's logs itself. |
