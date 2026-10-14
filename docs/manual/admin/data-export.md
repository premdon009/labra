---
title: Data export
features: [M26]
---

# Data export

## What it's for

Take the lab's data out of Labra as ordinary files:

- **The day's accounts:** one day's figures for the accountant, to open in a spreadsheet or
  load into accounting software.
- **Everything:** every table, for another system, for analysis, or simply so the lab is
  never locked in.

## Where to find it

There is no screen. An administrator runs a command on the server, in the folder where
Labra was installed:

```bash
docker compose exec web labra export accounting --date 2026-10-14 --as <your username>
docker compose exec web labra export all --as <your username>
```

Only an active administrator can export. Each export is written in the audit log under
the name given after `--as`.

## Steps

### The day's accounts

1. Run `labra export accounting --date <YYYY-MM-DD> --as <your username>`.
2. Add `--branch <code>`, such as `--branch B2`, for one branch only. Without it, every
   branch is in the file, with a total line at the end.
3. Add `--format json` for software; the default, CSV, opens in a spreadsheet.
4. The file is written to `accounting/accounting-<date>-<branch or ALL>.<csv or json>` in the
   export folder. Running it again for the same day replaces the file with the figures as
   they are then.

Each line has the money taken by cash, UPI and card, the refunds and the net collected;
the bills issued with their gross, discount and net; the bills cancelled; what was owed at
the end of the day; and the tests sent to outside labs with their cost, the patients'
charge and the margin. They are the same figures as [Daily
figures](../owner/daily-collection.md) shows for that day.

### Everything

1. Run `labra export all --as <your username>`.
2. Add `--format csv` or `--format parquet` for one kind only; the default writes both.
3. A new folder `all-<date>-<time>` is made in the export folder, with:
   - `csv/`: one file per table, for people and most software;
   - `parquet/`: the same tables in Parquet, smaller and with their types, for analysis
     tools such as DuckDB, pandas or Excel Power Query;
   - `schema.md`: every table and column, its type, whether it may be empty, and which
     table it refers to.

## Good to know

- Exports hold patient data. They are written only to the export folder on the server
  (`/data/export`), readable by Labra alone. Copy them only to an encrypted disk, and
  delete copies you no longer need.
- The full export is taken at one moment, so its tables agree with each other even while
  the lab is working.
- Passwords and signed-in sessions are never exported.
- Uploaded files, such as letterheads, signatures, outside reports and report PDFs, are
  listed in the `stored_file` table but are not copied; they are in the backups.
- In CSV an empty cell is a missing value. Amounts are in rupees with two decimals, and
  times are in UTC with their offset.
- If the command says `Set LABRA_EXPORT_DIR`, the export folder is not set up; ask whoever
  installed Labra.

## Related pages

- [Daily figures](../owner/daily-collection.md)
- [Settings](settings.md)
