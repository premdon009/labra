---
items: [W24]
status: accepted
date: 2026-10-15
---

# ADR-0011: Untrusted SVG parsed with the standard library

## Context
An administrator can upload an SVG letterhead. SVG is XML, so the file could declare entities
that expand to gigabytes, or point at a file or URL the server would read. Labra parsed it
with `defusedxml`, which refuses DTDs, entity declarations and external references, and then
ran its own allowlist sanitiser over the tree (`labra.core.svg`).

`defusedxml` was marked Watch in `docs/DEPENDENCIES.md`:

- it has had no release since 0.7.1 (2021-03-08) and has one maintainer;
- its ElementTree wrapper works by replacing ElementTree's parser class, which blocks
  CPython's faster C module for the whole process, and leans on interpreter details that
  each new Python version can change;
- Labra used it in exactly two calls, both in `labra.core.svg`.

The standard library has what those two calls need. Expat's handlers let a caller stop at the
first DOCTYPE, entity declaration or external reference, and expat 2.4.0 and later (2.8.2 on
Python 3.14) also caps how far entities may amplify a document.

## Decision
`labra.core.svg` parses uploaded SVG with `xml.parsers.expat` directly, feeding an
`xml.etree.ElementTree.TreeBuilder`. The parser raises at any DOCTYPE, entity declaration,
unparsed entity or external entity reference, and parameter entities are never read. An SVG
with a DOCTYPE is refused, as it was before. Namespaced names are turned into ElementTree's
`{namespace}name` form, so the allowlist code is unchanged.

`defusedxml` leaves the runtime dependencies. It stays in the lock only as a development
dependency of pip-audit. An import-linter contract keeps `xml` imports in `labra.core.svg`,
so no other module can parse untrusted XML on its own.

## Consequences
- Labra owns about 30 lines of parser set-up. `tests/test_svg.py` covers it with every
  attack the old parser was tested against (external DTD, `file://` entity, script, event
  handlers) and three more: a nested-entity bomb, an entity declared with no DOCTYPE, and a
  reference to an undeclared entity. A file saved by a drawing program, with its own
  namespaces, comments and `xml:space`, still parses and keeps its text.
- One fewer runtime dependency to watch.
- If a future Python or expat release weakens these defaults, or the handlers stop being
  called, the attack tests fail. The fallback is to bring `defusedxml` (or its successor)
  back in this one module; nothing outside `labra.core.svg` changes.
