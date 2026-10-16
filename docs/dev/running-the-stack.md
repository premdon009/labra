---
items: [W03, W16, W17, W19, W07, EC-D05, EC-B06, EC-E02]
---

# Running the stack

`compose.yaml` runs Labra on one small server at the main lab: the web app, Postgres 18 and a
reverse proxy (Caddy, or nginx), plus a tunnel for branches. It's sized for a 4 GB laptop
([design §1a](../design/v1-plan.md)). The commands below say `docker compose`; `podman compose`
and `nerdctl compose` take the same arguments ([Container runtimes](runtimes.md)).

| Service | What it does | Reachable from |
|---|---|---|
| `db` | Postgres, data checksums on, tuned for 4 GB | `web` only (internal network) |
| `migrate` | runs `labra migrate` once (waits up to 60 s for Postgres), then exits | — |
| `web` | the app, 2 workers, on port 8000 | the proxy |
| `proxy` | HTTPS for the LAN on 443; port 8080 for the tunnel | main-lab PCs |
| `tunnel` | cloudflared, under the `tunnel` profile | branches, through Cloudflare |
| `tailscale` | Tailscale or Headscale, under the `tailscale` profile | branches, over the tailnet |
| `netbird` | NetBird, cloud or self-hosted, under the `netbird` profile | branches, over NetBird |

## First start
1. Create the two secrets. They stay on the server and are never committed (`secrets/` is
   ignored by git):
   ```sh
   mkdir -p secrets && chmod 700 secrets
   # Hex, so the password needs no escaping inside the URL.
   openssl rand -hex 24 | tr -d '\n' > secrets/db_password
   printf 'postgresql+psycopg://labra:%s@db:5432/labra' "$(cat secrets/db_password)" \
     > secrets/database_url
   chmod 600 secrets/db_password
   # The app reads this one as its own user, whose number on the host differs between
   # runtimes (rootless ones remap it). The 0700 directory is what keeps it private.
   chmod 644 secrets/database_url
   ```
   To keep secrets elsewhere, set `LABRA_SECRETS_DIR`.
2. Start it, then create the first branch and administrator:
   ```sh
   docker compose up -d
   docker compose exec web labra add-branch --code MAIN --name "Main lab" --kind main_lab
   docker compose exec web labra create-admin --username admin --full-name "Lab Admin"
   ```
3. On each main-lab PC, point `labra.lan` at the server (router DNS or the hosts file) and
   install Caddy's root certificate once, from the `caddy_data` volume
   (`/data/caddy/pki/authorities/local/root.crt` inside the container).

`scripts/stack_smoke.sh` does all of this with throwaway secrets and ports, checks the result
end to end, and removes it again.

## nginx instead of Caddy
nginx doesn't make its own certificates, so create one first (or use the lab's own CA):
```sh
mkdir -m 700 secrets/tls
openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=labra.lan" \
  -addext "subjectAltName=DNS:labra.lan" \
  -keyout secrets/tls/labra.key -out secrets/tls/labra.crt
chmod 644 secrets/tls/labra.crt
docker compose -f compose.yaml -f deploy/nginx/compose.nginx.yaml up -d
```
Install `labra.crt` on the main-lab PCs instead of Caddy's root. The headers, the `/metrics`
block and the tunnel port are the same; the app sets its own security headers, so either proxy
gives the same result.

## Branches
Pick one. Each reaches the proxy, so branches get the same HTTPS site as the LAN.

- **Cloudflare Tunnel:** create a tunnel, point its public hostname at `http://proxy:8080`, then
  `LABRA_TUNNEL_TOKEN=<token> docker compose --profile tunnel up -d`.
- **Tailscale:** create an auth key, then
  `LABRA_TAILSCALE_AUTHKEY=<key> docker compose --profile tailscale up -d`. Branch PCs on the
  tailnet open `https://labra.lan` once `labra.lan` points at the `labra` machine in the
  tailnet's DNS. For self-hosted Headscale add
  `LABRA_TAILSCALE_ARGS=--login-server=https://<your headscale>`. It runs in userspace, so it
  needs no extra privileges.
- **NetBird:** create a setup key, then
  `LABRA_NETBIRD_SETUP_KEY=<key> docker compose --profile netbird up -d`. For a self-hosted
  control plane set `LABRA_NETBIRD_MANAGEMENT_URL`. It shares the proxy's network and needs
  `/dev/net/tun` and `NET_ADMIN`.
- **WireGuard** from a small VPS is the fallback with no third party at all
  ([design §19.2](../design/v1-plan.md)).

Without a key, `tailscale` and `netbird` start and wait, printing a login link in their logs.

## Settings
Process settings are `LABRA_*` environment variables ([Developer setup](setup.md)). The ones
Compose passes through:

