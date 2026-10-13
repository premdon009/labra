---
title: Calculated values
features: [M11.2]
---

# Calculated values

## What it's for

Some rows of a test are worked out from other rows, such as LDL cholesterol from total
cholesterol, HDL and triglycerides. Labra does the sum for you, so nobody needs a
calculator and the number can't be mistyped.

## Where to find it

**Menu ▸ Lab ▸ Worklist**, then click the patient's name. Calculated rows are marked
**(calc.)**.

## Steps

1. Enter the measured values of the test. See [Entering results](entering-results.md).
2. As soon as every value a calculated row needs is saved, Labra fills that row and
   flags it like any other.
3. If you correct a measured value, Labra works the calculated rows out again.

## Screenshot

<!-- screenshot: lab-calculated-values.png (taken with the demo data) -->

## Good to know

- A calculated row has no box. To change it, change the values it is built from.
- A calculated row stays empty until all its values are entered.
- **Not calculable, measure directly** means the formula doesn't hold for this patient.
  The usual case is LDL when triglycerides are 400 mg/dL or more. Measure the row
  directly and report it as its own test.
- A row built on a row that is not calculable is not calculable either.
- A division by zero also shows **Not calculable**.
- The sum is done on the server, with the rounding set for the row in the test catalog.
- An administrator sets the formulas under **Menu ▸ Test catalog**.

## Related pages

- [Entering results](entering-results.md)
- [Test catalog](../admin/catalog.md)
