---
title: Amended reports
features: [M12]
---

# Amended reports

## What it's for

When a value on a released report turns out to be wrong, a signatory reopens the test,
corrects it and releases the report again. The new version says on its first page that it
is an amended report, which version it replaces and why each test was corrected. The old
version is kept as it was released.

## Where to find it

- **Menu ▸ Lab ▸ Worklist**, open the visit: a released test shows **Reopen** to a
  signatory, with the note "This test is on a released report".
- Then **Report** at the top of the visit, which opens [Releasing
  reports](releasing.md).

## Steps

1. On the visit in the lab, type the reason in **Reason for reopening** under the test and
   press **Reopen**. Write the reason for the patient and the doctor to read, such as
   "Typing slip in cholesterol": it prints on the report.
2. The test goes back to **Resulted**. Until it is verified again, the release screen
   lists it under **Pending**, and the rest of the report stays as released.
3. Correct the value, submit the test and verify it again.
4. Open **Report**. The test is listed under **Corrected on this version**, with your
   reason.
5. Tick **Yes, release B2/R/2627/000001 v2 as an amended report** and press **Release
   B2/R/2627/000001 v2**.

## Screenshot

<!-- screenshot: reports-amended.png (taken with the demo data) -->

## What the amended report shows

- A box at the top of the first page: **AMENDED REPORT: supersedes v1**, then one line per
  corrected test with its reason, such as "Lipid profile: Typing slip in cholesterol".
- Every test of the report, the corrected ones with their new values.
- The same report number as before, with the next version.

## Good to know

- The old version becomes **Superseded**. Its PDF still opens from **Released versions**
  on the release screen, so you can see what was handed over before. It can't be changed
  or deleted.
- A new version that only adds tests verified later is not an amended report; it has no
  box.
- If several tests are reopened before the next release, the box lists each of them.
- The reason is kept with the test's history; it is not sent anywhere outside Labra.
- For an outside lab's report released on its own (see [Releasing
  reports](releasing.md#outside-lab-results)), reopening a test on it makes the next
  version of that report amended too. Its box names the corrected tests; the outside
  lab's own pages carry their correction.

## Related pages

- [Releasing reports](releasing.md)
- [Entering results](../lab/entering-results.md)
