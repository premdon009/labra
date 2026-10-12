---
title: Reference ranges
features: [M05.2, EC-F03]
---

# Reference ranges

## What it's for

A reference range is the normal range printed next to a result, and the limits Labra uses to
mark a result high, low or critical. A parameter can have different ranges by sex, age or
condition, such as pregnancy.

## Where to find it

Open a test in the **Test catalog**, open a number or calculated parameter, and look under
**Reference ranges**. Ranges still waiting for approval are listed on
**Test catalog ▸ Ranges to approve**.

An administrator adds and changes ranges. Only a signatory can approve them.

## Steps

To add a range:

1. On the parameter, select **Add range**.
2. Choose **Sex**, or leave it as **Any**.
3. Fill in **Age from** and **Age up to** in years, months or days. Leave **Age up to** empty
   for no upper limit. An age of 18 years up to (but not including) 60 years covers someone
   on their 18th birthday but not on their 60th.
4. Choose a **Condition** if the range is only for one, for example the first trimester of
   pregnancy.
5. Fill in **Normal from** and **Normal up to**. One of them can stay empty, for example for
   "up to 200".
6. Optionally fill in **Critical below** and **Critical above**, the limits beyond which a
   result is critical, and **Impossible below** and **Impossible above**, beyond which a value
   can only be a typing mistake.
7. Fill in **Printed as** only if the report should print something other than the limits.
8. Fill in **Source**: where the limits come from, such as the kit insert or a guideline.
9. For results read in tiers, such as cholesterol (desirable, borderline, high), fill in the
   **Interpretation tiers**: a label, a severity and the limits of each tier.
10. Select **Save**.

To approve ranges (signatory):

1. Open **Test catalog ▸ Ranges to approve**.
2. Check each range against its **Source**. **Open** shows the full range and its tiers.
3. Select **Approve** on the row, or **Approve this range** on the range itself.

## Screenshot

<!-- screenshot: admin-reference-ranges.png (taken with demo data) -->

## Good to know

- Long lists show 25 rows at a time. Use **Previous** and **Next** under the list to move
  through them; a search or filter you chose stays in place.
- A new range, and any change to a range or its tiers, waits for a signatory's approval. The
  catalog shows how many ranges are waiting.
- Two ranges in use for the same sex and condition can't share an age, so it is always clear
  which one applies to a patient. One range may end at the age where the next one starts.
- The limits must be in order: impossible outside critical, critical outside normal.
- Ranges are only for number and calculated parameters. A choice parameter marks its abnormal
  choices instead.
- To stop using a range, untick **Range is in use**. It stays in the catalog's history.
- Every change and every approval is recorded in the audit log.

## Related pages

- [Test catalog](catalog.md)
- [Starter catalog](starter-catalog.md)
