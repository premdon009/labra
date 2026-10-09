---
title: Settings
features: [W04]
---

# Settings

## What it's for

Settings change how Labra behaves for your lab, such as the lab name and the usual
turnaround time. Some apply to the whole lab; some can be different at each branch.

## Where to find it

**Menu ▸ Settings**. Administrators and branch managers see it. Others can't open it.

## Steps

1. Change the values you need. The **Applies to** column says whether a value is for the
   whole lab or for the branch you are working at.
2. Select **Save**. Values that aren't allowed are shown in red with the reason, and the
   others are saved.

## Screenshot

<!-- screenshot: admin-settings.png (taken with the demo data) -->

## Good to know

| Setting | Applies to | Allowed values |
|---|---|---|
| Lab name on screens | Whole lab | Any text; starts as "Labra Diagnostics" |
| GST state code of the main lab | Whole lab | The two-digit code from the GSTIN, such as `29` |
| Default turnaround time (hours) | Each branch | 1 to 720; starts at 24 |
| Footer printed on receipts | Each branch | Any text, up to 500 characters |

- A branch value overrides the whole-lab value at that branch. Branches without their own
  value use the whole-lab one.
- Administrators can change every setting. Branch managers can change only the
  per-branch settings, and only at their own branch.
- To change a branch's setting, first [switch](../getting-started/screen-layout.md) to that
  branch.
- Every change is recorded in the audit log with the old and new value.

## Related pages

- [Branches](branches.md)
