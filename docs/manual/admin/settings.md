---
title: Settings
features: [W04, M02, M07, M07.1, M07.5, EC-C01, M12, M17, M20]
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
2. Select **Save**. Values that aren't allowed are shown in red with the reason, and
   nothing is saved until they are fixed.

## Screenshot

<!-- screenshot: admin-settings.png (taken with the demo data) -->

## Good to know

| Setting | Applies to | Allowed values |
|---|---|---|
| Lab name on screens | Whole lab | Any text; starts as "Labra Diagnostics" |
| GST state code of the main lab | Whole lab | The two-digit code from the GSTIN, such as `29`, or empty. Bills from a branch without its own code print this one as the place of supply |
| Default turnaround time (hours) | Each branch | 1 to 720; starts at 24 |
| Footer printed on receipts | Each branch | Any text, up to 500 characters |
| Legal name printed on bills | Whole lab | Up to 120 characters. Leave empty to print the lab name |
| SAC code printed on bill lines | Whole lab | 4 to 8 digits; starts as `999316` |
| Exemption note printed on bills | Whole lab | Up to 200 characters |
| Scan samples in when they reach the lab | Whole lab | Only samples from another branch (the start value), every sample, or never. See [Receiving samples](../lab/receiving-samples.md) |
| Reports for a visit with outsourced tests | Whole lab | One report with every test (the start value), or the lab's own report plus one for each outside lab document |
| Reference interval column on reports | Whole lab | Show it (the start value) or hide it |
| Web address the report QR code points to | Whole lab | An `https://` address without a trailing slash, up to 120 characters. Leave it empty and the QR code carries the report number and a check code instead |
| Footer printed on reports | Whole lab | Up to 200 characters |
| Resolution for picture letterheads | Whole lab | 150 to 200 dots per inch; starts at 150 |
| What the Print button makes | Each branch | A PDF for pre-printed letterhead paper, without the letterhead (the start value), or a PDF with the letterhead on it |
| Printer offset right / down (mm) | Each branch | −10 to 10; starts at 0. Moves everything on the printed copy to make up for a printer that doesn't print exactly where it should. A negative value moves it left or up |

- A branch value overrides the whole-lab value at that branch. Branches without their own
  value use the whole-lab one.
- If an open branch has no GST state code of its own and the main lab's is empty, the top
  of the page says **Bills from B2 will print no place of supply** (naming each such branch
  you can see). Bills are still made, with the place of supply left empty. Set the code
  here, or the branch's own on [Branches](branches.md), and the notice goes.
- Administrators can change every setting. Branch managers can change only the
  per-branch settings, and only at their own branch.
- To change a branch's setting, first [switch](../getting-started/screen-layout.md) to that
  branch.
- Every change is recorded in the audit log with the old and new value.
- The legal name, SAC code and exemption note are printed on new bills only. A bill that
  is already issued keeps what it was printed with.
- Report settings apply to reports released after the change. A report that is already
  released keeps what it was released with.
- The printer offset applies only to the Print copy, never to the PDF that is downloaded
  or sent.
- The SAC code and the exemption note start with common values for diagnostic labs. Ask
  your accountant to confirm them for your lab.

## Number formats

Select **Number formats** at the top of the page to see how each branch numbers its
patients, visits, bills, receipts, refunds, samples and reports, and the next number in
each.
Administrators can change a format; branch managers can only look.

| Part | Becomes | Example |
|---|---|---|
| `{BR}` | The branch code | `B2` |
| `{FY2}` | The financial year, four digits | `2627` for April 2026 to March 2027 |
| `{FY}` | The financial year, long form | `2026-27` |
| `{SEQ:5}` | The running number, padded to 5 digits (any width from 1 to 9) | `00123` |

- A new branch gets the standard formats as soon as it is added, for example bill numbers
  like `B2/2627/00001`, patient numbers like `B2/P/000001` and report numbers like
  `B2/R/2627/000001`.
- A report's later versions keep its number; the version is printed beside it, as in
  `B2/R/2627/000001 v2`.
- Numbers with `{FY2}` or `{FY}` in them start again from 1 on 1 April. Numbers without
  the year, such as patient numbers, never start again, so they never repeat.
- Bill numbers can be at most 16 characters and may use only letters, digits, `-` and `/`,
  as GST rules require. A format that could go past that is refused with the reason.
- Changing a format doesn't change the running number: the next bill carries on from the
  last one.
- If someone else changed the same format while you were editing, Labra asks you to
  reload instead of overwriting their change.

## Consent notice

Select **Consent notice** at the top of the page to see the words a patient agrees to
before their samples are tested or sent to a referral lab. Administrators can change them;
branch managers can only look.

1. Change the text under **What the patient agrees to**.
2. Select **Publish as version N**. The new wording applies from that moment.

- Old wording is never changed or removed. Each consent the front desk records keeps
  pointing at the exact version the patient saw.
- After a new version, patients tick consent again at their next visit.
- A new lab starts with placeholder wording. Replace it with your own before the first
  visit.
- If someone else published a version while you were editing, Labra asks you to reload.

## Related pages

- [Branches](branches.md)
- [Currency](currency.md): how amounts look, and what bill totals are rounded to.
