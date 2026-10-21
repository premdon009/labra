---
items: [EC-L03, EC-D07]
---

# Internet down at a branch

Use this when a collection centre can't open Labra. The main lab keeps working on its own
network whatever happens to the internet; only the branches, the Google Drive copy of the
backups and the alerts need it.

## Find where the break is

Ask the branch, then check from the main lab:

| Check | If it fails |
|---|---|
| At the branch: does any website open (for example a news site)? | The branch's own internet is down. [Keep the branch working](#keep-the-branch-working) and call its internet provider. |
| At the main lab: does Labra open on a main-lab PC (`https://labra.lan`)? | The server itself is down, not the internet: [Laptop dead or won't start](laptop-dead.md). |
| At the main lab: does any website open? | The main lab's internet is down, so **every** branch is cut off. Call the provider. The watchdog alert has probably already come. |
| On the server: is the tunnel running? (below) | Start it again (below). |

On the server, in the folder where Labra is installed:

```bash
docker compose --profile tunnel ps tunnel        # STATUS should say "Up"
docker compose --profile tunnel logs --tail 30 tunnel
```

- Not running: `docker compose --profile tunnel up -d`.
- The log says `Unauthorized` or `Invalid tunnel secret`: the tunnel's token was changed in
  Cloudflare. Follow [Certificate and tunnel renewal](certificate-and-tunnel.md#the-tunnel-stopped-working).
- The log shows it connecting again and again: Cloudflare can't be reached from the lab. Check
  the main lab's internet, and Cloudflare's status page.

If the branch reaches the sign-in page of Cloudflare Access but the email code never comes,
check the spam folder, and that the person's email is still in the Access policy
([Certificate and tunnel renewal](certificate-and-tunnel.md#cloudflare-access)).

## Keep the branch working

- **A phone's hotspot** is the quickest fix: connect the branch PC to it and open Labra as
  usual. Cloudflare Access may ask for the email code again. Use the same Labra address;
  nothing on the server changes.
- **On paper** if there is no hotspot: [Working on paper](../manual/troubleshooting/working-on-paper.md).
  Patients still give samples and pay; bills and results are entered once the line is back.
- The branch can't print reports while it is cut off. Released reports can be printed at the
  main lab and sent with the courier, or the main lab can download the **PDF to send** and
  email it or send it on WhatsApp ([Print or send](../manual/reports/print-vs-digital.md)).

## When the main lab's internet is down

The main lab keeps working: the server, the PCs and the printers all talk over the lab's own
network ([EC-D07](../ENTERPRISE_CHECKLIST.md)). Meanwhile:

- the Google Drive copy of each backup fails and an alert would be sent; the USB copy is still
  made, so the 15-minute target holds;
- no alerts can leave the lab, so Healthchecks.io notices the missing pings and sends the
  backup and watchdog alerts itself. They are expected and clear when the line returns.

When the line returns, the tunnel connects again by itself within a minute or two, and the
next backup sends everything that changed to Google Drive. Check on Healthchecks.io that the
checks are green again, and ask each branch to open Labra.

## Afterwards

- The branch enters its paper records ([Working on paper](../manual/troubleshooting/working-on-paper.md#afterwards)).
- If the main lab's line fails often, a second connection (a 4G router as a fallback on the
  main router) keeps the branches working. It needs no change in Labra.
