---
items: [EC-L03, EC-A11]
---

# Certificate and tunnel renewal

Labra is reached two ways, and each has something that can run out:

| Who | How they reach Labra | What can run out |
|---|---|---|
| Main-lab PCs | `https://labra.lan` on the lab's network, with the server's own HTTPS certificate | the certificate (Caddy renews its own; one made by hand for nginx lasts about two years) |
| Branches | the lab's public address, through Cloudflare Tunnel and Cloudflare Access | the tunnel's token (only if someone changes it), the lab's domain name (renewed yearly), who is allowed in |

The [System](../manual/admin/system.md) page shows the certificate's expiry. The watchdog
alert ([Alerts and nightly checks](../manual/admin/alerts-and-checks.md)) comes when the
public address stops answering.

## The certificate on the lab's network

### With Caddy (the usual setup)

Caddy runs its own small certificate authority on the server. It makes a certificate for
`labra.lan` that lasts 12 hours and renews it by itself, so there is nothing to do on a
schedule. Its root certificate, which each main-lab PC trusts, lasts 10 years.

| What happens | What to do |
|---|---|
| The System page shows the certificate in red | Renewal has stopped. Restart the proxy: `docker compose restart proxy`, then reload the System page. |
| One PC says *Your connection is not private* and the others don't | That PC doesn't trust the lab's root yet (a new or reinstalled PC). Install the root certificate on it (below). |
| Every PC says it, after a restore onto a new server | The new server has a new root. Install it on every PC (below). |

To install the root certificate on a main-lab PC:

1. On the server, copy it out of the proxy:

   ```bash
   docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./labra-root.crt
   ```

2. Copy `labra-root.crt` to the PC (a USB stick is fine; it isn't secret).
3. On Windows: double-click it, **Install Certificate**, **Local Machine**, **Place all
   certificates in the following store**, **Trusted Root Certification Authorities**,
   **Finish**. Close and reopen the browser.

### With nginx

A certificate made by hand for nginx (as in [Running the stack](../dev/running-the-stack.md#nginx-instead-of-caddy))
lasts 825 days. The System page counts only certificates from Caddy's own authority as
renewing by themselves, so it turns red 30 days before this one runs out, whatever its
lifetime. To renew it:

1. Make a new one, in the folder where Labra is installed:

   ```bash
   openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=labra.lan" \
     -addext "subjectAltName=DNS:labra.lan" \
     -keyout secrets/tls/labra.key -out secrets/tls/labra.crt
   chmod 644 secrets/tls/labra.crt
   docker compose -f compose.yaml -f deploy/nginx/compose.nginx.yaml restart proxy
   ```

2. Install the new `secrets/tls/labra.crt` on every main-lab PC, as for Caddy's root above.
   Until a PC has it, that PC shows *Your connection is not private*.

## The tunnel for the branches

The tunnel runs on the server as the `tunnel` service and connects out to Cloudflare, so the
lab's router has no open ports. Branch staff sign in through Cloudflare Access with a code
sent to their email.

### The tunnel stopped working

Check it on the server:

```bash
docker compose --profile tunnel ps tunnel
docker compose --profile tunnel logs --tail 30 tunnel
```

| The log says | What to do |
|---|---|
| `Unauthorized`, `Invalid tunnel secret`, or the token is refused | The token was changed or the tunnel deleted. Get the token (below) and start it again. |
| It connects again and again, or `no such host` | The lab's internet or Cloudflare is down: [Internet down at a branch](branch-internet-down.md). |
| Nothing wrong, but branches see a Cloudflare error page (`1033`, `502`) | The tunnel is up but can't reach Labra. Check `docker compose ps proxy web`, and that the tunnel's public hostname points at `http://proxy:8080`. |

To get the token and start the tunnel again:

1. In the Cloudflare dashboard, **Zero Trust ▸ Networks ▸ Tunnels**, open the lab's tunnel.
   Copy the token from the install command it shows (the long string after `--token`). To
   replace a token that may have leaked, use **Refresh token** first.
2. On the server, put it in `.env` beside `compose.yaml`, replacing the old line:

   ```bash
   LABRA_TUNNEL_TOKEN=eyJ…
   ```

3. Start it: `docker compose --profile tunnel up -d`. The tunnel shows **Healthy** in the
   dashboard within a minute, and a branch can open Labra again.

### The domain name

The lab's public address (for example `labra.example-lab.in`) is a domain the lab pays for
every year. If it lapses, the branches can't reach Labra, even though nothing on the server
changed. Turn on automatic renewal at the registrar, and keep the card on file current. The
owner's email gets the renewal reminders.

### Cloudflare Access

Cloudflare Access decides who may open the public address at all, before Labra's own sign-in.

- **A new branch member:** add their email to the Access application's policy (**Zero Trust
  ▸ Access ▸ Applications**, the Labra application, **Policies**). Then add them in Labra
  ([Staff and roles](../manual/admin/users-and-roles.md)).
- **Someone leaves:** remove their email from the policy, and untick **Still works here**
  in Labra.
- **The email code doesn't arrive:** check the spam folder and the spelling of the email in
  the policy.
- **The watchdog alert comes, but branches can open Labra:** the bypass rule for `/healthz`
  is missing or was changed. The policy must let `/healthz` through without signing in
  ([install guide](../install/laptop.md#9-branches-cloudflare-tunnel-and-access)).

### Tailscale or NetBird instead

If the lab uses Tailscale, its machine keys expire after 180 days by default and the server
drops off the tailnet. In the admin console, open the `labra` machine and choose **Disable
key expiry**. With NetBird, check the setup key and the peer's login expiry the same way.
