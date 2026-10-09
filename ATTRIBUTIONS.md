# Attributions

Labra is MIT-licensed. It builds on the open-source projects below; their licences apply to their code. The full dependency list, with licences and fallbacks, is in [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

## Bundled in the repository
| Project | Licence | Used for |
|---|---|---|
| htmx | 0BSD | partial page updates |
| Alpine.js (CSP build) | MIT | small client-side interactions |
| Basecoat | MIT | UI components and styles |

Vendored files and their SHA-256 checksums are listed in `src/labra/static/vendor/manifest.json`.

## Ideas borrowed, no code copied
Labra's design studied these projects' workflows and screens. No code or text was copied; GPL and AGPL projects were used for ideas only ([ADR-0002](docs/adr/0002-licence-mit.md)).

| Project | Licence | Idea |
|---|---|---|
| OpenELIS Global | MPL-2.0 | critical-value ranges and notification log |
| Bahmni | AGPL-3.0 | lab order flow between collection centre and main lab |
| SENAITE | GPL-2.0 | sample states and analysis workflow |
| Frappe, ERPNext | MIT, GPL-3.0 | accounting export shape |
| Home Assistant, Immich, Paperless-ngx | Apache-2.0, AGPL-3.0, GPL-3.0 | release, deprecation and maintainer-handover practices |
