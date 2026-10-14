---
title: Branches
features: [M02, M02.1, M12.1, EC-F03]
---

# Branches

## What it's for

A branch is a place that works with Labra: the main lab, where tests are run, and the
collection centres that send it samples. Every visit, bill and sample belongs to a branch.

## Where to find it

**Menu ▸ Branches**. Everyone sees the branches they work at. Only an administrator can add
or change branches.

## Steps

To add a branch:

1. Select **Add branch**.
2. Fill in the **Code**: 1 to 4 capital letters or digits, such as `B2`. It is printed at the
   start of bill and visit numbers, so keep it short.
3. Fill in the **Name** and choose the **Type**: main lab or collection centre.
4. Add the address, GST state code, phone, email and GSTIN if the branch has them.
   If the branch is accredited, add its **NABL certificate number**.
5. Select **Save**. You are given your administrator role at the new branch, so it shows in
   your list straight away. Give other staff a role there from **Users and roles**.

To change a branch, select **Edit** on its row, change the fields, and select **Save**. To
close a branch, untick **Active**: its records stay, but no new work can be added there.

## Screenshot

<!-- screenshot: admin-branches.png (taken with the demo data) -->

## Good to know

- Long lists show 25 rows at a time. Use **Previous** and **Next** under the list to move
  through them; a search or filter you chose stays in place.
- There can be only one main lab.
- Two branches can't share a code.
- The NABL certificate number is kept in capitals. It prints on a report only when every
  test on that report is in your NABL scope, which you set on each test in the
  [Test catalog](catalog.md).
- Bill and invoice numbers can be at most 16 characters (GST rules). A four-letter code
  leaves less room for the rest of the number than a two-letter one.
- If you change a branch's code and one of its numbers would no longer fit, Labra doesn't
  save and says which number. Use a shorter code, or change that number's format under
  **Numbering** first.
- If someone else saved the same branch while you were editing it, Labra refuses your save
  and asks you to reload, so neither change is lost silently.
- Every change is recorded in the audit log with who made it and when.

## Related pages

- [Staff and roles](users-and-roles.md)
- [Settings](settings.md)
