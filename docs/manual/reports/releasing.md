---
title: Releasing reports
features: [M12, M12.1, M20]
---

# Releasing reports

## What it's for

This screen shows the report a signatory is about to issue for one visit: which tests it
carries, which are still pending, and a preview of the PDF exactly as the patient will get
it.

## Where to find it

**Menu ▸ Lab ▸ Worklist**, open the visit, then press **Report** at the top. Only a
signatory sees the button, once at least one test of the visit is verified.

## Steps

1. Read **Signed off, ready to report**: the verified tests done at your branch.
2. Read **Pending**: the visit's tests not yet verified. They print at the end of the
   report as pending, with the time each is expected, and the report is marked **PARTIAL
   REPORT**.
3. Under **Preview**, choose:
    - **Paper**: A4 or A5.
    - **Reference interval column**: show or hide it.
    - **Tests**: tick some to preview a report with only those tests. None ticked means
      all.
4. Press **Open the preview**. The PDF opens in a new tab.

## Screenshot

<!-- screenshot: reports-releasing.png (taken with the demo data) -->

## What the report shows

- At the top of every page: the patient's name, patient number, age and sex, the
  referring doctor, when the sample was collected (and at which branch), received and
  reported, and a barcode of the visit number.
- Tests grouped by department, in the order set in the [catalog](../admin/catalog.md).
  Each test has its specimen, sample number and method in its heading, then the columns
  **Test**, **Result**, **Flag**, **Unit** and **Bio. ref. interval**.
- Values outside the interval are in bold with their flag (L, H, LL, HH or A). There is no
  colour, so the report reads the same on a black-and-white printer.
- Rows worked out by Labra are marked **(calc.)**. A text answer such as a Widal titre uses
  the full width of the row.
- Where a test has bands (such as cholesterol risk levels), they are listed once under it,
  with the band this result falls in.
- Sample remarks print above the test, and a critical value prints the line "informed to …
  at …".
- A test done by an outside lab is marked **\***, with the lab's name, its NABL number and
  their accession number at the end.
- A test for research use is marked **†**, with a note that it is not for diagnosis.
- The lab's NABL certificate number prints only when every test on the report is in the
  scope of a NABL-accredited branch.
- The signatory's name, qualification, registration number and signature are on the last
  page only, followed by **End of report**.
- Every page ends with the report number, the version and **Page x of y**.

## Good to know

- The preview says **PREVIEW: not released, not for the patient** at the top and
  **Preview, not released** on every page. Nothing is saved or numbered.
- A test that doesn't fit on the page moves to the next one whole. A long test that is
  bigger than a page starts where it is and carries on under its name marked
  **(continued)**.
- A5 always uses the plain header with the lab name and address, inside smaller margins.
  A4 uses the branch's published [letterhead](../admin/letterhead-and-margins.md).
- Tests done at a branch where you aren't a signatory are not on your report.
- Front desk staff and technicians can't open this screen.

## Related pages

- [Entering results](../lab/entering-results.md)
- [Letterhead and margins](../admin/letterhead-and-margins.md)
- [Catalog](../admin/catalog.md)
- [Users and roles](../admin/users-and-roles.md)
