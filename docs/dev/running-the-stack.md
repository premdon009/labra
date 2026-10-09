---
items: [W03, W16]
---

# Running the stack

`compose.yaml` runs Labra on one small server at the main lab: the web app, Postgres 18 and
Caddy, plus cloudflared for branches. It's sized for a 4 GB laptop
([design §1a](../design/v1-plan.md)).

| Service | What it does | Reachable from |
|---|---|---|
| `db` | Postgres, data checksums on, tuned for 4 GB | `web` only (internal network) |
| `migrate` | runs `labra migrate` once, then exits | — |
| `web` | the app, 2 workers, on port 8000 | Caddy |
| `caddy` | HTTPS for the LAN on 443; port 8080 for the tunnel | main-lab PCs |
| `tunnel` | cloudflared, under the `tunnel` profile | branches, through Cloudflare |

## First start
1. Create the two secrets. They stay on the server and are never committed (`secrets/` is
   ignored by git):
   ```sh
   mkdir -p secrets && chmod 700 secrets
   # Hex, so the password needs no escaping inside the URL.
   openssl rand -hex 24 | tr -d '\n' > secrets/db_password
   printf 'postgresql+psycopg://labra:%s@db:5432/labra' "$(cat secrets/db_password)" \
     > secrets/database_url
   chmod 600 secrets/*
   # The web image runs as user 10001, and Compose mounts secret files with their owner.
   sudo chown 10001 secrets/database_url
   ```
2. Start it, then create the first branch and administrator:
   ```sh
   docker compose up -d
   docker compose exec web labra add-branch --code MAIN --name "Main lab" --kind main_lab
   docker compose exec web labra create-admin --username admin --full-name "Lab Admin"
   ```
3. On each main-lab PC, point `labra.lan` at the server (router DNS or the hosts file) and
   install Caddy's root certificate once, from the `caddy_data` volume
   (`/data/caddy/pki/authorities/local/root.crt` inside the container).

For branches, create a tunnel in Cloudflare, point its public hostname at
`http://caddy:8080`, then:
```sh
LABRA_TUNNEL_TOKEN=<token> docker compose --profile tunnel up -d
```

## Settings
Process settings are `LABRA_*` environment variables ([Developer setup](setup.md)). The ones
Compose passes through:

| Variable | Default | Meaning |
|---|---|---|
| `LABRA_IMAGE` | the release's exact version | image to run |
| `LABRA_SITE` | `labra.lan` | LAN host name Caddy serves |
| `LABRA_HEARTBEAT` | `log` | `http` to ping a monitor such as Healthchecks.io |
| `LABRA_MAILER` | `console` | `smtp` to send mail |

Anything else, such as the heartbeat URLs (`LABRA_HEARTBEAT_URL_<JOB>`) or
`LABRA_SMTP_URL_FILE` with its secret, goes in the `x-labra` block at the top of
`compose.yaml`. Run `docker compose exec web labra check-config` after changing them.

## Health and metrics
- `/healthz`: the process is up. The image's own health check uses it.
- `/readyz`: database reachable, migrations at head, and enough free disk for the files
  folder. Compose waits for it before starting Caddy.
- `/metrics`: Prometheus format, only from inside the stack or with `LABRA_METRICS_TOKEN`.
  Caddy answers 404 for it, so it is never exposed through the LAN or the tunnel.
