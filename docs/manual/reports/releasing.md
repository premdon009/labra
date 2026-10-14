---
title: Releasing reports
features: [M12, M12.1, M20]
---

# Releasing reports

## What it's for

A signatory releases a visit's report here: the screen lists which tests the report
carries, which are still pending, and lets you preview the PDF before you release it.
Releasing gives the report its number, stores the PDF exactly as released and marks the
tests released. The **Reports** screen lists the visits waiting for a release and the
released reports not yet handed over.

## Where to find it

- **Menu ▸ Reports** lists:
    - **To release** (signatories only): visits with verified tests not yet on a report,
      the longest waiting first. Press **Release** to open the visit.
    - **Released, not yet handed over**: the current version of each report nobody has
      handed over yet, newest first, with **Open the PDF**.
- Or **Menu ▸ Lab ▸ Worklist**, open the visit, then press **Report** at the top. Only a
  signatory sees the button, once at least one test of the visit is verified.

Front desk staff, technicians, branch managers and admins see **Menu ▸ Reports** with the
released list only.

## Steps

1. Read the heading **Release B2/R/2627/000001 v1**: the number and version the report will
   get. A first release shows the next free number; if another report is released first,
   yours gets the one after.
2. Read the lists:
    - **New on this version**: the verified tests done at your branch.
    - **Carried over from v1** (from the second version on): every test already on the
      report. They stay on it.
    - **Pending**: the visit's other tests. They print at the end of the report with the
      time each is expected, and the report is marked **PARTIAL REPORT**.
3. If you want to check the PDF first, use **Preview** (see below).
4. Tick **Yes, release B2/R/2627/000001 v1** and press **Release B2/R/2627/000001 v1**.
5. The screen comes back with the version under **Released versions**. Press **Open the
   PDF** to see the stored copy.

### Preview

Under **Preview**, choose:

- **Paper**: A4 or A5.
- **Reference interval column**: show or hide it.
- **Tests**: tick some to preview a report with only those tests. None ticked means all.

Press **Open the preview**. The PDF opens in a new tab. Nothing is saved or numbered.

## Screenshot

<!-- screenshot: reports-releasing.png (taken with the demo data) -->

## Versions

A visit has one report number. When more tests are verified after a release, the next
release is a new version of the same number, such as **v2**, carrying every test of v1
and the new ones. v1 is then **Superseded**; its PDF is kept and still opens from
**Released versions**, but only the current version is listed for handing over.

A released version can't be changed or deleted, by anyone.

## The QR code

The last page has a QR code beside the signature.

- When **Web address the report QR code points to** is set in
  [Settings](../admin/settings.md), the code opens a public page on that address. Anyone holding the paper can see the lab's name, the report
  number, the version, when it was issued, and whether it is still the current version.
  It shows nothing about the patient or the results, and needs no sign-in.
- Without the address, the code holds the report number, the version and a fingerprint of
  the report's contents, which the lab can compare with its stored copy.

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
  page only, with the QR code, followed by **End of report**.
- Every page ends with the report number, the version and **Page x of y**.

## Good to know

- **The release is refused** while a value was saved against no reference range because
  the range for this patient was waiting for approval. The screen names the test and the
  parameter: approve the range in the [catalog](../admin/catalog.md), reopen the test,
  save the value again and verify it.
- If another signatory released or verified something while you were reading, the release
  is refused with "The tests waiting to be reported have changed". Reload and check the
  lists again.
- The preview says **PREVIEW: not released, not for the patient** at the top and
  **Preview, not released** on every page.
- A test that doesn't fit on the page moves to the next one whole. A long test that is
  bigger than a page starts where it is and carries on under its name marked
  **(continued)**.
- A5 always uses the plain header with the lab name and address, inside smaller margins.
  A4 uses the branch's published [letterhead](../admin/letterhead-and-margins.md). A
  released report keeps the letterhead it was released with.
- Tests done at a branch where you aren't a signatory are not on your report; they stay
  pending until a signatory there releases the next version.

## Related pages

- [Entering results](../lab/entering-results.md)
- [Letterhead and margins](../admin/letterhead-and-margins.md)
- [Catalog](../admin/catalog.md)
- [Settings](../admin/settings.md)
- [Users and roles](../admin/users-and-roles.md)
