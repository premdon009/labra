---
title: Starter catalog
features: [M24]
---

# Starter catalog

## What it's for

The starter catalog is a ready-made set of about forty common tests (blood counts, sugar,
lipids, liver and kidney tests, thyroid, urine, serology and more), with their parameters,
units, methods, formulas, packages and adult reference ranges. It saves typing the catalog
from scratch. It has no prices.

## Where to find it

**Test catalog ▸ starter catalog**: the link shows while the catalog is empty. The page is at
`/admin/catalog/starter` for an administrator at any time.

An administrator can also import it from the server's command line:
`labra import-starter --as <username>`.

## Steps

1. Open the starter catalog page and read what will be added.
2. Select **Import the starter catalog**. The page says how much was added and lists any test
   it left alone.
3. Ask a signatory to check and approve the new reference ranges on **Ranges to approve**.
4. Set the [prices](prices.md).
5. Change anything to match how the lab works: codes the staff are used to, names, methods,
   ranges for the lab's own analysers.

## Screenshot

<!-- screenshot: admin-starter-catalog.png (taken with demo data) -->

## Good to know

- Importing only adds what is missing. A test or package whose code the lab already uses is
  left exactly as it is, and so are departments and specimen types it already has.
- Importing again, for example after an upgrade, adds only new items; nothing is added twice.
- Every imported range shows its source, starts at 18 years, and waits for a signatory's
  approval. Ranges for children must be added by the lab.
- No critical limits are imported; the lab sets its own.
- Every imported item is recorded in the audit log like an administrator's own change.

## Related pages

- [Test catalog](catalog.md)
- [Reference ranges](reference-ranges.md)
- [Prices](prices.md)
