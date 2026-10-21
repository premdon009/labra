---
title: A day at the lab
features: [EC-L02]
---

# A day at the lab

## What it's for

One patient's tests from the front desk to the final report, step by step, with the page of
this manual for each step. Read it first to see how the screens fit together, or use it for
training with the demo data. Everyone in it is made up.

## Where to find it

The demo data (`labra seed`, on a training copy only, never on the lab's own server) has the
same people and places:

| Who | Signs in as | Works at |
|---|---|---|
| Front desk | `priya` | Branch 2, a collection centre |
| Technician | `suresh` | the main lab |
| Signatory (pathologist) | `meera` | the main lab |
| Owner | `anil` | everywhere |

## Steps

### 1. 08:40, Branch 2 front desk: the visit

A 58-year-old man comes in with a doctor's slip for fasting glucose, a lipid profile, a urine
routine and vitamin D.

1. The front desk presses **Alt+N** for a new visit and types his phone number. He has been
   before, so his record comes up and no duplicate is made
   ([Find or register a patient](../frontdesk/find-patient.md)).
2. She picks the referring doctor, then types each test's short code; the line under the box
   shows the test and its price before **Enter** adds it ([New visit](../frontdesk/new-visit.md)).
3. She gives the senior citizen discount with its reason, takes part of the amount by UPI with
   its reference, and leaves the rest as due. She ticks the consent box.
4. **Save and print** prints the bill and then the sample labels, one per tube
   ([Bills and receipts](../frontdesk/bills-and-receipts.md),
   [Sample labels and collection](../frontdesk/labels.md)).

### 2. 08:50, collection

The phlebotomist takes the samples. The front desk opens **Collect samples**, chooses the
phlebotomist in **Collected by**, and scans each tube ([Sample labels and collection](../frontdesk/labels.md)).
At 11:00 the courier takes the box to the main lab.

### 3. 11:45, main lab: receiving and sending out

1. The technician opens **Receive samples** and scans each tube. The in-house tests appear on
   the worklist ([Receiving samples](../lab/receiving-samples.md), [Lab worklist](../lab/worklist.md)).
2. Vitamin D isn't done in-house. Under **Lab ▸ Outsourcing**, he picks the outside lab by its
   cost and turnaround time, prints the sheet for the bag, types the outside lab's own number
   and marks the test sent ([Outsourcing](../lab/outsourcing.md)).

### 4. 14:10, results

The technician opens the patient from the worklist and types each value, pressing **Enter**
after each ([Entering results](../lab/entering-results.md)).

- Labra picks the adult male reference intervals and marks each value: high, low, abnormal or
  normal, with the row's colour. The calculated values (LDL, VLDL, the ratio) fill in by
  themselves ([Calculated values](../lab/calculated-values.md)).
- A typing slip such as 1320 for glucose asks for a check before it can be saved.
- A critical value (glucose of 480, say) can't be left until he records whom he told and when
  ([Critical values](../lab/critical-values.md)).

He submits the tests for verification.

### 5. 15:00, verification and the first report

The signatory reads the results with the previous values, verifies them, and releases the
report from **Menu ▸ Reports** ([Releasing reports](../reports/releasing.md)). Vitamin D is
still with the outside lab, so this is a **partial report** that lists it as pending.

At 17:30 the patient comes back to Branch 2. The front desk prints the report on the branch's
letterhead paper and records that it was handed to the patient
([Print or send](../reports/print-vs-digital.md), [Handing over reports](../reports/delivery.md)).

### 6. The next day, 12:20: the outside result

The outside lab emails its PDF. The technician attaches it under **Results from outside labs**,
types the value so that it shows in the patient's history, and submits it
([Outsourcing](../lab/outsourcing.md)).

### 7. 13:00, the final report

The signatory verifies vitamin D and releases version 2 of the same report. It carries every
test, with vitamin D marked as done by the outside lab. When the patient collects it, the
front desk takes the amount due in cash and the bill shows as paid
([Dues and payments](../frontdesk/dues-and-payments.md)).

### 8. Throughout: the lab status board

Later. A screen for the lab's TV showing each visit's progress isn't in Labra yet.

### 9. 20:00, the owner's evening check

The owner opens **Menu ▸ Owner figures**: the day's money by branch and payment method, the
dues with this patient's balance, pending tests, and what was sent out with its cost and margin
([Daily figures](../owner/daily-collection.md),
[Dues, pending tests and outsourcing](../owner/dues-pending-outsourcing.md)).

### 10. By itself, all day and night

- Every 15 minutes in lab hours, a backup goes to Google Drive and the USB disk
  ([Backups and restore](../admin/backups-and-restore.md)).
- At night Labra checks that nobody changed the audit log, and every hour that the disk has
  room. Once a month it restores a backup to prove it works. Anything wrong sends the owner an
  alert ([Alerts and nightly checks](../admin/alerts-and-checks.md)).

## Screenshot

<!-- screenshot: getting-started-a-day-at-the-lab.png (taken with the demo data) -->

## Good to know

- Every step above is in the audit log, with who did it and when. The patient's history
  shows all his visits, results and reports in one place
  ([Patient history](../frontdesk/patient-history.md)).
- A branch sees only its own patients and visits. The main lab sees the samples sent to it.

## Related pages

- [Screen layout](screen-layout.md)
- [Keyboard shortcuts](keyboard-shortcuts.md)
