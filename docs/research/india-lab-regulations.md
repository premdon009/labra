# Indian Regulatory Compliance for Lab Management Software (August 2026)

**Document Date:** August 18, 2026  
**Scope:** Compliance obligations for small to mid-sized diagnostic center/pathology lab software (patient records, test orders, results, billing, inventory)

---

## Executive Summary

Small and mid-sized diagnostic centers in India must navigate a complex, overlapping regulatory landscape spanning data protection (DPDP Act 2023), healthcare interoperability (ABDM), quality assurance (NABL accreditation), facility registration (Clinical Establishments Act), and emerging AI governance. As of August 2026, the most critical compliance obligations are:

1. **DPDP Act compliance by May 2027** — consent management, data breach notification, security safeguards (ISO 27001 or equivalent), and patient data erasure/retention policies now operationalized with active regulatory enforcement from November 2026 onward
2. **ABDM integration for empanelled labs** — not universally mandatory yet, but increasingly required for AB-PMJAY empanelment and state insurance access; HFR registration and FHIR-compliant data exchange are effectively de facto requirements by 2026
3. **NABL 112/ISO 15189 compliance** — audit trails, data integrity, authorized signatories, authorized signatories, record retention (minimum 2 years post-patient discharge/termination), and lab information system controls are now evaluated under ISO 15189:2022 standards
4. **PC-PNDT Act record-keeping** — Form F maintenance and 2-year retention for prenatal diagnostic procedures; non-compliance invokes suspension or cancellation of facility registration
5. **DPDP Act and IT Act 2000 / SPDI Rules overlap** — until DPDP fully repeals SPDI Rules, dual compliance is required; SPDI Rules mandate ISO/IEC 27001 or equivalent security standards for health data

**No standalone AI regulation exists as of August 2026**, but ICMR Ethical Guidelines (2023) require prospective validation, post-deployment audits, and accountability frameworks for AI-assisted diagnostic interpretation; GST/e-invoicing applies only to taxable services (wellness packages, commercial testing); diagnostic patient-facing tests remain GST-exempt.

---

## 1. Digital Personal Data Protection Act 2023 & DPDP Rules

**Status as of August 2026:** Operative since November 14, 2025; enforcement in transition from soft enforcement to active regulatory oversight.

### Timeline & Enforcement Phases

- **Phase 1 (November 2025 – Present):** Board established, complaint portal live, penalties nominally in force but soft enforcement.
- **Phase 2 (November 2026):** Consent Manager framework operationalization complete; transition to active regulatory supervision. Soft enforcement ends.
- **Phase 3 (May 13, 2027):** Hard deadline for full compliance; no grace period. IT Secretary has confirmed immediate enforcement from Day 1.
- **Possible acceleration:** MeitY proposed (January 2026) to compress Significant Data Fiduciary (SDF) compliance window from 18 months to 12 months — if gazetted, large-volume data processors face a November 2026 deadline.

### Health Data Classification

- **No separate "sensitive category"** — the Act adopts a risk-based approach. Health data (medical histories, diagnoses, prescriptions, lab results, genetic info, mental health records) is unequivocally high-risk.
- Central Government can designate large hospitals, hospital chains, health insurers, and health-tech platforms as SDFs, triggering heightened obligations (e.g., privacy by design, data protection impact assessments, internal audit).
- Diagnostic labs managing patient records and lab results are data fiduciaries; labs processing high volumes may be designated SDFs.

### Key Obligations for Lab Software

| Obligation | Requirement |
|---|---|
| **Consent** | Obtain explicit, informed consent before collecting/processing health data. Must be presented in plain language. Consent Managers (being operationalized Aug 2026) allow patients to manage/withdraw consent across platforms. |
| **Notice & Transparency** | Publish a privacy policy disclosing data collection, purpose, retention, sharing, and patient rights. Must be easily accessible. |
| **Data Security** | Implement security safeguards — no specific standard mandated, but compliance with ISO/IEC 27001 or equivalent is de facto required and legally safer. Encryption at rest and in transit, access controls, audit logs. |
| **Breach Notification** | Notify affected persons and the Data Protection Board of India within 72 hours of breach discovery. A "breach" includes unauthorized access, use, disclosure, or loss of personal data. |
| **Data Retention & Erasure** | Retain health data only for the time necessary to fulfill the stated purpose. Patient has the right to request erasure ("right to be forgotten") once purpose is fulfilled; lab must comply unless legal obligation requires retention. NABL typically requires 2-year retention post-discharge; balance retention needs against erasure requests. |
| **Cross-Border Transfer** | Health data transfer outside India is permitted only where the recipient country offers adequate data protection or with explicit patient consent. EU-equivalent data protection is considered "adequate." |
| **Liability & Penalties** | Contraventions attract penalties up to ₹250 crore (serious breach) or ₹5 crore (other breaches), personal liability for officers, and criminal prosecution. |

