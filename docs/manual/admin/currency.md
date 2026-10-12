---
title: Currency
features: [M23]
---

# Currency

## What it's for

Sets how amounts look on screens, bills and receipts at your branch: the symbol, where it
goes, how digits are grouped, and how the amount is written in words. It also sets what
bill totals are rounded to.

## Where to find it

**Menu ▸ Settings ▸ Currency**. Administrators and branch managers can change it. Others
can't open it.

## Steps

1. Choose the values you want. The **How amounts will look** box at the top changes as
   you choose, so you can check the result before saving.
2. Select **Save**. Values that aren't allowed are shown in red with the reason, and
   nothing is saved until they are fixed.

## Screenshot

<!-- screenshot: admin-currency.png (taken with the demo data) -->

## Good to know

| Setting | Choices | Starts as |
|---|---|---|
| Currency code | Three capital letters | `INR` |
| Currency symbol | Up to 5 characters, or blank for none | `₹` |
| Where the symbol goes | Before or after the amount, with or without a space | Before: `₹1,737.00` |
| Digit grouping | Lakh and crore (`1,23,45,678`) or thousands and millions (`12,345,678`) | Lakh and crore |
| Decimals shown | Two, or none | Two |
| Symbol in bill columns | Once in the column heading, or on every amount | Column heading |
| Amount in words | Lakh and crore, or million and billion | Lakh and crore |
| Word for the main unit | Any word, up to 20 characters | `rupees` |
| Word for the small unit | Any word, up to 20 characters | `paise` |
| Round bill totals to | Nearest rupee, 50 paise, 10 paise, or no rounding | Nearest rupee |

- Every setting here is for **your current branch**. To change another branch,
  [switch](../getting-started/screen-layout.md) to it first.
- Amounts are always kept to the paisa. Choosing no decimals changes only what is shown:
  `₹1,737.50` shows as `₹1,738`.
- Amounts in words are written cheque style, for example *Rupees one thousand seven
  hundred thirty-seven and fifty paise only*.
- A bill keeps the look it had when it was made. Changing these settings changes new
  bills only; reprints of old bills look the same as the first print.
- Every change is recorded in the audit log with the old and new value.

## Related pages

- [Settings](settings.md)
