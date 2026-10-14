---
title: Letterhead and margins
features: [M17, EC-K03, EC-A07]
---

# Letterhead and margins

## What it's for

Reports and bills are made as PDF files by Labra. This screen sets, for each branch, the
letterhead drawn on them and the **content box**: the space inside the margins where the
report or bill is printed. Reports and bills have separate settings, so a bill can use a
smaller header.

Every document comes out in two ways from the same layout:

- **Digital**: the letterhead is drawn on the page. This is the copy that is downloaded,
  emailed or kept.
- **Print**: no letterhead, for paper that already has the letterhead printed on it. The
  text lands in exactly the same place as on the digital copy.

## Where to find it

**Menu ▸ Letterheads**, for administrators. Choose **Open** beside the branch and document.

## Steps

To set up a letterhead:

1. Under **Letterhead file**, choose the whole A4 page as one file and select **Upload**. An
   SVG or PDF file is best: it stays sharp and is small. A PNG, JPEG or WebP picture also
   works; it must be A4 portrait (for example 2480 × 3508 pixels).
2. Under **Content box**, fill in the **Top**, **Bottom**, **Left** and **Right** margins in
   millimetres, measured from the edge of the paper to where the text may start.
3. Fill in **Signature area on the last page**: the height kept free for the signatory's
   name and signature.
4. Choose **Text size** and whether to draw the letterhead on **Every page** or **The first
   page only**.
5. Watch the **Preview** while you type. The blue line is the content box and the red dashes
   the signature area. Choose another **Sample document** to check a long report or long
   names.
6. Select **Save draft**, or press **Alt+S**.
7. Select **Open the calibration page** and print it on your letterhead paper (see below).
8. When it looks right, select **Publish as version N**.

To go back to the built-in header, select **Use the built-in header instead**, then save and
publish.

### Printing the calibration page

1. Load the letterhead paper in the printer.
2. Open the calibration page and print it. In the print box set the scale to **Actual size**
   or **100%**, never **Fit to page**.
3. The four corner marks should meet the corners of the space on your paper, and the line
   marked **100 mm** should measure 100 mm with a ruler.
4. If the line is not 100 mm, the printer is scaling: check the scale setting again.
5. If everything is shifted the same way, set **Printer offset right** and **Printer offset
   down** for this branch in [Settings](settings.md). Use a negative number to move left or
   up. The offset changes only the print copy.

## Screenshot

<!-- screenshot: admin-letterhead.png (taken with demo data) -->

## Good to know

- Nothing changes on documents until you publish. A draft can be discarded with **Discard the
  draft**.
- Each publish makes a new version, numbered 1, 2, 3 and so on. A report that was already
  released, or a bill already issued, keeps printing on the version it was made with.
- With no letterhead published, documents print a plain header with the lab name, branch,
  address and phone inside the same margins.
- On a report, the patient's details and the barcode repeat at the top of every page, and the
  report number with **Page x of y** at the bottom, all inside the content box. Long names
  make that band taller, so it never runs into the letterhead. The **Sample document** list
  has a long report and long names in Hindi to check this.
- The screen shows the size of the file you uploaded and the size actually used. Pictures are
  resized to A4 at 150 dots per inch (set **Resolution for picture letterheads** in
  [Settings](settings.md) for 200), and the smaller of JPEG and PNG is kept. A report of
  several pages stores the letterhead only once, so the file stays small enough to send on
  WhatsApp.
- An SVG file is cleaned before use: scripts, links to other files and anything else that
  isn't a drawing are removed, and the screen lists what was taken out. A PDF letterhead
  keeps only its first page, without links or actions. Password-protected PDFs are refused.
- Labra fetches nothing from the internet while making a document. A letterhead that points
  to a web address shows without that part.
- Margins can be up to 120 mm at the top and bottom and 60 mm at the sides; text size from 7
  to 14 pt.
- Every upload, draft change, publish and discard is recorded in the audit log.

## Related pages

- [Settings](settings.md)
- [Branches](branches.md)
- [Releasing reports](../reports/releasing.md)
