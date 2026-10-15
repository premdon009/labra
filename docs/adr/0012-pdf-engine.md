---
items: [M12, M17]
status: accepted
date: 2026-10-15
---

# ADR-0012: WeasyPrint stays the PDF engine

## Context
Reports and bills are HTML templates turned into PDF by WeasyPrint, inside `labra.printing`
and nowhere else (an import-linter contract). The letterhead is then stamped on with pypdf.
WeasyPrint needs `pyphen` for hyphenation. `pyphen` is used under MPL-1.1, a recorded licence
exception in `docs/DEPENDENCIES.md`, and its bundled dictionaries carry mixed licences. The
owner asked on 2026-10-15 what else could produce these PDFs, including the engines Documenso
and Microsoft use, and what a switch would cost. This record keeps the answer, from research
done that day, so the question needn't be researched again from scratch.

What a Labra PDF needs:

- paged CSS: running headers and footers, margin boxes, "page X of Y", tables that break
  across pages with repeated headers;
- correct Devanagari and the rupee sign, which means a real text shaper (HarfBuzz);
- offline rendering on a small server, x86-64 or arm64, with no network access;
- a few hundred milliseconds per report on an old laptop.

## Options
**WeasyPrint (kept).** BSD-3-Clause; 70.0 released 2026-09-08. It runs in-process, works
offline, and has the strongest paged-CSS support of the open engines: running headers, margin
boxes and `counter(pages)`. Devanagari is shaped by Pango and HarfBuzz. `pyphen` comes with
it: WeasyPrint imports it at start-up, so it can't be dropped while WeasyPrint stays.

**Chromium print through Playwright (Microsoft, Apache-2.0): fallback 1.**
- The HTML templates and the pypdf stamping are kept.
- The running header moves to Chromium's header template, or to the CSS margin boxes Chrome
  now prints (see the print-margins post below).
- Every network request must be blocked through request interception.
- The cost is about 500 MB more image and 150–300 MB of RAM per browser. It would run as a
  sidecar container, not inside the app.
- Gotenberg (MIT) is the ready-made container form of the same engine, and heavier still.
- Microsoft has no HTML-to-PDF engine of its own apart from Playwright; WebView2's
  `PrintToPdfAsync` is Windows only.

**Typst (Apache-2.0): fallback 2.** Small, in-process, offline, and built for arm64. But
every template would be rewritten in Typst's own language. That language is still pre-1.0,
and the Python binding (`typst-py`) has one maintainer.

**Documenso's approach: doesn't fit.** In January 2026 Documenso stopped printing through
Playwright. It now draws pages with Konva on skia-canvas and uses `@libpdf/core` (MIT) to
open, stamp and sign PDFs. That suits fixed-layout certificates. It has no HTML layout, so it
can't flow a report of any length across pages, and it would need a Node sidecar.

**Not candidates.**
- ReportLab: its Indic shaping is experimental.
- pdf-lib: unmaintained since 2021.
- @react-pdf/renderer: unreliable Indic shaping, and it needs Node.

## Decision
WeasyPrint stays the PDF engine, and `pyphen` stays with it. Labra never asks it to
hyphenate. If WeasyPrint has to go, the order is Chromium through Playwright as a sidecar,
then Typst. The swap is confined to `labra.printing.pdf` (see `docs/dev/services.md`).

## Consequences
- No change to code or images.
- `pyphen` and its dictionaries stay in the image. Stripping the dictionaries would save
  about 6.2 MB (1–2% of the image) and gain nothing in speed, memory or security; look again
  when the attributions page is done.
- Look again if WeasyPrint stops being maintained, if a CSS feature a report needs is
  missing, or if its licence changes.

## Sources
Read on 2026-10-15. Versions at that date: Playwright for Python 1.64.0 (2026-10-13),
Gotenberg 8.37.0 (2026-09-11), typst-py 0.15.0 (2026-06-16), ReportLab 5.0.1 (2026-08-20),
@libpdf/core 0.5.2 (2026-10-07), pdf-lib 1.17.1 (2021-11-06), @react-pdf/renderer 4.9.0
(2026-08-27).

- <https://github.com/documenso/documenso/blob/main/ARCHITECTURE.md>
- <https://github.com/documenso/documenso/pull/2251> (Konva, 2026-01-06)
- <https://github.com/documenso/documenso/pull/2403> (libpdf, 2026-01-21)
- <https://github.com/LibPDF-js/core>
- <https://playwright.dev/python/docs/api/class-page#page-pdf>
- <https://developer.chrome.com/blog/print-margins>
- <https://github.com/gotenberg/gotenberg>
- <https://pypi.org/project/typst/> and <https://github.com/messense/typst-py>
- <https://pypi.org/project/reportlab/>
- <https://github.com/Hopding/pdf-lib>
- <https://github.com/diegomura/react-pdf>
