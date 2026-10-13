---
title: Sample labels and collection
features: [M08, EC-J01]
---

# Sample labels and collection

## What it's for

Every tube or container gets a barcode label, so the lab always knows whose sample it is.
After the sample is taken, scanning the label records that it was collected, when, and by
whom.

## Where to find it

- Labels: on a visit, select **Print labels** or press **Alt+L**. Straight after **Save
  and print** on a new visit they open by themselves, once the bill has printed.
- Collection: **Menu ▸ Collect samples**. Front desk staff, phlebotomists, branch managers
  and administrators see it.

## Steps

To print the labels:

1. Open the labels as above. There is one label for each kind of container: tests that
   share a tube share a label.
2. In the print window, choose the **label printer** and the 50 × 25 mm label size, and
   print.
3. Stick each label on its container. The label names the container, such as `Grey top`,
   and the tests that go in it.

To record a collection:

1. Open **Collect samples**.
2. Choose who took the sample in **Collected by**. It stays chosen for the next scans.
3. Scan the label. The scanner types the **Sample number** and presses **Enter** for you.
   Without a scanner, type the number and press **Enter**.
4. Labra shows **Collected** with the patient, the container and the tests. The box is
   empty again and ready for the next label.

## Screenshot

<!-- screenshot: frontdesk-labels.png (taken with the demo data) -->

## Good to know

- A label shows the barcode, the sample number, the patient's name, age and sex, the
  container, and the tests.
- Labels print before the sample is taken, so the collection time is a blank
  `Coll __:__` to fill in by hand. A label printed again after collection shows the time.
- The bill prints on the A4 printer and the labels on the label printer, so the browser
  asks twice after a new visit.
- **Collected by** lists everyone active at your branch, including staff who never sign
  in, such as home-collection phlebotomists.
- A sample can be collected once. Scanning it again says it is already marked.
- A sample whose bill was cancelled can't be collected. Labra says so; throw the tube
  away.
- You can collect only the samples of the branch shown under **Working at**.
- If a label says **Container not set**, the test has no specimen type. Ask an
  administrator to set it in the catalog.
- Set the scanner to send **Enter** after each scan. Most scanners do this out of the box.
- A sample that is tested at another branch is scanned again when it arrives there. See
  [Receiving samples](../lab/receiving-samples.md).
- Each collection is recorded in the audit log.

## Related pages

- [New visit](new-visit.md)
- [Bills and receipts](bills-and-receipts.md)
- [Keyboard shortcuts](../getting-started/keyboard-shortcuts.md)
