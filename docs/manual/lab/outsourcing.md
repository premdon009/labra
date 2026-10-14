---
title: Outsourcing
features: [M10, M21, M09]
---

# Outsourcing

## What it's for

Some tests are done by an outside lab. This screen lists the tests waiting to go, prints
the sheet that travels with the samples, records when a sample left, and shows what is
still with an outside lab and when it is due back.

## Where to find it

**Menu ▸ Lab ▸ Outsourcing**. The result PDF is attached on the result screen of the
visit, under **Results from outside labs**.

## Steps

### Sending samples

1. Under **To send**, click the lab's name next to **Sheet to go with the samples**.
2. Press **Print** and put the sheet in the bag with the samples.
3. When the samples have left, come back to **To send**.
4. If the outside lab gave its own number for a sample, type it in **Their number**.
5. Press **Mark sent** for each test. It moves to **With an outside lab**.

### Attaching the result

1. Under **With an outside lab**, click **Attach the result** for the patient.
2. Under **Results from outside labs**, tick the tests the PDF is the result of.
3. Choose the PDF in **Result PDF** and press **Attach the PDF**.
4. If you want the value on the report, type it in the test's row.
5. Press **Submit for verification**. A signatory then verifies the test as usual.

### Moving a test to an outside lab

1. Under **Could go to an outside lab**, pick the lab in **Done at**.
2. Press **Move the test**. It moves to **To send**.

## Screenshot

<!-- screenshot: lab-outsourcing.png (taken with the demo data) -->

## Good to know

- A test can be marked sent only after its sample is collected.
- The sheet lists the sample number, the container, the patient's name, age and sex, the
  test and the outside lab's own code for it. It has the phone number or the address only
  if the lab is set up to be given them. See [External labs](../admin/external-labs.md).
- **Late** means the test is past the time it was due back.
- **Their number** can be corrected while the test is with the outside lab.
- Once a test is marked sent, its bill can't be cancelled, because the outside lab will
  charge for it.
- Only a PDF is accepted, up to 20 MB. A file of another kind is refused even if its name
  ends in `.pdf`.
- Labra never shows the PDF inside the page. **Result PDF** downloads it, under a name
  Labra gives it.
- The same file can't be attached twice to one visit. A corrected PDF can be added until
  the test is verified; the earlier one is kept.
- A value can be typed only after the PDF is attached. Typing it is optional: the test can
  be submitted with the PDF alone.
- **Timeline**, under each test, lists what happened to it, when and who did it:
  registered, sample collected, routed, sent, result received, submitted, verified, then
  report released and report handed over (see [Handing over
  reports](../reports/delivery.md)).
- **Could go to an outside lab** shows at most 25 tests, the most urgent first.
- Staff who route tests but don't enter results, such as an administrator, see the lists
  and can move and send tests. Only staff who enter results at the lab that does the test
  can attach a PDF.
- The screen shows the patient's name, age and sex, never the phone number or address.

## Related pages

- [Entering results](entering-results.md)
- [Lab worklist](worklist.md)
- [External labs](../admin/external-labs.md)
- [Receiving samples](receiving-samples.md)
