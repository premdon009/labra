---
title: Find or register a patient
features: [M03, EC-F03]
---

# Find or register a patient

## What it's for

Look up a patient who has come before, or register a new one. Each patient gets a patient
number that stays with them for every later visit.

## Where to find it

**Menu ▸ Patients**, or press **Alt+F** on any screen. Front desk staff, branch managers and administrators see it.

## Steps

To find a patient:

1. Type in **Phone, patient number or name** and select **Find**.
   - A phone number, or just its first digits, finds patients by either of their phones.
   - The end of a patient number, such as `P/000123`, finds that patient.
   - A name finds close spellings too: `Sunita` also finds `Suneeta`.
2. With nothing typed, the list shows the newest registrations first.

To register a patient:

1. Select **Register patient**.
2. Fill in the **Full name** and choose the **Sex**.
3. Enter the **Date of birth**. If the patient doesn't know it, leave it empty and fill in
   the age in **Years**, **Months** and **Days** instead; Labra works out a date of birth
   from it and marks the age as *about*.
4. Add the **Phone** as 10 digits, without +91, and any other details the patient gives.
5. Select **Save**, or press **Alt+S**. Labra gives the next patient number of your branch and shows the patient
   in the list.

To change a patient's details, select **Edit** on their row, change the fields, and select
**Save**.

## Screenshot

<!-- screenshot: frontdesk-find-patient.png (taken with the demo data) -->

## Good to know

- You see the patients who registered at, or visited, a branch you work at. Other
  branches' patients are not shown.
- If the phone number and a similar name are already registered, Labra stops and shows the
  patient it found. Select that patient to use the existing record, or select **Register
  as a new patient** if this is a different person, such as a family member sharing a
  phone.
- When the matching patient belongs to a branch you don't work at, Labra only says that
  one may exist; it shows none of their details.
- A date of birth can't be in the future or more than 150 years ago.
- Phone numbers are 10 digits starting with 6, 7, 8 or 9. A PIN code is 6 digits.
- If someone else saved the same patient while you were editing, Labra refuses your save
  and asks you to reload, so neither change is lost silently.
- Registrations and changes are recorded in the audit log. The log names the fields that
  changed, never the patient's details.
- Long lists show 25 rows at a time. Use **Previous** and **Next** under the list to move
  through them; a search you typed stays in place.

## Related pages

- [New visit](new-visit.md)
- [Referrers](referrers.md)
- [Staff and roles](../admin/users-and-roles.md)
