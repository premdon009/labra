---
title: Bills and receipts
features: [M07, M07.1, M07.4, M17, M23, M26, EC-B05, EC-J03]
---

# Bills and receipts

## What it's for

See a visit with its bill, print the bill and its receipts again, look through the bills
of any day, and cancel a bill that was made by mistake.

## Where to find it

**Menu ▸ Bills** lists the bills of your branch, newest first. Selecting a bill number
opens the visit it belongs to. Front desk staff, branch managers and administrators see
it. Only branch managers and administrators can cancel a bill.

## Steps

To find a bill:

1. Open **Bills**.
2. Set **From** and **To** for the days you want, or choose a **Status**: **Due**, **Paid**
   or **Cancelled**. Select **Show**.
3. Select the bill number to open the visit.

To print a bill again:

1. On the visit, select **Print bill and receipt**, or press **Alt+R**. From the list,
   select **Print** on the bill's row.
2. The bill opens ready to print, with a receipt for each payment under it.
   Straight after a new visit, the [sample labels](labels.md) open to print next.
3. To print one receipt on its own, select **Print receipt** on its row under
   **Payments**.

To get the bill as a PDF:

1. On the visit, select **PDF to print** for paper that already has your letterhead
   printed on it, or **PDF to send** for a copy with the letterhead on it, to share or
   print on plain paper. From the list, **PDF** on the bill's row opens the copy to send.
2. The PDF opens in a new tab. Use the browser's print or download button there.

To cancel a bill:

1. On the visit, select **Cancel bill**.
2. Type the **Reason for cancelling**.
3. If money was already paid, choose how it is given back in **Money paid back by**, and
   add the **Refund reference** if there is one.
4. Tick **Yes, cancel this bill** and select **Cancel the bill**.

## Screenshot

<!-- screenshot: frontdesk-bills-and-receipts.png (taken with the demo data) -->

## Good to know

- The printed bill is a **Bill of Supply**. Diagnostic services are exempt from GST, so
  the bill shows no tax. It carries the lab's name, address and GSTIN, the bill number and
  date, the patient, each service with its SAC code, the amount after discount, and a
  place for the authorised signatory.
- Bill numbers run in order for each branch and financial year, such as `B2/2627/00042`.
  A number is never used twice and never skipped.
- A bill can't be changed after it is saved. To correct one, cancel it and make a new
  visit.
- Cancelling can't be undone. It cancels the visit, its tests and the samples not yet in
  the lab. A cancelled bill keeps its number and prints with **CANCELLED** across it.
- A bill can't be cancelled once one of its tests was sent to an outside lab or has a
  result. Labra shows **This bill can't be cancelled** instead of the form.
- Cancelling a bill that was paid gives **all** the money back, and the refund is recorded
  with its own number. Giving back only a part is not possible yet.
- A printed bill always shows what was true on the day it was made: the lab's name, the
  currency and the wording, even if an administrator has changed them since.
- The bill PDF uses your branch's [bill letterhead and margins](../admin/letterhead-and-margins.md).
  A reprint uses the letterhead that was published when the bill was made, even if it has
  been changed since. Until a letterhead is set, the PDF has plain margins and the bill's
  own heading.
- **PDF to print** leaves the letterhead off and moves the text by your branch's printer
  offset, so it lands inside the frame of the printed paper. An administrator can make it
  include the letterhead instead, in **Settings ▸ What the Print button makes**.
- Amounts print with the currency symbol and commas the way your lab has set them, such as
  `₹1,23,456.00`.
- The printed page has no menu and no buttons. Use **Back to the visit** on the screen to
  return.
- Bills, payments, cancellations and refunds are recorded in the audit log.
- Long lists show 25 rows at a time. Use **Previous** and **Next** under the list; the
  dates and status you chose stay in place.

## Related pages

- [New visit](new-visit.md)
- [Dues and payments](dues-and-payments.md)
- [Currency](../admin/currency.md)
- [Letterhead and margins](../admin/letterhead-and-margins.md)
