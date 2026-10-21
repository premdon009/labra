---
title: Working on paper
features: [EC-L03, EC-D03]
---

# Working on paper

## What it's for

How to keep serving patients while Labra can't be reached, and how to enter that work once it
is back, so that every bill, sample and result ends up in Labra.

## Where to find it

Keep this page printed, with a stack of paper forms, at every front desk and in the lab.

## Steps

### While Labra is down

At the front desk, for each patient, write on a numbered paper form:

1. The date and time, and your name.
2. The patient's name, age, sex and phone number, and the referring doctor.
3. The tests, and the price of each from the printed price list.
4. The discount and its reason, the amount paid, how (cash, UPI with its reference, card),
   and what is due.
5. Give the patient a handwritten receipt with the form's number on it.
6. Write the form's number and the patient's name on each sample tube, in pen.

In the lab:

1. Keep a worksheet per department: form number, patient name, test, result, time, your
   initials.
2. Report a critical value by phone as usual, and write down whom you told and when.
3. Don't hand out handwritten reports. Results are released in Labra once it is back, so that
   they are verified and signed like any other report. Tell patients when to come back.

### Afterwards

When Labra is back, the administrator tells everyone from which time Labra's data is
complete. After a restore from backup that time can be up to 15 minutes **before** Labra
stopped, so check the last few bills and samples from before the outage too.

1. Front desk: for each paper form, in order, make the visit in Labra as usual
   ([New visit](../frontdesk/new-visit.md)) with the same tests, discount and payment. Write
   Labra's visit number on the paper form, and print the labels to stick over the handwritten
   ones.
2. Payments taken on paper: enter them with the visit, using the same method and UPI
   reference.
3. Lab: receive the samples, then enter the worksheet results on the result screen
   ([Entering results](../lab/entering-results.md)), verify and release as usual.
4. Keep the paper forms and worksheets with the day's records. They show what was done
   while Labra was down.

## Screenshot

There is no screen to show.

## Good to know

- Bills made afterwards carry the date they are entered. The paper form keeps the real date
  and time; put it in the visit's **Note for staff only** if needed.
- Enter the paper forms before new patients pile up, ideally the same day.
- If a payment on paper is entered twice by mistake, the UPI reference check refuses the
  second one ([Dues and payments](../frontdesk/dues-and-payments.md)).

## Related pages

- [Labra won't open](labra-wont-open.md)
- [New visit](../frontdesk/new-visit.md)
- [Backups and restore](../admin/backups-and-restore.md)
