---
title: Changing my password
features: [M27]
---

# Changing my password

## What it's for

Anyone who signs in can change their own password, for example the first time they sign in
with a password an administrator gave them, or when they think someone else knows it.

## Where to find it

Select **Password** at the top right of any screen, next to your name.

## Steps

1. Type your **Current password**.
2. Type the **New password**, then type it again in **New password again**.
3. Select **Change password**. Labra says *Your password is changed.*

From then on, sign in with the new password. You stay signed in on this computer; on every
other computer where you were signed in, you are signed out and have to sign in again with
the new password.

## Screenshot

<!-- screenshot: getting-started-change-password.png (taken with the demo data) -->

## Good to know

- **"That isn't your current password."** A wrong current password counts as a failed
  sign-in. After 5 of them from the same computer within 15 minutes, both this page and the
  sign-in screen refuse that username on that computer for 15 minutes, as in
  [Signing in](login.md).
- The new password needs at least 10 characters, common ones are refused, and it must
  differ from the current one.
- If you have forgotten your password, this page can't help: ask an administrator to give you
  a new one ([Staff and roles](../admin/users-and-roles.md)), then change it here.
- Every change is in the audit log as `user.password_change`.

## Related pages

- [Signing in](login.md)
- [Sign-in problems](../troubleshooting/sign-in-problems.md)