| Variable | Default | Meaning |
|---|---|---|
| `LABRA_IMAGE` | the release's exact version | image to run |
| `LABRA_SITE` | `labra.lan` | LAN host name the proxy serves |
| `LABRA_HEARTBEAT` | `log` | `http` to ping a monitor such as Healthchecks.io |
| `LABRA_MAILER` | `console` | `smtp` to send mail |
| `LABRA_SECRETS_DIR` | `./secrets` | where the secret files are |
| `LABRA_HTTP_PORT`, `LABRA_HTTPS_PORT` | `80`, `443` | published ports (rootless runtimes: see [Container runtimes](runtimes.md)) |
| `LABRA_EDGE_SUBNET` | `172.30.0.0/24` | the proxy network; the app trusts forwarded addresses only from it |
| `LABRA_HEARTBEAT_URL_<JOB>` | empty | a monitor's ping address per job: `BACKUP`, `DRILL`, `AUDIT_VERIFY`, `DISK`, `WATCHDOG` |
| `LABRA_WATCHDOG_URL` | `http://web:8000/healthz` | what the watchdog fetches; the public address checks the tunnel too |

Anything else, such as the `LABRA_SMTP_URL_FILE` secret, goes in the `x-labra` block at the
top of `compose.yaml`. Run `docker compose exec web labra check-config` after changing them.

## Exports

`labra export accounting` and `labra export all` write to the `exports` volume, mounted at
`/data/export` (`LABRA_EXPORT_DIR`). They hold patient data: copy them off the server only to
an encrypted disk, and never into a folder the proxy serves. For example:

```bash
docker compose exec web labra export accounting --date 2026-10-14 --as admin
docker compose cp web:/data/export ./export-copy
```

The [Data export](../manual/admin/data-export.md) page of the manual explains the files.

## Backups
The `backup` service ([ADR-0013](../adr/0013-backup-runner.md)) sits under the `jobs` profile,
so `up -d` never starts it. `scripts/backup.sh` runs one job in it, one at a time:

```bash
scripts/backup.sh init        # create the repositories (once)
scripts/backup.sh backup      # one backup: pg_dump + /data/files into every repository
scripts/backup.sh snapshots   # list them
scripts/drill.sh              # the monthly drill: each repository into a scratch database
scripts/restore.sh [--from usb|drive] [--replace] [SNAPSHOT]   # put the data back
sudo scripts/install_timers.sh --dry-run   # the systemd timers it would install
```

It needs two more secrets beside `database_url`, both mode 0644 inside the 0700 folder,
because the job runs as uid 10001 like the app:

- `restic_password`: the repository password. Keep a paper copy; without it no backup opens.
- `rclone.conf`: an rclone config with a remote named `drive`. For a test, `[drive]` with
  `type = local` stores the "Drive" repository on a local path.

`LABRA_BACKUP_REPO_DRIVE` (for example `rclone:drive:labra-backup`) and
`LABRA_BACKUP_REPO_USB` (`/backup/usb/labra`, the host's `LABRA_BACKUP_USB_DIR` inside the
container) choose the repositories; leave one empty to skip it. Each run adds a row to
`ops_run` and pings `LABRA_HEARTBEAT_URL_BACKUP` (the drill: `LABRA_HEARTBEAT_URL_DRILL`).

`restore.sh` stops `web`, runs the job in the `restore` service (the same image, with the files
volume writable) and starts the stack again. The load is one `psql -1` transaction, and every
table's row count is checked against the dump's `COPY` blocks. It refuses a database that
already has tables unless `--replace` is given. The drill restores into `labra_drill`, a name
the job insists ends in `_drill`, and runs `labra audit verify --database labra_drill` from the
web image.

`scripts/stack_smoke.sh` takes real backups into both kinds of repository and one with the USB
disk missing, then runs the drill, a refused restore, a `--replace` restore and a drill of a
damaged repository. The [Backups and restore](../manual/admin/backups-and-restore.md) page is the
administrator's guide; [Restore from backup](../runbooks/restore-from-backup.md) is the runbook.

### Nightly checks and the watchdog

`install_timers.sh` also installs three checks:

```bash
scripts/labra.sh audit verify   # 02:30 nightly: the audit hash chain, logged as kind verify
scripts/labra.sh check-disk     # hourly: fails at 80% used (--percent N to change it)
scripts/watchdog.sh             # every 5 minutes: fetches /healthz, pings only when it answers ok
```

`labra.sh` runs any `labra` command in the running `web` container. The watchdog runs in the
backup image without the backup lock, and fetches `LABRA_WATCHDOG_URL` (default
`http://web:8000/healthz`; set it to the public address so the tunnel is checked too). Each
check pings `LABRA_HEARTBEAT_URL_AUDIT_VERIFY`, `_DISK` or `_WATCHDOG` when
`LABRA_HEARTBEAT=http`. An empty URL means "not set". The administrator's guide is
[Alerts and nightly checks](../manual/admin/alerts-and-checks.md).

## Health and metrics
- `/healthz`: the process is up. The image's own health check uses it.
- `/readyz`: database reachable, migrations at head, enough free disk for the files folder.
  Compose waits for it before starting the proxy.
- `/metrics`: Prometheus format, only from inside the stack or with `LABRA_METRICS_TOKEN`.
  The proxy answers 404 for it, so it's never exposed through the LAN or a tunnel.
