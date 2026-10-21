---
title: Labra won't open
features: [EC-L03, EC-D07, EC-E03]
---

# Labra won't open

## What it's for

What to do when Labra doesn't open, is very slow, or shows an error, and who to tell. Staff
can do the first checks themselves; the administrator does the rest from the runbooks.

## Where to find it

This page is also in the printed manual. Keep a printed copy at each front desk, because
while Labra is down its help pages are down too.

## Steps

1. Try another screen in Labra, then reload the page (**F5**).
2. Ask a colleague on another PC at the same place whether Labra opens for them.
   - **It opens for them:** the problem is your PC. Restart the browser, then the PC. Check
     the network cable or Wi-Fi.
   - **It doesn't open for anyone here:** go on.
3. Check where it fails, and tell the administrator what you found:

   | Where you are | What you see | What it usually means |
   |---|---|---|
   | Main lab | The page doesn't load at all | The server is off or Labra stopped. [Laptop dead or won't start](../../runbooks/laptop-dead.md) |
   | Main lab | *Your connection is not private* on one PC only | That PC doesn't trust the lab's certificate yet ([Certificate and tunnel renewal](../../runbooks/certificate-and-tunnel.md)) |
   | Branch | No website opens, not only Labra | The branch's internet is down ([Internet down at a branch](../../runbooks/branch-internet-down.md)) |
   | Branch | Other websites open, Labra doesn't | The main lab's internet or the tunnel is down. The main lab still works. |
   | Branch | The email code to sign in never arrives | Check the spam folder; the administrator checks your email is allowed in |
   | Anywhere | A page with *Reference: E-…* | Labra hit an error. Note the reference and what you were doing. |

4. If Labra is down for more than a few minutes, carry on [on paper](working-on-paper.md).

## Screenshot

There is no screen to show.

## Good to know

- An error reference such as `E-7F3K9Q2M` lets the administrator find exactly what happened:
  `docker compose logs web | grep E-7F3K9Q2M` on the server. Give it with the time and the
  patient or visit number you were working on.
- The main lab doesn't need the internet. When the internet is down, the main lab keeps
  working; only the branches, the Google Drive backup and the alerts wait for it.
- The administrator usually knows already: the watchdog alert goes to the owner when Labra
  can't be reached ([Alerts and nightly checks](../admin/alerts-and-checks.md)).
- Problems signing in, such as a forgotten password, are on [Sign-in problems](sign-in-problems.md).

## Related pages

- [Sign-in problems](sign-in-problems.md)
- [Working on paper](working-on-paper.md)
- [System](../admin/system.md)
