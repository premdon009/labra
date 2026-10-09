---
items: [W02]
---

# Compliance checklist (India)

What Labra does, or must do, for each law or standard that touches a small diagnostic lab. Background and sources: [`docs/research/india-lab-regulations.md`](../research/india-lab-regulations.md).

> **Not legal advice.** A chartered accountant (GST) and a lawyer (DPDP, IT Act signatures) must review this list before Labra is offered to other labs (EC-C08). Each lab remains responsible for its own compliance.

Status: ☐ not started · ◐ partly · ☑ done. Ticks happen in [`ENTERPRISE_CHECKLIST.md`](../ENTERPRISE_CHECKLIST.md); this page explains the reason for each.

## Digital Personal Data Protection Act 2023 and Rules
Full compliance is due by 13 May 2027. Lab results are high-risk personal data.

| Obligation | What Labra does | Item |
|---|---|---|
| Consent before processing and before sharing with a referral lab | consent recorded per visit; consent text versioned | EC-C01 |
| Share only what's needed | outsourced-test manifests carry the minimum; phone and address only when the receiving lab requires them | EC-C02 |
| Security safeguards | encrypted disk, encrypted backups, role and branch scoping, append-only audit log | EC-A05, EC-A12, M15 |
| No personal data in logs, URLs, analytics or metrics | log scrubbing with a CI test; metric labels never carry IDs | EC-C03, W16 |
| Notice, access, correction, erasure | privacy notice; patient data export; correction workflow; anonymise after the retention period | EC-C06 |
| Breach notification within 72 hours | breach register and runbook | EC-C06 |
| Processors and sub-processors | data-processing agreement template; list of sub-processors (backup cloud, tunnel, messaging provider) | EC-C07 |
| Data kept in India | default install keeps data on the lab's own server; cloud backup region documented | W06 |

## NABL (ISO 15189:2022)
| Requirement | What Labra does | Item |
|---|---|---|
| Who did what, when | append-only, hash-chained audit log | M15 |
| Records kept at least 2 years; no hard deletes | retention rule, soft delete only | EC-C05 |
| Critical values communicated and logged | critical-value highlight and "informed whom, when" log | see design §1b |
| Authorised signatories | signatory list on reports | EC-C09 |
| Audit pack for assessors | export of audit trail, signatories, critical-value log, QC | EC-C09 |

## PC-PNDT Act 1994
| Requirement | What Labra does | Item |
|---|---|---|
| No disclosure of fetal sex | no fetal-sex field or output anywhere; a test scans the models | EC-C04 |
| Form F and 2-year retention (ultrasound centres) | out of scope while Labra handles lab tests only | — |

## IT Act 2000 and SPDI Rules 2011
| Requirement | What Labra does | Item |
|---|---|---|
| Reasonable security practices | the A section of the enterprise checklist; OWASP ASVS L1 self-assessment | EC-A14 |
| Electronic signatures on reports | signature image now; DSC or eSign through `labra.report_signers` later — needs the lawyer's view | design §7.1 |

## GST and billing (needs CA review)
- GST treatment of lab-to-lab (B2B) outsourced tests.
- Wording required on bills and receipts; receipt numbering per financial year.
- Whether e-invoicing applies at the lab's turnover.

## ABDM
Not mandatory for private labs outside government schemes as of 2026. The data model follows FHIR so ABDM integration can come later (ADR-0005).
