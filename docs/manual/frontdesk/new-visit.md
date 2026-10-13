---
title: New visit
features: [M18, M18.2, M07, M07.2, M04, EC-C01, EC-B07, EC-J01, EC-J02]
---

# New visit

## What it's for

One screen for everything that happens when a patient comes to the counter: find or
register the patient, choose the tests, give a discount, take the money, and save. Saving
makes the visit, the samples to collect, the bill and the receipt together.

## Where to find it

**Menu ▸ New visit**, or press **Alt+N** on any screen. Front desk staff, branch managers
and administrators see it.

## Steps

The whole screen works from the keyboard. **Tab** moves forward, **Shift+Tab** moves back.

1. Type the patient's **Phone**. If someone is already registered with that number, Labra
   lists them under the box: select the patient to use their record.
2. For a new patient, fill in the **Full name**, the **Sex**, and the **Date of birth, or
   the age** in **Years**, **Months** and **Days**.
3. Select **Referred by** (or press **F2**) and choose the doctor or clinic that sent the
   patient. Type part of the name to shorten the list. If they aren't listed, fill in
   **Not in the list? Add them** and select **Add and choose**. Leave it at **No referrer**
   for a patient who came on their own.
4. In **Test code or name**, type a code such as `fbs` or part of a name, and press
   **Enter** to add the first match. Carry on typing the next one. Each line says whether
   the test is done **in-house** or is **outsourced ★**. Select **Remove** to take a line
   off.
5. For a charge that isn't a test, such as home collection, fill in **Extra charge**,
   **Amount** and **Reason**, and select **Add charge**.
6. To give a discount, type the **Discount**, choose **Amount** or **Per cent**, and give
   the **Discount reason**. **To pay** shows the new figure.
7. Choose **Paid by** and type the **Amount paid now**. For UPI, type the reference number
   (UTR) from the patient's phone, 8 to 35 letters and digits with at least one digit; for a
   card, the last 4 digits. Leave the amount empty if the
   patient will pay later.
8. Tick the consent box after the patient has read the notice. **Read the notice** shows
   its words.
9. Select **Save and print**, or press **Alt+S**. The bill and receipt open ready to print,
   and after them the [sample labels](labels.md).

## Screenshot

<!-- screenshot: frontdesk-new-visit.png (taken with the demo data) -->

## Good to know

- **Enter** never saves the visit by accident. It adds the test you typed. Only **Save and
  print** or **Alt+S** saves.
- You can add tests and change the discount quickly, one after the other. Labra applies
  the changes in the order you made them, so the total always matches the lines shown.
- You don't have to wait for one test to appear before typing the next code. What you type
  while Labra is still adding the last test stays in the box.
- Nothing is kept until you save. If a field is wrong, Labra says **Not saved yet**, marks
  the field, and keeps everything you typed.
- If the phone and a similar name are already registered, Labra asks whether this is the
  same person. Choose the existing patient, or **Register as a new patient and save** for
  someone else sharing the phone.
- The consent tick is needed once for each version of the notice. A patient who agreed
  before shows **Consent on file**. When an administrator publishes a new notice, every
  patient is asked again.
- The same test can't be ordered twice in one visit, also not once on its own and once
  inside a package.
- A test or package with no price at your branch can't be added. Ask an administrator to
  set the price.
- A discount and an extra charge each need a reason. The discount reason prints on the
  bill.
- **Promise results by** is filled in for you from the slowest test ordered. Set another
  time only if you have agreed one with the patient.
- **Note printed on the bill** is for the patient. **Note for staff only** is never
  printed.
- Selecting **Save and print** twice, or losing the connection while saving, never makes
  two visits or two bills.
- If a search or a lookup fails, a red message at the top of the screen says so. What you
  typed stays; try again.
- The visit is made at the branch shown under **Working at**.

## Related pages

- [Bills and receipts](bills-and-receipts.md)
- [Dues and payments](dues-and-payments.md)
- [Referrers](referrers.md)
- [Keyboard shortcuts](../getting-started/keyboard-shortcuts.md)
