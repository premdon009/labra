---
title: Staff and roles
features: [M01, M01.1, M01.2, M12, M12.1, EC-F03]
---

# Staff and roles

## What it's for

Add the people who work at your lab, decide who can sign in, and give each person roles at
the branches where they work. Roles decide what they can see and do.

## Where to find it

**Menu ▸ Staff and roles**. Only an administrator sees it.

## Steps

To add a person:

1. Select **Add staff**.
2. Fill in the **Full name** and a **Username** (small letters, digits, dot, dash or
   underscore).
3. Leave **Signs in to Labra** ticked if they will use Labra, and give them a
   **Password** of at least 10 characters. Untick it for staff who only appear on records,
   such as home-collection phlebotomists.
4. For a signatory, fill in **Qualification** (for example MD (Pathology)) and the
   **Medical council registration number** under **On reports**. Both print under their
   name on the reports they release.
5. In the **Roles** table, tick each role they have at each branch.
6. Select **Save**.

To add a signatory's signature:

1. Open the person with **Edit**. The **Signature** section is under the form.
2. Choose a PNG or JPEG picture of the signature, up to 5 MB, and select **Upload**.
3. Check the picture shown. To change it, upload another one. To take it off, select
   **Remove the signature**.

To change someone, select **Edit** on their row. To reset a password, type a **New
password** and save; they are signed out everywhere. When someone leaves, untick **Still
works here**. Their name stays on the records they made.

## Screenshot

<!-- screenshot: admin-users-and-roles.png (taken with the demo data) -->

## Good to know

| Role | What it allows |
|---|---|
| Administrator | Everything, at every branch: branches, staff, settings, audit log |
| Branch manager | Everything front desk can do, plus cancel bills, see the branch and its settings, and change the per-branch settings |
| Front desk | Find and register patients, keep the referrer list, book visits, print labels, mark samples as collected, see bills and take payments |
| Phlebotomist | Mark samples as collected |
| Technician | Work at the branch |
| Signatory | Work at the branch |

- Roles count only at the branch they are ticked for. A front-desk user at Branch 2 can't
  see Branch 3 at all.
- Technician and signatory gain their own screens as Labra grows.
- You can't switch off your own sign-in, so a lab is never left without an administrator.
- For the best signature, sign in dark ink on plain white paper and photograph or scan it
  close up. A PNG with a clear background prints best on a letterhead.
- Labra makes a new PNG of at most 600 by 200 pixels from the picture's pixels alone. The
  camera details and anything else stored in the file are left out. A file that is not
  really a PNG or JPEG is refused, whatever its name says.
- A signatory without a signature can still release reports. The report shows the name,
  qualification and registration number without the signature.
- Every change is recorded in the audit log.
- Long lists show 25 rows at a time. Use **Previous** and **Next** under the list to move
  through them; a search or filter you chose stays in place.

## Related pages

- [Signing in](../getting-started/login.md)
- [Branches](branches.md)
