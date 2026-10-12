---
title: Methods and comment presets
features: [M05]
---

# Methods and comment presets

## What it's for

A method says how the lab runs a test, for example Westergren for ESR, and is printed on the
report. Comment presets are ready-made comments a technician can add to a result instead of
typing them, such as "Sample haemolysed".

## Where to find it

Open a test in the **Test catalog** and select **Methods and comment presets**. Presets for
any test are on **Test catalog ▸ Comment presets**.

Everyone can look. Only an administrator can change them.

## Steps

To add a method:

1. Fill in **New method** at the bottom of the methods table.
2. Tick **Default** if this is the method the lab normally uses.
3. Select **Add method**.

To change a method, edit its row and select **Save** on that row.

To add a comment preset:

1. Fill in **New preset label**, a short name the technician picks from, and **Comment**, the
   text that is added to the result.
2. On **Comment presets**, choose **For**: one test, or **Any test**. On a test's own page the
   preset is for that test.
3. Select **Add preset**.

## Screenshot

<!-- screenshot: admin-methods.png (taken with demo data) -->

## Good to know

- A test has at most one default method. Making another method the default takes the mark
  off the old one.
- A method that is no longer used is switched off by unticking **In use**, so old reports
  still show it.
- A test can't have two methods with the same name.
- Every change is recorded in the audit log.

## Related pages

- [Test catalog](catalog.md)
