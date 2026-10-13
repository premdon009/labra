---
title: Entering results
features: [M11, M11.1]
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
- A test that is verified can't be changed. A signatory must reopen it first.
- If someone else changed the same value while you were typing, Labra says so and shows
  the newer value. Type yours again if it is still right.
- The screen shows the patient's name, age and sex, never the phone number or address.
- Tests of the same visit that another branch does are listed at the bottom as **Done at
  another branch**.

## Related pages

- [Lab worklist](worklist.md)
- [Calculated values](calculated-values.md)
- [Reference ranges](../admin/reference-ranges.md)
- [Keyboard shortcuts](../getting-started/keyboard-shortcuts.md)
