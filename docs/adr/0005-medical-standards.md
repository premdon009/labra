---
items: [W02]
status: accepted
date: 2026-10-09
---

# ADR-0005: Medical standards — follow their shape now, export later

## Context
Indian labs are moving towards ABDM and FHIR-based exchange, but a small lab's first need is correct bills and reports. Code systems such as LOINC and SNOMED CT come with their own licences.

## Decision
- The data model follows HL7 FHIR R4 structure (Patient, ServiceRequest, Specimen, Observation, DiagnosticReport, Organization), so a FHIR export can be added without remodelling.
- Units use UCUM from the start.
- LOINC codes are an optional field on tests and parameters. SNOMED CT comes later.
- Labra ships **import tools, not code files**. Each lab imports the code files under its own licence.
- PC-PNDT: no fetal-sex fields or output anywhere (EC-C04); a test scans the models.

Details: design §11.

## Consequences
- Reports and exports can map to FHIR later without data migration.
- The repository stays free of licensed terminology content.
