---
items: [EC-L03]
---

# Forgotten administrator password

Use this when an administrator can't sign in. It takes a few minutes. Nothing in the lab's
data changes except that person's password.

## Pick the case

| What the sign-in screen says | Go to |
|---|---|
| "Too many failed attempts. Wait 15 minutes, or ask an administrator." | [Locked out](#locked-out) |
| "Wrong username or password." and another administrator can sign in | [Another administrator resets it](#another-administrator-resets-it) |
| "Wrong username or password." and nobody else is an administrator | [At the server](#at-the-server) |

## Locked out

Five wrong passwords in a row lock that username on that PC for 15 minutes. Other PCs and
other users are not affected.

1. Wait 15 minutes, then try once more, carefully. Check Caps Lock and the keyboard layout.
2. If the password is really forgotten, go on to the next case.

## Another administrator resets it

1. The other administrator opens **Menu ▸ Staff and roles** and selects **Edit** on the
   person's row.
2. They type a **New password** of at least 10 characters and select **Save**. The person is
   signed out everywhere.
3. The person signs in with the new password, then changes it to one only they know: **Edit**
   on their own row, a **New password**, **Save**. That signs them out too; they sign in again
   with it.

## At the server

When the only administrator has forgotten their password, set a new one on the server
itself. You need to be able to sign in to the server (its own keyboard, or `ssh` from a
main-lab PC) as the account that runs Labra.

1. Go to the folder where Labra is installed, for example `cd /opt/labra`.
2. Set the new password. It asks for it twice and doesn't show it:

   ```bash
   docker compose exec web labra set-password --username admin
   ```

   Use the username shown on the Staff screen (often `admin`). It ends with
   `Password changed for admin. They are signed out everywhere.`
3. Sign in on a PC with the new password. If the sign-in screen still says "Too many failed
   attempts", wait 15 minutes.
4. Make a second administrator account for the owner, so this isn't needed again
   ([Staff and roles](../manual/admin/users-and-roles.md)).

What the messages mean:

| The command says | What to do |
|---|---|
| `There is no user …` | Check the spelling. `docker compose exec db psql -U labra -c "select username, full_name from app_user where can_login"` lists the usernames that can sign in. |
| `… can't sign in at all (switched off on the Staff screen)` | Someone switched off that person's sign-in. Use another administrator, or make a new one with `docker compose exec web labra create-admin --username owner2 --full-name "…"`. |
| `Use at least 10 characters.` or `This password is too common.` | Run it again with a longer or less common password. |
| `service "web" is not running` | Start Labra first: `docker compose up -d`. |

Every password change, at the server or on the Staff screen, is in the audit log as
`user.password_reset`.
