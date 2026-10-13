---
title: External labs
features: [M10]
---

# External labs

## What it's for

Some tests are not done in your own lab and are sent to another lab. This screen holds those
labs: who to call, whether they have signed a data agreement, which tests each one does for
you, what it charges and how long it takes. The lab staff see these costs when they choose
where to send a test.

## Where to find it

**Menu ▸ External labs**. Administrators can add and change labs. Technicians and branch
managers can see them but not change them.

## Steps

To add a lab:

1. Select **Add lab**.
2. Fill in **Name**. The other boxes are optional: **NABL certificate number**, **Contact
   person**, **Phone**, **Email**, **Email that results come from** and **Results website**.
3. Fill in **Data agreement signed on** if the lab has agreed in writing how it handles
   patient details.
4. Under **On the sheet sent with a sample**, tick **Patient's phone** or **Patient's
   address** only if this lab really needs them. Both start unticked.
5. Select **Save**, or press **Alt+S**.

To say which tests the lab does, open the lab and use **Add a test or change its cost**:

1. Fill in **Test code** with your own code from the test catalog, for example `vitd`.
2. Fill in **Cost**, what the lab charges you, with up to two decimals.
3. Fill in **Result in (hours)**, how long the lab takes.
4. Optionally fill in **Their code**, the lab's own code for the test.
5. Select **Set cost**. The test appears under **Tests this lab does for us**.

To change a cost, enter the same test code again with the new cost. To stop sending a test to
this lab, select **Stop sending** on its row.

To stop using a lab altogether, open it, untick **We still send tests to this lab** and
select **Save**.

## Screenshot

<!-- screenshot: admin-external-labs.png (taken with demo data) -->

## Good to know

- Two labs can't have the same name.
- A lab's sheet always carries the patient's name, age and sex. Phone and address go only
  when ticked here.
- A new cost starts at once. A test that was already sent keeps the cost it was sent at, and
  the old cost stays under **Earlier costs**.
- A cost can't be negative or have more than two decimals. **Result in (hours)** is a whole
  number from 1 to 1440.
- A lab that is **Not in use**, and a test you stopped sending, are no longer offered when a
  test is sent out. Tests already sent are not affected.
- The demo data has two invented labs with different costs for the same test.
- Every change is recorded in the audit log.
- Long lists show 25 rows at a time. Use **Previous** and **Next** under the list.

## Related pages

- [Test catalog](catalog.md)
- [Prices](prices.md)
