---
title: Receiving samples
features: [M11.3]
---

# Receiving samples

## What it's for

A sample taken at one branch and tested at another travels between them. Scanning it when
it arrives records that the lab has it, when, and who took it in. Until then its tests show
as collected, not as in the lab.

## Where to find it

**Menu ▸ Receive samples**. Technicians and phlebotomists see it.

## Steps

1. Check **Working at** shows the lab the samples have arrived at.
2. Open **Receive samples**.
3. Scan the label. The scanner types the **Sample number** and presses **Enter** for you.
   Without a scanner, type the number and press **Enter**.
4. Labra shows **In the lab** with the patient's name, age and sex, the container, the
   tests, and the branch the sample came from. The box is empty again and ready for the
   next label.

## Screenshot

<!-- screenshot: lab-receiving-samples.png (taken with the demo data) -->

## Good to know

- Only samples that come from another branch need the scan. A sample collected at the
  branch that also tests it is in the lab as soon as it is collected.
- An administrator can change this under **Settings**, with **Scan samples in when they
  reach the lab**: only samples from another branch, every sample, or never.
- The screen never shows the patient's phone number or address.
- A sample must be marked as collected first. If Labra says it **isn't marked as collected
  yet**, ask the branch that took it to record the collection.
- **Has no test that is done at this branch** means the sample belongs to another lab, or
  **Working at** shows the wrong branch.
- **Is already in the lab** means the sample was scanned before. Nothing more is needed.
- A sample whose bill was cancelled can't be received. Labra says so; don't test it.
- Set the scanner to send **Enter** after each scan. Most scanners do this out of the box.
- Each scan is recorded in the audit log.

## Related pages

- [Sample labels and collection](../frontdesk/labels.md)
- [Settings](../admin/settings.md)
- [Keyboard shortcuts](../getting-started/keyboard-shortcuts.md)
