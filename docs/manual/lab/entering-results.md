---
title: Entering results
features: [M11, M11.1, M09, M10, M21, M12.1, M20, M12]
---

# Entering results

## What it's for

This screen holds every test of one visit that your lab does. You type each value once.
Labra saves it, compares it with the reference interval, and marks it normal, low, high
or critical.

## Where to find it

**Menu ▸ Lab ▸ Worklist**, then click the patient's name.

## Steps

1. Click the first **Result** box of the test.
2. Type the value and press **Enter**. Labra saves the value and moves to the next box.
3. For a row with a list, such as urine protein, pick the answer from the list.
4. Read the **Flag** column and the colour of the row:

    | Mark | Meaning |
    |---|---|
    | ✓ | Inside the reference interval |
    | ↓ L | Below the interval |
    | ↑ H | Above the interval |
    | ⚠ LL or ⚠ HH | Critical: far outside the interval |
    | A | An abnormal answer on a list or text row |

5. To go back one box, press **Shift+Enter**. To drop what you have just typed and keep
   the saved value, press **Esc**.
6. To correct a saved value, type over it and press **Enter**.
7. When the test is ready, press **Submit for verification** under its rows.

### Verifying

Only a signatory sees these buttons.

1. Open the visit from the worklist. The line under each test says how many values are
   critical, high, low, abnormal and missing.
2. Read the values, then press **Verify**.
3. To correct a verified or released test, type the reason in **Reason for reopening**
   and press **Reopen**. Correct the value, submit the test and verify it again. A
   released test then goes out on the next version of its report, marked amended with
   your reason. See [Amended reports](../reports/amended.md).
4. To see the report these tests make, press **Report** at the top. See [Releasing
   reports](../reports/releasing.md).

### Sample remarks and method

1. To note something about the sample that the report should show, such as "Mildly
   haemolysed", type it in **Sample … remarks** above the test's rows and press **Save
   remarks**. It prints above the panels of every test from that sample.
2. If the test can be run by more than one method, pick the one used in **Method** and
   press **Use this method**. The report names it under the test's heading. The method
   marked **(usual)** is the test's default.

### Choosing where a test is done

1. In **Done at**, above the test's rows, pick your own lab, the branch that took the
   sample, or an outside lab.
2. Type a reason if you want one kept.
3. Press **Move the test**.

## Screenshot

<!-- screenshot: lab-entering-results.png (taken with the demo data) -->

## Good to know

- There is no Save button. A value is saved when you leave its box.
- Every mark has a letter or sign as well as a colour, so it reads the same on a
  black-and-white screen.
- **Previous** shows the patient's last verified value for the same row, its date and
  the change in percent.
- If a value is far outside anything a person can have, Labra refuses it and asks you to
  look again. A wrong decimal point is the usual cause. If the value is right, press
  **Save … anyway**. Labra records that you confirmed it.
- Type numbers as plain digits, such as `180` or `4.5`. A row that takes whole numbers
  refuses `4.5`.
- **Range not approved** means a signatory has not yet approved the reference interval.
  The value is saved without a flag.
- Rows marked **(calc.)** are worked out by Labra and can't be typed. See
  [Calculated values](calculated-values.md).
- You can submit a test with rows still empty. The line under the test counts them as
  missing.
- If a value is changed after the test was submitted, the test goes back to **In the
  lab**. Submit it again.
- A critical value can't be submitted or verified until you record who was informed. See
  [Critical values](critical-values.md).
- A test that is verified or released can't be changed. A signatory must reopen it first.
  Labra keeps each value as it was before the correction, with the reason.
- An administrator can't verify. Verifying needs the signatory role.
- Each outside lab in **Done at** shows what it charges, the margin left from what the
  patient paid for the test, and its turnaround time in hours. The cheapest lab is first.
  For a test inside a package, the margin uses the test's share of the package price.
- A test can be moved until it has a result. After that the list is gone.
- Sample remarks are shared by all tests on the same sample, so a change under one test
  shows under the others too. Remarks and the method can be changed until the test is
  verified. Changing the method of a submitted test sends it back to **In the lab**.
- The method list appears only for a test with more than one method. Methods are kept in
  [Methods and comment presets](../admin/methods.md).
- A test that goes to an outside lab takes no value until the lab's PDF is attached under
  **Results from outside labs**. See [Outsourcing](outsourcing.md).
- **Timeline**, under each test, lists what happened to it, when and who did it.
- If the patient hasn't agreed to their details going to an outside lab, Labra shows
  **No consent to share with an outside lab**. Ask the patient, then press **Record
  consent**. The warning doesn't stop you moving the test.
- If someone else changed the same value while you were typing, Labra says so and shows
  the newer value. Type yours again if it is still right.
- The screen shows the patient's name, age and sex, never the phone number or address.
- Tests of the same visit that another branch does are listed at the bottom as **Done at
  another branch**.

## Related pages

- [Lab worklist](worklist.md)
- [Releasing reports](../reports/releasing.md)
- [Amended reports](../reports/amended.md)
- [Critical values](critical-values.md)
- [Outsourcing](outsourcing.md)
- [Calculated values](calculated-values.md)
- [External labs](../admin/external-labs.md)
- [Reference ranges](../admin/reference-ranges.md)
- [Keyboard shortcuts](../getting-started/keyboard-shortcuts.md)
