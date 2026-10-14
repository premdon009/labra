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
    - **Released, not yet handed over**: the current version of each report not handed
      over yet, newest first. Press **Print or hand over** to open the report's own screen
      (see [Handing over reports](delivery.md)).
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
5. The screen comes back with the version under **Released versions**. Press **Open** to
   see the report's own screen, where you can open the stored copy with **PDF to send**.

### Preview

Under **Preview**, choose the paper, the reference interval column and the tests (see
[Report options](options.md)), then press **Open the preview**. The PDF opens in a new tab.
Nothing is saved or numbered.

## Outside lab results

When the visit has a test done by an outside lab, the screen shows **Outside lab results**
with a choice of how that lab's work reaches the patient. Choose before the first release
and press **Save the choice**; after the first release it stays as it is.

- **One report with every test** (the lab's setting, unless changed in
  [Settings](../admin/settings.md)). The outside test is on the same report as the rest.
  If its values were typed in, they print like any other test. If only the outside lab's
  PDF was attached, the test reads "See the attached report from …", and the PDF's pages
  follow the last page of the report.
- **This lab's own report, plus each outside lab's PDF as a report of its own**. The
  report carries this lab's tests and lists the outside ones under "Reported separately
  by the outside lab". Each outside PDF appears under **Outside lab reports**:
    1. Once every test on that PDF is verified, tick **Yes, release this lab's report under
       a new number** and press **Release the … report**.
    2. It gets the next report number: a cover page headed **Outside laboratory report**
       with the patient and the tests, then the outside lab's pages.
    3. If the outside lab sends a corrected PDF later, a signatory reopens its tests with
       a reason, then the corrected PDF is attached, the tests are verified again, and the
       release makes it the next version of that number, marked amended.

    A PDF still waiting for its tests to be verified says how many are left. A test whose
    PDF hasn't come yet is listed under **Waiting for the outside lab's PDF**.

Labra copies only the pages of an outside PDF. Links, scripts, forms and files attached
inside it are left out, so the report opens the same everywhere.

## Corrections

To correct a released test, a signatory reopens it in the lab with a reason. The next
release lists it under **Corrected on this version** and is marked amended. See [Amended
reports](amended.md).

## Screenshot

<!-- screenshot: reports-releasing.png (taken with the demo data) -->

## Versions

A visit has one report number. When more tests are verified after a release, the next
release is a new version of the same number, such as **v2**, carrying every test of v1
and the new ones. v1 is then **Superseded**; its PDF is kept and still opens from
**Released versions**, but only the current version is listed for handing over, and it is
listed again even if v1 was handed over.

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
- **An outside PDF with a password can't be added.** The release says so; ask the outside
  lab for a copy without a password, attach it to the tests, and release again. A PDF
  that only stops printing or copying is fine.
- The pages of an outside PDF keep their own look and page numbers; **Page x of y** at the
  bottom counts this lab's pages only.
- Tests done at a branch where you aren't a signatory are not on your report; they stay
  pending until a signatory there releases the next version.

## Related pages

- [Handing over reports](delivery.md)
- [Report options](options.md)
- [Amended reports](amended.md)
- [Entering results](../lab/entering-results.md)
- [Outsourcing](../lab/outsourcing.md)
- [Letterhead and margins](../admin/letterhead-and-margins.md)
- [Catalog](../admin/catalog.md)
- [Settings](../admin/settings.md)
- [Users and roles](../admin/users-and-roles.md)