### Consent Manager Framework (August 2026 Context)

As of August 2026, the central Consent Manager framework is being operationalized (June–August 2026 rollout). This allows patients to:
- Review, grant, or withdraw consent for data sharing with multiple health services from one interface.
- Track data flow in real time.

Labs integrating with ABDM or other health data exchanges should prepare for Consent Manager integration.

**Sources:**
- [India's DPDP Timeline: Critical Compliance Deadlines for 2026-27](https://www.india-briefing.com/news/india-dpdp-compliance-timeline-enforcement-2026-27-44740.html)
- [DPDP Compliance Timeline 2026–2027 | ConsentOS](https://consentos.in/learn/dpdp-compliance-timeline/)
- [Health Data and the DPDP Act: A Practical Guide | AM Legals](https://amlegals.com/health-data-and-the-dpdp-act-a-practical-guide/)

---

## 2. Ayushman Bharat Digital Mission (ABDM) & Health Facility Registry

**Status as of August 2026:** De facto mandatory for empanelled labs; voluntary for private labs not linked to government schemes but increasingly a market requirement.

### Current Mandate Status

- **Not universally mandatory** for private diagnostic labs *not* under government schemes (as of mid-2026).
- **Effectively mandatory** for:
  - Labs empanelled under AB-PMJAY (Ayushman Bharat Pradhan Mantri Jan Arogya Yojana).
  - Labs participating in state insurance schemes or CGHS/ECHS.
  - Government hospital-linked diagnostic centers.
  - Labs bidding on government contracts/tenders (ABDM integration is an eligibility criterion).
- **Market reality:** By 2027, ABDM certification is expected to be a de facto market requirement; adoption is accelerating across hospital chains and private labs.

### Key ABDM Components for Lab Software

| Component | Role |
|---|---|
| **ABHA (Ayushman Bharat Health Account)** | Unique 14-digit patient identifier. Patients create their own ABHA ID; labs should support patient login via ABHA and record this ID alongside test results. |
| **Health Facility Registry (HFR)** | Public registry of all facilities under ABDM. Every diagnostic lab should register (free) at facility.abdm.gov.in to obtain a unique facility ID — prerequisite for integration, state insurance access, and ABDM-linked reporting. Registration requires Aadhaar-linked mobile number of owner/authorized manager, facility name, address, geolocation, and facility type (lab). |
| **Health Professional Registry (HPR)** | Registry of all registered medical practitioners. Lab directors and authorized signatories should register. Not mandatory but increasingly expected. |
| **FHIR R4 Interoperability** | ABDM mandates HL7 FHIR R4 for data exchange. For labs: LOINC codes for laboratory test results, SNOMED CT and ICD-10/11 for terminology. Lab software must support these standards for ABDM integration. |
| **HMIS/LMIS Certification** | Hospital Information Management System (HMIS) or Laboratory Management Information System (LMIS) must pass WASA (Web API Security Assessment) testing by a CERT-In empanelled auditor before production integration. Process typically takes 3–6 months. |

### M1/M2/M3 Certification

- **M1 Certification:** LMIS passes WASA security audit and integrates with ABDM sandbox.
- **M2 Certification:** LMIS demonstrates consent management and patient consent for data sharing.
- **M3 Certification:** Advanced integration, e.g., health record exchange, clinical document generation.

Private labs most commonly pursue M1 certification initially; M2/M3 are aspirational or required for larger operators.

### Financial Incentive

The Digital Health Incentive Scheme offers:
- Up to ₹4 crores per facility for ABDM-compliant systems.
- Diagnostic facilities receive ₹15 per additional transaction above baseline levels (can accumulate significantly for high-volume labs).

### 2026 Regulatory Shift

In 2026, HIP (Health Information Provider) registration moved from voluntary to effectively mandatory:
- NABH 5th edition accreditation standards require HIP registration.
- State insurance empanelment (AB-PMJAY, state schemes, CGHS, ECHS) now requires HIP.

**Sources:**
- [ABDM Certification Guide 2026](https://qualysec.com/abdm-certification/)
- [ABDM Compliance for AB-PMJAY Hospitals 2026 | Lifemaan](https://www.lifemaan.com/blog/abdm-compliance-ab-pmjay-hospitals-2026-deadline/)
- [HFR and HPR: The Unsung Registries | Caladrius Health AI](https://caladriushealth.ai/blog/2026/06/18/HFR-and-HPR/)
- [Health Facility Registry (HFR) | ABDM](https://abdm.gov.in/health-facilities)
- [Information on HFR | National Portal of India](https://www.india.gov.in/information-health-facility-registry-hfr)

---

## 3. NABL Accreditation (NABL 112 / ISO 15189:2022)

**Status as of August 2026:** NABL 112A and 112B (aligned with ISO 15189:2022) are the current standards.

### Overview

NABL 112 is the Specific Criteria for Accreditation of Medical Laboratories, aligned with ISO 15189: Medical Laboratories – Requirements for Quality & Competence. NABL 112A provides interpretation guidance; NABL 112B provides a structured implementation approach. Accreditation is valid for 2 years with annual surveillance audits.

### Lab Information System (LIS/LMIS) Requirements

The DPDP Act and IT Act 2000/SPDI Rules require data security; NABL 112/ISO 15189:2022 add information management requirements specific to labs:

| Requirement | LIS/Lab Software Implication |
|---|---|
| **Audit Trails** | All user actions (login, data entry, result modification, report generation, deletion) must be logged with timestamp, user ID, and change description. Non-repudiation is critical. |
| **Data Integrity** | System must ensure results cannot be altered retroactively without audit trail visibility. Consider cryptographic signatures for authorized report signings. |
| **Report Formats** | Reports must be generated in a standardized format acceptable to referring physicians and patients. Lab software should support digital and paper formats. |
| **Authorized Signatories** | Only designated lab directors, pathologists, or technicians can approve/sign test results. System must enforce role-based access control and signatures (electronic or otherwise). |
| **Sample Retention & Record Retention** | Labs must define and document sample retention periods (typically 1–5 years depending on test type) and retain records of sample receipt, testing, and disposal. LIS must track sample lifecycle. |
| **Contingency Planning** | Labs must design a contingency plan (backup system, disaster recovery) to ensure results are communicated even in case of system failure. NABL requires documented continuity procedures. |
| **Quality Control** | LIS must support internal quality control (QC) schemes and external quality assessment (proficiency testing). System should track QC results over time and flag drift. |
| **Collection Centre Compliance** | If lab operates satellite collection centres, those facilities also must comply with ISO 15189 requirements; system must track specimen integrity, chain of custody from collection to lab. |

### Accreditation Process

1. **Scope Definition:** Lab defines which tests it will seek accreditation for.
2. **System Readiness:** Quality management system (QMS), LIS, SOPs, and personnel training aligned with ISO 15189/NABL 112.
3. **Audit:** NABL-appointed assessor conducts on-site evaluation.
4. **Certificate:** Valid for 2 years upon successful audit.
5. **Surveillance:** Annual audit to verify continued compliance.

**Sources:**
- [NABL 112: Medical Lab Accreditation Criteria](https://www.scribd.com/document/406585163/201902121156-NABL-112-doc)
- [NABL 112A Document | NABL India](https://nabl-india.org/nabl/file_download1.php?filename=202412180304-NABL-112-A-doc.pdf)
- [A Complete Guide to NABL 15189 Accreditation (2025) | Pranava Company Group](https://pranavacompany.com/blogs/complete-guide-nabl-15189-accreditation-implementation-compliance-2025)

---

## 4. Clinical Establishments (Registration and Regulation) Act 2010

**Status as of August 2026:** Adopted by 10+ states/UTs; state-specific implementation.

### Applicability

The Clinical Establishments (Registration and Regulation) Act, 2010 (administered by the Ministry of Health and Family Welfare) applies to diagnostic centers, laboratories, and pathology centers where pathological, bacteriological, genetic, radiological, chemical, biological investigations or other services are carried out.

### State/UT Coverage

**Adopting states/UTs (direct applicability):**
- Arunachal Pradesh, Bihar, Himachal Pradesh, Jharkhand, Mizoram, Rajasthan, Sikkim, Tripura, Uttarakhand, and all Union Territories (Delhi, Puducherry, etc.).

**States with equivalent laws:**
- Maharashtra (Nursing Home Registration Act).
- Karnataka (Karnataka Private Medical Establishments Act).
- Tamil Nadu (Tamil Nadu Clinical Establishment Act).
- Gujarat (equivalent state act).

For states with no adopted CEA Act, local clinical/nursing home registration laws apply.

### Registration Requirements for Diagnostic Centers

| Aspect | Requirement |
|---|---|
| **Registration Scope** | Per establishment, per category. Diagnostic center categories differ from clinic categories. |
| **Minimum Standards** | Facilities, equipment, personnel qualifications, hygiene, waste disposal, patient safety protocols. |
| **Record-Keeping** | Medical records, patient consent forms, staff credentials, equipment maintenance logs, and incident reports must be maintained per CEA standards and applicable state rules. |
| **Re-registration** | Typically renewable annually or biennially depending on state rules. |

### Additional Licenses Required for Diagnostic Centers

Beyond CEA registration:

1. **PC-PNDT Registration** (if offering ultrasound/imaging for sex determination screening).
2. **AERB License** (Atomic Energy Regulatory Board) — if using X-ray, CT, mammography, or other ionizing radiation equipment. Requires appointment of a Radiation Safety Officer.
3. **Biomedical Waste Authorization** — from State Pollution Control Board + tie-up with common biomedical waste treatment facility.
4. **NABL Accreditation** (optional but strongly encouraged for quality recognition).

### Penalties for Non-Compliance

- Fines: ₹10,000 to ₹5,00,000 depending on violation severity.
- Operational restrictions: Government may suspend operations.
- Criminal proceedings against owner/operator.
- Cancellation or suspension of registration.

**Sources:**
- [Clinical Establishment Registration in India: A Complete Guide | Turnkey Solutions](https://www.hospertz.com/clinical-establishments-act-registration-india/)
- [How to Start a Diagnostic Centre in India (2026) | Turnkey Solutions](https://www.hospertz.com/how-to-start-a-diagnostic-centre-in-india/)
- [Clinical Establishment Registration | Corpzo](https://www.corpzo.com/clinical-establishment-registration-legal-requirements-in-india)

---

## 5. CDSCO & Medical Device Rules 2017: Software as a Medical Device (SaMD)

**Status as of August 2026:** CDSCO draft guidance issued October 21, 2025, establishing regulatory pathways for medical device software.

### When Lab Software is a Medical Device

A software qualifies as a medical device under MDR 2017 **only if** it was intentionally developed for a medical purpose and meets the MDR definition. Generic LIMS used purely for workflow, data management, sample tracking, and reporting **is not** a medical device.

**SaMD status triggers** (requiring CDSCO registration):
- Software performs diagnostic interpretation (e.g., flags abnormal results, suggests diagnoses).
- Software drives clinical decision-making.
- Software provides patient monitoring or clinical support.

### Risk-Based Classification (Class A–D)

CDSCO uses a four-tier risk classification:

| Class | Risk Level | Example |
|---|---|---|
| **A** | Low risk | Generic data entry, simple logging. |
| **B** | Low-to-moderate risk | Administrative workflows, generic QC tracking. |
| **C** | Moderate-to-high risk | Software providing clinical decision support or preliminary flagging (not autonomous diagnosis). |
| **D** | High risk | Autonomous diagnosis, life-critical interpretation, or high-impact clinical decisions. |

Software embedded in hardware devices (SiMD) inherits the hardware's classification. **As of August 2026, no software has been classified as Class D.**

### Standards Compliance

SaMD must comply with standards prescribed by:
1. **Bureau of Indian Standards (BIS)** (if applicable).
2. **Central Government notified standards** (where available).
3. **ISO/IEC standards** (where no Indian standard exists) — e.g., ISO 13485 (medical device quality management), ISO 14971 (risk management), IEC 62304 (software lifecycle processes), IEC 80001 (network security), ISO/IEC 27001 (information security).
4. **Validated manufacturer standards** (if no recognized standard applies).

Key standards for lab software:
- **IEC 62304:** Software lifecycle and development processes.
- **ISO 14971:** Risk management.
- **ISO/IEC 27001:** Information security.
- **IEC 80001:** Network security (if cloud-based).
- **ISO/IEC 80059:** AI risk management (for AI/ML-assisted interpretation).

### Recent Guidance (October 2025)

CDSCO's draft guidance (S.O. 648(E), Feb 2020, formalized Oct 2025) clarifies:
- SaMD classification process.
- Regulatory approval pathways (simplified for low-risk).
- Post-marketing surveillance requirements.

Practical takeaway: A standard LMIS for sample tracking and reporting is **not** a regulated device. If your software interprets results or drives diagnoses, seek CDSCO classification before deployment.

**Sources:**
- [CDSCO Issues Guidance on Medical Device Software | Conventus Law](https://conventuslaw.com/report/india-cdsco-issues-guidance-on-medical-device-software-under-the-medical-devices-rules-2017/)
- [Medical Device Software: Has CDSCO Guidance Changed the Rules? | Cyril Amarchand Blogs](https://corporate.cyrilamarchandblogs.com/2026/01/medical-device-as-software-has-cdsco-guidance-changed-the-rules/)
- [SaMD Regulation in India: CDSCO Classification & Registration | Freyr](https://www.freyrsolutions.com/blog/samd-regulation-in-india-cdsco-classification-class-a-d-registration-requirements-emerging-market-strategy)

---

## 6. Pre-Conception and Pre-Natal Diagnostic Techniques (PC-PNDT) Act 1994

**Status as of August 2026:** Active enforcement; violations carry serious penalties.

### Scope & Applicability

The PC-PNDT Act, 1994 prohibits sex determination (sex selection) using prenatal diagnostic techniques. It applies to all diagnostic centers performing ultrasound, genetic counseling, or imaging on pregnant women.

### Record-Keeping Obligations

Diagnostic centers performing ultrasound on pregnant women must maintain:

| Record Type | Form | Requirement |
|---|---|---|
| **Patient Information Register** | (General) | Name, age, spouse's name, address, referring doctor, date of scanning, number of previous children and their genders. |
| **Patient Declaration Form** | Form F | Filled before every obstetric ultrasound (copy per patient). Must document that patient consented to procedure and that sex was not disclosed. |
| **Invasive Procedure Form** | Form G | If any invasive diagnostic (amniocentesis, chorionic villi sampling), filled and signed by patient and doctor. |
| **Equipment Log** | (General) | Record of all ultrasound/imaging machines, their serial numbers, and any shifts to another facility. |
| **Staff Credentials** | (General) | Qualifications of sonographers, technicians, doctors; training records. |

### Retention Period

- **Minimum 2 years** post-examination; longer if legal case is pending.
- Duplicate Form F: one submitted to Appropriate Authority, one retained at center.

### Display & Signage Requirements

- Prominent board (English + local language): "Sex selection and detection is **not** done at this Centre and is punishable under the PC-PNDT Act."
- Display a copy of the PC-PNDT Act at reception and ultrasound room.

### Penalties for Non-Compliance

- **Improper record-keeping** (e.g., Form F filled incorrectly or incompletely) → Suspension or cancellation of registration.
- **Sex determination disclosure** → Criminal prosecution, fines, imprisonment.
- **Operating without registration** → FIR, sealing of premises, loss of credibility.

**Real-world example (2026 enforcement):** In Patna, of 52 diagnostic centers inspected, 2 received FIRs, 2 were suspended for operating without registration, and 8 were served show-cause notices — highlighting active regulatory scrutiny.

### Lab Software Implication

Lab management software serving diagnostic centers with ultrasound must:
- Enforce Form F completion before every obstetric scan (workflow integration).
- Track 2-year retention via auto-archival or flagging.
- Generate audit reports for Appropriate Authority submissions.
- Prevent disclosure of fetal sex in any patient-facing report/interface.

**Sources:**
- [PC-PNDT Act: Understanding Provisions | M3India](https://www.m3india.in/contents/editor_pick/pc-pndt-act-understanding-its-provisions-and)
- [Implications of Incorrect Form F | MedN Law](https://mednlaw.com/form-f/)
- [The Ultimate Guide to PC-PNDT Act 1994 | Airacle Labs](https://airacle.in/blog/pcpndt-act-1994/)

---

## 7. Information Technology Act 2000 & SPDI Rules 2011

**Status as of August 2026:** Still in force but transitional; will be repealed by DPDP Act 2023 at a future notification date.

### Current Status & Applicability

The IT Act 2000 and Information Technology (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011 (SPDI Rules) are the current baseline for health data privacy in India **until the DPDP Act fully operationalizes and repeals SPDI Rules**. Until then, dual compliance with both DPDP and SPDI Rules is prudent.

### Health Data Under SPDI Rules

SPDI Rules classify health data as **Sensitive Personal Information** (SPI), including:
- Medical records and history.
- Physical, physiological, or mental health conditions.
- Biometric information.
- Sexual orientation.
- Genetic information.

### Key Obligations Under SPDI Rules

| Obligation | Requirement |
|---|---|
| **Applicability** | Applies to all bodies corporate (hospitals, clinics, diagnostic labs, health-tech platforms collecting/processing health data). |
| **Consent** | Consent is the sole ground for SPI collection. Must be informed, specific, and freely given. |
| **Privacy Policy** | Must publish a clear privacy policy disclosing data collection, processing, storage, sharing, and individual rights. |
| **Security Standards** | Must comply with ISO/IEC 27001 or an equivalent recognized standard. Implement encryption, access controls, audit logs, and data protection measures. |
| **Data Transfers** | SPI may be transferred outside India only where legally necessary (contract fulfillment) and with informed consent. Recipient must provide equivalent data protection. |
| **Individual Rights** | Individuals have rights to access, correct, and withdraw consent for data processing. |
| **Grievance Officer** | Entities must appoint a grievance officer to handle data subject complaints. |
| **Liability** | Non-compliance attracts civil liability for negligence; complainant can seek damages. |

### SPDI-Specific Gaps (Unresolved)

- No mandatory encryption benchmarks (only "reasonable" security required).
- No specific regulations for anonymized health data.
- No formal data breach notification timeline (unlike DPDP Act's 72-hour requirement).

### Relationship to DPDP Act

The DPDP Act 2023 introduces stricter requirements (250-crore penalties, 72-hour breach notification, explicit data minimization) than SPDI Rules. Once DPDP is fully notified (May 2027), SPDI Rules will be repealed. Until then, the more stringent of DPDP or SPDI Rules applies.

**Sources:**
- [Healthcare Data Privacy in India | India Law Offices](https://www.indialawoffices.com/legal-articles/healthcare-data-privacy-india)
- [SPDI Rules 2011: Securing Data | Singhania & Co](https://singhania.in/blog/spdi-rules-2011-taking-a-step-towards-securing-data)
- [At a Glance: Data Protection in India | Lexology](https://www.lexology.com/library/detail.aspx?g=8f0d53d3-2313-438b-ab0b-b19c2e306c78)

---

## 8. ICMR Guidelines: AI in Healthcare & Diagnostics

**Status as of August 2026:** ICMR Ethical Guidelines for AI (2023) are in force; no standalone AI regulation exists in India.

### ICMR Ethical Guidelines for AI (March 2023)

The Indian Council of Medical Research (ICMR) and Department of Health Research issued the Ethical Guidelines for Application of Artificial Intelligence in Biomedical Research and Healthcare, covering AI applications in diagnosis, screening, therapeutics, clinical decision-making, and public health surveillance.

### Key Requirements for Lab AI/Diagnostic Interpretation

| Requirement | Implication for Lab Software |
|---|---|
| **Intended Use Documentation** | If using AI for diagnostic interpretation, clearly document the intended scope (e.g., "assist in flagging abnormal blood chemistry"), intended user (lab technician, pathologist), and patient population. |
| **Risk Tiering** | ICMR mandates model risk tiering: low-risk (administrative automation), moderate-risk (clinical decision support), high-risk (autonomous diagnosis or life-critical functions). Design and validate accordingly. |
| **Prospective Validation** | Before deployment, conduct prospective clinical validation studies demonstrating the model's accuracy, sensitivity, specificity, and applicability to the target population. Retrospective validation alone is insufficient. |
| **Bias Assessment** | AI models must be evaluated for demographic biases (e.g., differences in accuracy across age, gender, ethnicity groups). Document findings and mitigation strategies. |
| **Post-Deployment Audit** | ICMR requires ongoing post-deployment monitoring and regular audits to detect performance drift, adverse events, or model degradation. Findings should be publicly disclosed. |
| **Accountability Framework** | Define accountability when AI-assisted diagnosis is incorrect: who is responsible (lab director, AI vendor, software provider)? Document this in SOPs. |
| **Transparency & Explainability** | AI-assisted results should be presented with confidence scores and interpretability (e.g., which test parameters drove the flag). Users should understand the AI's reasoning. |
| **Data Governance** | For AI models trained on patient data, ensure DPDP/SPDI compliance: consent, data minimization, retention policies, and audit trails. |
| **Professional Competence** | Lab staff using AI tools must be trained and competent in understanding AI outputs and limitations. AI should not replace human judgment. |

### Indian Regulatory Landscape (No Standalone AI Law)

As of August 2026, India has **no dedicated AI regulation**. The governing framework includes:
- **ICMR Ethical Guidelines (2023)** — non-binding but expected to be referenced in regulatory audits.
- **DPDP Act 2023** — applies to AI processing of personal data.
- **Telemedicine Practice Guidelines 2020** — AI cannot independently diagnose or prescribe; functions only as decision support under a registered medical practitioner.
- **CDSCO Medical Device Regulation** — AI/SaMD performing diagnosis may be classified as medical devices (see Section 5).

### Notable AI Diagnostics Deployed in India

Examples demonstrating compliance:
- **Qure.ai:** AI for tuberculosis detection from chest X-rays.
- **NIRAMAI:** AI thermal imaging for early breast cancer detection.
- **Cough Against TB:** AI for TB detection yield improvement (+12–16%).
- **MadhuNetrAI:** AI for diabetic retinopathy screening (14,000+ images across 11 states).

**Sources:**
- [ICMR Ethical Guidelines for AI in Healthcare | ICMR](https://www.icmr.gov.in/ethical-guidelines-for-application-of-artificial-intelligence-in-biomedical-research-and-healthcare)
- [ICMR's Ethical Principles for AI in Healthcare | NASSCOM](https://community.nasscom.in/communities/healthtech-and-life-sciences/icmrs-ethical-principles-ai-healthcare)
- [AI Ethics in Indian Healthcare (2026) | BMC Medical Ethics](https://link.springer.com/article/10.1186/s12910-026-01435-1)

---

## 9. GST & E-Invoicing Requirements

**Status as of August 2026:** Patient-facing diagnostic tests remain GST-exempt; e-invoicing applies only to taxable supplies.

### GST Status of Diagnostic Services

**Exempt from GST:**
- Diagnostic services (tests, imaging) performed by clinical establishments for patient diagnosis and treatment.
- Includes pathology tests, radiology, ultrasound, ECG, and other diagnostic procedures.
- Lab can issue a "bill of supply" (not a GST invoice) to patients.

**Taxable at 18% GST:**
- Wellness packages and preventive health checkup packages (not treatment).
- Commercial/non-clinical testing (forensic analysis, food quality testing, environmental testing, research services to pharma).
- Sample collection support services (collection outlet that only collects and forwards samples) classified as healthcare support, taxable at 18% under SAC 998599.
- Diagnostics through aggregator platforms (per AAR Karnataka ruling) — aggregators don't qualify for healthcare exemption.

### E-Invoicing Requirements

| Criterion | Requirement |
|---|---|
| **Threshold** | E-invoicing mandatory only for entities with annual aggregate turnover **above ₹5 crore**. |
| **Applicability** | Only for **taxable** supplies. Exempt diagnostic services do **not** require e-invoicing. |
| **For Exempt Labs** | Labs exclusively offering exempt diagnostic services do **not** need GST registration or e-invoicing. Billing via bill of supply is acceptable. |
| **Mixed Supply Labs** | If a lab offers both exempt (diagnostics) and taxable (wellness, commercial testing) services, it must register under GST, segregate supplies by category, and maintain separate records for Input Tax Credit (ITC) purposes. |

### Practical Lab Software Considerations

1. **Item-level tax classification:** Each service/product must have a defined tax status (exempt, 18%, etc.) in the billing system.
2. **Invoice vs. Bill of Supply:** System should auto-generate appropriate document type based on service taxability.
3. **Mixed-supply segregation:** If lab offers both exempt and taxable services, billing system must track and segregate for GST compliance and ITC claims.
4. **E-invoicing integration (if applicable):** If turnover > ₹5 crore and taxable supplies present, integrate e-invoicing API with the GST portal.

**Sources:**
- [GST on Lab Tests in India — Applicability and Exemptions | CAClub India](https://www.caclubindia.com/forum/gst-applicable-on-lab-test-610680.asp)
- [GST for Hospitals India 2026: Complete Guide | Adrine](https://www.adrine.in/blog/gst-for-hospitals-india-2026)
- [Diagnostic & Lab Aggregators Taxable at 18% GST | Tax Guru](https://taxguru.in/goods-and-service-tax/diagnostic-lab-aggregators-taxable-18-percent-gst-aar-karnataka.html)

---

## 10. Other Emerging / State-Specific Considerations

### Telemedicine Practice Guidelines 2020

- Applies if lab offers remote result consultations or AI-powered report interpretation.
- Lab must ensure that telemedicine platforms comply with confidentiality and data protection laws (DPDP, SPDI Rules, Telemedicine Guidelines).
- AI cannot independently diagnose; must function as decision support under a registered medical practitioner.

### State-Specific Clinical Establishments Acts

Several states have enacted their own clinical establishment acts (Maharashtra, Karnataka, Tamil Nadu, Gujarat) with varying registration timelines and fee structures. Verify your state's specific requirements.

### Biomedical Waste Management

Diagnostic centers must obtain authorization from the State Pollution Control Board and maintain tie-ups with common biomedical waste treatment facilities. Software may need to track waste disposal records.

### Radiation Safety (AERB License)

If lab uses ionizing radiation equipment (X-ray, CT, mammography), AERB license is mandatory. Appoint a Radiation Safety Officer; maintain equipment maintenance and safety logs.

---

## Summary of Top 5 Compliance Obligations for Lab Software

**Small and mid-sized diagnostic lab software must be designed to enforce these five critical compliance obligations by 2027:**

1. **DPDP Act 2023 Data Governance** — Implement explicit patient consent flows (integrating Consent Manager by Aug 2026), privacy policies, ISO/IEC 27001–level security (encryption, audit logs, access controls), breach notification procedures (72-hour reporting to DPBI), data retention/erasure mechanisms (balance NABL 2-year retention with patient erasure requests), and audit trails for all data access and modification. Penalties reach ₹250 crore for serious contraventions; active enforcement begins November 2026, with hard deadline May 13, 2027.

2. **NABL 112/ISO 15189 Audit & Data Integrity Controls** — Design immutable audit trails (timestamp, user ID, action, change details) for all lab operations; enforce role-based access control (authorized signatories only can approve results); implement sample lifecycle tracking (from collection through disposal) and two-year minimum record retention; support quality control scheme integration; and provide contingency/backup procedures documented and tested. These requirements are evaluated during NABL accreditation audits (2-year certificate with annual surveillance).

3. **ABDM Integration & HFR Registration** — Facilitate HFR registration (unique facility ID, patient ABHA login), support FHIR R4 data exchange (LOINC codes for lab results, SNOMED CT/ICD-10/11 terminology), manage patient consent for data sharing via ABDM Consent Manager, and prepare for WASA/CERT-In security audit (3–6 months pre-deployment). By 2027, ABDM integration is de facto mandatory for AB-PMJAY empanelment, state insurance access, and government tenders.

4. **PC-PNDT Compliance for Prenatal Diagnostics** — For centers offering ultrasound on pregnant women: enforce Form F completion before every obstetric scan (audit trail of forms), prevent fetal sex disclosure in any report interface, manage 2-year retention of duplicate Forms F and patient registers, and support submission to Appropriate Authority. Non-compliance invokes suspension or cancellation of facility registration.

5. **AI/SaMD Governance & ICMR Alignment (if deploying AI-assisted interpretation)** — If using AI for diagnostic result interpretation or flagging, document intended use, conduct prospective clinical validation studies, assess model bias across demographic groups, implement post-deployment performance monitoring and public reporting of audit findings, define accountability in SOPs, and ensure explainability (confidence scores, reasoning) to users. If AI is autonomous diagnosis-capable, seek CDSCO SaMD classification; maintain DPDP/SPDI compliance for any training data. ICMR guidelines are non-binding but expected to be referenced in regulatory audits and are de facto industry standard for AI-assisted diagnostics.

---

**Last Updated:** August 18, 2026

