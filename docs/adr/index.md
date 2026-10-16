# Architecture decision records

How to write one: [ADR-0001](0001-record-decisions.md).

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-record-decisions.md) | Record architecture decisions | accepted |
| [0002](0002-licence-mit.md) | Licence stays MIT; copyleft projects are for ideas only | accepted |
| [0003](0003-fastapi-postgres.md) | Build fresh on FastAPI and Postgres | accepted (admin-screen line superseded by 0010) |
| [0004](0004-small-server-hosting.md) | Small server at the main lab, with layered offline fallbacks | accepted |
| [0005](0005-medical-standards.md) | Medical standards: follow their shape now, export later | accepted |
| [0006](0006-customisation-model.md) | Customisation through settings, data, templates and plugins | accepted |
| [0007](0007-replaceable-edges.md) | Replaceable edges, stable core | accepted |
| [0008](0008-platform-ports.md) | Platform services behind ports, with built-in defaults, and a database seam | accepted |
| [0009](0009-runtime-neutral-packaging.md) | Runtime-neutral packaging | accepted |
| [0010](0010-own-admin-screens.md) | Own HTMX admin screens instead of SQLAdmin | accepted |
| [0011](0011-svg-stdlib-parser.md) | Untrusted SVG parsed with the standard library | accepted |
| [0012](0012-pdf-engine.md) | WeasyPrint stays the PDF engine | accepted |
| [0013](0013-backup-runner.md) | Backups run from host timers in a one-shot container | accepted |
