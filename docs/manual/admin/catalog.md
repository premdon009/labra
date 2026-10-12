---
title: Test catalog
features: [M05, M05.1, M14, EC-F03]
---

# Test catalog

## What it's for

The test catalog lists every test and package the lab offers: its code, name, department,
specimen and the parameters a result is entered for. The front desk finds tests by their code,
and reports print what is set here.

## Where to find it

**Menu ▸ Test catalog**. Everyone can look at it. Only an administrator can change it.

The links at the top of the page lead to **Packages**, **Departments and specimens**,
**Ranges to approve** and **Comment presets**.

## Steps

To find a test, type part of its code, another code or its name in **Find**, or pick a
**Department**, then select **Show**.

To add a test:

1. Select **Add test**.
2. Fill in **Code**: what the front desk types, in small letters, for example `hb`. Codes must
   be unique across tests and packages.
3. Fill in **Name** as it should print on the report, and choose the **Department**.
4. Add **Other codes** that should also find the test, separated by spaces, for example
   `hgb haemo`.
5. Choose the **Specimen**, the usual **Turnaround (hours)**, and the **Interpretation** text to
   print under the results, if any.
6. Select **Save**. The test opens again, ready for its parameters.

To add a parameter (one line of the result, such as Haemoglobin or HDL cholesterol):

1. Open the test and select **Add parameter**.
2. Fill in **Code** (used in formulas, for example `HDL`) and **Name**.
3. Choose the **Result type**:
   - **Number**: choose the **Unit** and the **Decimal places**.
   - **Choice**: type each choice under **Choices**, tick the ones that are abnormal and pick
     the default.
   - **Text**: optionally say what the text must look like, for example `^\d{2,3}/\d{2,3}$`
     for a blood pressure such as 120/80.
   - **Calculated**: write the **Formula** from the other parameter codes of the same test, for
     example `TC - HDL - TG / 5`, and, if needed, **Calculate only when**, for example
     `TG < 400`.
4. Set the **Order on the report** and select **Save**.

To add a department or a specimen type, open **Departments and specimens**, fill in the row at
the bottom of the table and select **Add department** or **Add specimen type**. To change one,
edit its row and select **Save** on that row.

To add a package (tests billed together, such as `fbs+ppbs`), open **Packages**, select
**Add package**, fill in **Code** and **Name**, tick the tests in it and select **Save**.

## Screenshot

<!-- screenshot: admin-catalog.png (taken with demo data) -->

## Good to know

- Long lists show 25 rows at a time. Use **Previous** and **Next** under the list to move
  through them; a search or filter you chose stays in place.
- A test or package that is no longer offered is switched off, not deleted: untick **Test is
  in use**. Old visits and reports keep showing it.
- Another code can't be used by two tests or by a test and a package.
- A formula can use `+ - * /`, `**` for powers, brackets, and `min`, `max`, `abs`, `ln` and
  `log10`. It can only use parameters of the same test, and can't depend on itself through
  another formula. If an input is missing, or the **Calculate only when** rule doesn't hold,
  no value is calculated.
- Units are chosen from a list, so every report prints them the same way.
- If someone else saved the same test while you were editing it, Labra refuses your save and
  says who changed it and when. Reload, then make your change again.
- Every change is recorded in the audit log with the old and new values.

## Related pages

- [Reference ranges](reference-ranges.md)
- [Methods and comment presets](methods.md)
- [Prices](prices.md)
- [Starter catalog](starter-catalog.md)
