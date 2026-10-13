---
title: Prices
features: [M06, M23.1, EC-F03]
---

# Prices

## What it's for

Every test and package has a lab price, charged at every branch. A branch can have its own
price for an item, which wins at that branch only. Labra keeps every old price, so a bill
always shows the price that was in force when it was made.

## Where to find it

**Menu ▸ Prices**. Everyone who can see the catalog can see prices. Only an administrator can
change them.

## Steps

To see prices, open **Prices**. To also see one branch's own prices, choose it in **Also show
the prices of** and select **Show**.

To change a price:

1. Select **Open** on the test or package.
2. Fill in **New price**, with up to two decimals, for example `180.50`. The heading shows
   the lab's currency symbol, set under **Settings ▸ Currency**, such as **New price (₹)**.
3. In **For**, keep **Every branch (lab price)**, or choose **Only** one branch to give that
   branch its own price.
4. Optionally fill in **Reason**, for example "New kit cost".
5. Select **Set price**. The new price starts at once.

To stop a branch's own price, so it charges the lab price again, select **Use the lab price
again** on its row under **Branch prices in force**.

## Screenshot

<!-- screenshot: admin-prices.png (taken with demo data) -->

## Good to know

- Long lists show 25 rows at a time. Use **Previous** and **Next** under the list to move
  through them; a search or filter you chose stays in place.
- A test or package without a price shows **No price**. Give it one before the front desk
  needs it.
- Prices can't be negative or have more than two decimals.
- A change never alters an old price. The old price stops at the moment the new one starts,
  and both stay in **History**.
- A later change to the lab price doesn't touch a branch's own price; that stays until it is
  stopped or changed.
- Every change is recorded in the audit log with the old and new price and the reason.

## Related pages

- [Test catalog](catalog.md)
- [Branches](branches.md)
