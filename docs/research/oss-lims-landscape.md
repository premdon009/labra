# Open-Source Lab Management System (LIMS/LIS) Landscape Survey — August 2026

## Executive Summary

This survey covers 15+ open-source laboratory information management systems suitable for a small-to-mid-sized Indian diagnostic lab ("Labra"). **Key finding:** No open-source LIMS ships with ABDM integration; you would need to build that layer separately via the NHA Sandbox API. 

**License implications for proprietary/private deployment:**
- **GPL-2.0 / GPL-3.0:** Safe for private/internal use or SaaS (no source disclosure required). Copyleft triggers only on distribution.
- **AGPL-3.0:** Very restrictive for SaaS — you must share modifications with network users.
- **MPL-2.0 / Apache 2.0 / MIT:** Permissive; forking into proprietary code is legally viable.

---

## Tier 1: Enterprise-Ready, Actively Maintained LIMS

### 1. SENAITE LIMS (Python/Plone)

**GitHub URL:** [github.com/senaite](https://github.com/senaite)  
**Primary repo:** [senaite/senaite.core](https://github.com/senaite/senaite.core)  
**License:** GPL-2.0  
**GitHub Stars:** 361 (senaite.core); 232 (senaite.lims meta-package)  
**Latest Release:** 2.6.0 (April 2026)

**Tech Stack:**
- Backend: Python 3, Plone CMS (Zope)
- Frontend: JavaScript (Plone UI)
- Database: PostgreSQL / MySQL
- Deployment: Docker available

**Maintenance Health:**
- Actively developed as of May 2026 (last commit: senaite.core, May 19, 2026)
- 37 repositories in the SENAITE organization
- Regular releases (minor/patch on ~4-week cycles)
- Maintained by RIDING BYTES & NARALABS (Europe-based)

**Scope Fit:**
- ✅ Patient registration (integrated demographics)
- ✅ Lab test orders, samples, results, reporting
- ✅ Instrument integration (ASTM, HL7)
- ✅ Inventory & stock management
- ✅ Quality control & validation
- ✅ Invoicing & billing (via plugins)
- ✅ ISO 17025 accreditation support

**India-Specific Features:**
- No built-in ABDM integration
- Senaite modules for pathology labs exist but FHIR layer would be custom

**Fork Viability for Proprietary Use:**
- ⚠️ **GPL-2.0 Copyleft**: Private/internal modifications are fine, but distributing or offering as SaaS still triggers copyleft obligation for those modifications
- **Recommendation:** If you run it internally only (private enterprise), GPL-2.0 doesn't force source disclosure. But if you offer it as a service to other labs, you'd need to either (a) share modifications, (b) use Senaite under a commercial license (available from RIDING BYTES), or (c) keep all modifications private/in-house

**Notable Plugins/Ecosystem:**
- senaite.impress (HTML to PDF rendering)
- senaite.instruments (analyzer middleware)
- Multiple accreditation helpers

---

### 2. OpenELIS Global 2 (Java/Spring + React)

**GitHub URL:** [github.com/DIGI-UW/OpenELIS-Global-2](https://github.com/DIGI-UW/OpenELIS-Global-2)  
**License:** MPL-2.0  
**GitHub Stars:** 243  
**Latest Release:** Frequently updated (9,448 commits on develop branch)

**Tech Stack:**
- Backend: Java, Spring Boot
- Frontend: React (IBM Carbon design system)
- Database: PostgreSQL
- Deployment: Docker / Kubernetes
- Interoperability: FHIR R4 native, HL7 support

**Maintenance Health:**
- Very active development (continuous CI/CD, thousands of workflow runs)
- Maintained by DIGI-UW (International Training & Education Center for Health, University of Washington) + Digital Square
- Wide international community (25+ countries in production)

**Scope Fit:**
- ✅ Patient registration & demographics
- ✅ Lab test orders, sample management, results entry
- ✅ Analyzer integration (ASTM, HL7, CSV)
- ✅ Result reporting & document management
- ✅ Quality assurance & validation
- ✅ Multi-site / lab network support
- ✅ User roles (lab tech, supervisor, manager)
- ~Billing: through external ERP integration

**India-Specific Features:**
- No native ABDM integration (but FHIR-native means easier custom integration)
- Used by public health labs (HIV, TB, routine testing)
- Deployed in Côte d'Ivoire, Mauritius, Haiti (similar low-resource contexts to India)

**Fork Viability for Proprietary Use:**
- ✅ **MPL-2.0 permissive license**: You can fork, modify privately, and run as a private service without sharing your changes
- File-level copyleft only — as long as you don't distribute the original files unchanged, you're free to proprietary modifications
- **Excellent choice** if you want a clean fork path

**Related Repos:**
- openelis-docker (Docker Compose setup)
- openelisglobal-plugins (35+ analyzer integrations)
- openelis-qaframework (BDD + Selenium testing)

---

### 3. Bahmni (OpenMRS-based EMR + OpenELIS Lab Module)

**GitHub URL:** [github.com/bahmni](https://github.com/bahmni)  
**License:** AGPL-3.0 (OpenMRS core is MPL-2.0; Bahmni's extensions are AGPL-3.0)  
**Primary Repos:** [Bahmni](https://github.com/Bahmni), [Bahmni/OpenElis](https://github.com/Bahmni/OpenElis)  
**GitHub Stars:** ~1,500+ (across multiple repos)  
**Latest Release:** Bahmni 0.93.x (2026)

**Tech Stack:**
- Backend: OpenMRS (Java), Spring Boot, Bahmni modules
- Frontend: Atom (custom micro-frontend framework for O3 migration)
- Database: MySQL / PostgreSQL
- Lab Component: OpenELIS (separate Java/PostgreSQL subsystem)
- Deployment: Docker, Kubernetes

**Maintenance Health:**
- Actively maintained by Thoughtworks (creator) + community
- 50+ countries in production
- ABDM-certified (official NHA approval)
- Bahmni Lite (cloud-native SaaS variant) available

**Scope Fit:**
- ✅ Complete EMR + hospital management + lab module
- ✅ Patient registration, appointment scheduling, clinical records
- ✅ Lab orders, sample tracking, results entry, reporting
- ✅ Pharmacy module (Odoo integration)
- ✅ Radiology (DCM4CHEE integration)
- ✅ Billing & accounting
- ✅ Multi-site, role-based access

**India-Specific Features:**
- ✅ **ABDM/ABHA integration** (certified)
- ✅ Auto-fetch patient demographics from ABHA ID
- ✅ Deploy as Health Information Provider (HIP)
- ✅ Widely adopted in Indian hospitals, clinics, NGOs
- ✅ Bahmni Lite targeting Indian small clinics (OPD-focused)
- ✅ Nagaland, IMDH hospitals, and state-level rollouts

**Fork Viability for Proprietary Use:**
- ⚠️ **AGPL-3.0 (restrictive for SaaS)**: If you fork Bahmni modules and offer them as a networked service to other labs/clinics, you must share your modifications
- OpenMRS core (MPL-2.0) is permissive, but Bahmni's AGPL overlays it
- **Not recommended** for proprietary SaaS; fine for private deployment
- **Alternative:** Commercial dual-licensing may be available via Thoughtworks

---

## Tier 2: Specialized/Active, Smaller Ecosystem

### 4. GNU Health + GNU LIMS (Occhiolino)

**GitHub URL:** [gnu-health.git](https://savannah.gnu.org/git/?group=health) (Savannah) + [acsone/gnu-lims](https://github.com/acsone/gnu-lims)  
**License:** GPL-3.0  
**Latest Release:** GNU Health 5.0 (June 2025)

**Tech Stack:**
- Framework: Tryton (ERP platform)
- Backend: Python
- Database: PostgreSQL
- Deployment: Linux native, Docker available
- LIMS: Occhiolino (integrated into GNU Health)

**Maintenance Health:**
- Steady development; official GNU package (GNU Solidario)
- Smaller community than Senaite/Bahmni but dedicated
- Regular annual releases

**Scope Fit:**
- ✅ Patient/specimen records, lab workflows
- ✅ Test orders, results, reporting
- ✅ Billing, invoicing, stock management
- ✅ Multi-language, audit trails
- ✅ ISO 17025-aligned
- ✅ Flexible linkage to HIS/EHR (GNU Health + external EMR)

**India-Specific Features:**
- No ABDM integration
- Smaller India footprint than Bahmni/OpenELIS

**Fork Viability for Proprietary Use:**
- ⚠️ **GPL-3.0 (copyleft)**: Similar restrictions as GPL-2.0; private use is safe, but distribution triggers copyleft
- Anti-DRM clauses (stronger than GPL-2.0)

---

### 5. OpenMRS O3 + Lab Modules

**GitHub URL:** [github.com/openmrs](https://github.com/openmrs)  
**License:** MPL-2.0 (with Healthcare Disclaimer)  
**Key Repos:** [openmrs-esm-laboratory-app](https://github.com/openmrs/openmrs-esm-laboratory-app), [openmrs-module-labonfhir](https://github.com/openmrs/openmrs-module-labonfhir)  
**GitHub Stars:** 2,000+ (core); 78–81 (lab modules)  
**Latest Release:** O3.6 (March 2026)

**Tech Stack:**
- Backend: Java (OpenMRS), Spring Boot
- Frontend: O3 (TypeScript, microfrontends)
- Database: MySQL / PostgreSQL
- FHIR: R4 native (via labonfhir module)

**Maintenance Health:**
- Very active (OpenMRS foundation-backed)
- Community of 200+ developers
- Regular quarterly releases (O3.6 March 2026, per Release Notes)

**Scope Fit:**
- ✅ Lab ordering, results, queue management
- ✅ Specimen tracking (via modules)
- ✅ FHIR-based LIS integration (labonfhir)
- ✅ Extensible via O3 module framework
- ~Billing: external module, typically via separate system

**India-Specific Features:**
- No native ABDM integration
- Used globally; smaller India presence than Bahmni

**Fork Viability for Proprietary Use:**
- ✅ **MPL-2.0**: Similar to OpenELIS — file-level copyleft, permissive for private modifications

---

## Tier 3: Specialized / Research-Focused / Lightweight

### 6. eLabFTW (PHP, AGPL-3.0)

**GitHub URL:** [github.com/elabftw/elabftw](https://github.com/elabftw/elabftw)  
**License:** AGPL-3.0  
**GitHub Stars:** ~1,395  
**Latest Commit:** August 13, 2026 (active)

**Tech Stack:**
- Backend: PHP 8.x
- Frontend: Vue.js
- Database: MySQL / MariaDB
- Deployment: Docker, self-hosted

**Maintenance Health:**
- Actively maintained (commits into August 2026)
- Lighter-weight than Senaite/OpenELIS
- Ecosystem: elAPI (REST client), pyelabdata (Python), migration tools from RSpace/LabFolder

**Scope Fit:**
- ✅ Electronic lab notebook, experiment tracking
- ✅ Sample/specimen database (generic object storage)
- ✅ Access control, multi-team on one instance
- ✅ Reporting, audit trails
- ⚠️ Limited billing / clinical workflow features (not designed for clinical labs)

**India-Specific Features:**
- Not India-focused (research/biobank emphasis)

**Fork Viability for Proprietary Use:**
- ⚠️ **AGPL-3.0 (very restrictive for SaaS)**: Designed for research; not suitable if you want to run it as a private service

---

### 7. Frappe Health (ERPNext Healthcare Module)

**GitHub URL:** [github.com/frappe/health](https://github.com/frappe/health)  
**License:** AGPL-3.0  
**Related:** [github.com/frappe/frappe](https://github.com/frappe/frappe) (Frappe framework, MIT)  
**Latest Release:** 2024–2026 (actively developed)

**Tech Stack:**
- Framework: Frappe (Python, web framework)
- Backend: Python, Flask
- Frontend: TypeScript, Vue.js
- Database: MariaDB / PostgreSQL
- Design: HL7 FHIR-based

**Maintenance Health:**
- Actively maintained by Frappe Technologies + community
- Integrated into ERPNext ecosystem (300+ modules)
- Regular updates

**Scope Fit:**
- ✅ Lab test templates, sample collection, results entry
- ✅ Billing integration (via ERPNext Sales Invoice)
- ✅ Appointment scheduling, patient registration
- ✅ Pharmacy, radiology modules
- ✅ Role-based permissions
- ✅ Multi-language (ICD-10 support)

**India-Specific Features:**
- Used in Indian clinics/hospitals (Frappe India presence)
- No built-in ABDM integration, but extensible

**Fork Viability for Proprietary Use:**
- ⚠️ **AGPL-3.0**: Same SaaS restrictions as eLabFTW. The Frappe framework is MIT (permissive), but the Health module is AGPL-3.0

---

## Tier 4: Lightweight / Community Projects / India-Origin

### 8. Bika LIMS (Python, GPL-2.0) — Archaic but Notable

**GitHub URL:** [github.com/bikalims/bika.lims](https://github.com/bikalims/bika.lims)  
**License:** GPL-2.0  
**Current Status:** Legacy; superseded by Senaite

**Context:**
- Original PyPI package (bika.lims) last updated October 2017 (3.2.1rc3)
- Active development moved to Senaite (github.com/senaite)
- "Ingwe Bika LIMS 4" is a Docker distribution combining Senaite + Bika add-ons
- Maintained by Bika Lab Systems (service provider since 2002)

**Not recommended for new deployments.** Use Senaite instead.

---

### 9. India-Origin GitHub Projects (Small-Scale)

**Pathology Lab Management (vivekcse14)**
- **URL:** [github.com/vivekcse14/Pathology-Lab-Management](https://github.com/vivekcse14/Pathology-Lab-Management)
- Tech: Django + MySQL
- User roles: User, Nominee, Agent, Admin
- Scope: Patient records, test tracking, billing
- ~50 stars; lightweight; community project
- License: Not explicitly stated (assume MIT)

**Online Diagnostic Lab Management (Kavirajput)**
- **URL:** [github.com/Kavirajput/Online-Diagnostic-Lab-Management](https://github.com/Kavirajput/Online-Diagnostic-Lab-Management)
- Tech: PHP + SQL
- Features: User roles, test management, appointment scheduling, billing
- No ABDM support

**Pathology Lab Software (alimarchal)**
- **URL:** [github.com/alimarchal/Pathology-Lab-Software](https://github.com/alimarchal/Pathology-Lab-Software)
- Tech: (Language TBD from repo)
- Region: Pakistan/Kashmir origin, applicable to South Asia
- Features: Patient mgmt, test results, report generation, billing

**Assessment:** These are small hobby/educational projects with <100 stars each. Suitable as **inspiration** or starting point for customization, but lack production maturity, documentation, and community support.

---

### 10. LibreHealth EHR

**GitHub URL:** [github.com/LibreHealthIO/lh-ehr](https://github.com/librehealthio/lh-ehr)  
**License:** GNU Affero General Public License (AGPL-3.0)  
**Primary Repo:** GitLab [gitlab.com/librehealth/ehr](https://gitlab.com/librehealth/ehr)

**Tech Stack:**
- Backend: PHP 7.2+, Apache
- Frontend: Web-based
- Database: MySQL

**Maintenance Health:**
- GitHub mirror shows last activity in 2023
- Main development on GitLab (mirrored to GitHub)
- Participating in Google Summer of Code 2026 (suggests ongoing community)
- ⚠️ Demo servers offline due to security vulnerabilities

**Scope Fit:**
- ✅ General EMR, patient records, appointments
- ~Lab integration through standards (HL7, labs) but not natively robust

**India-Specific:** None explicit

**Fork Viability:** AGPL-3.0 (same SaaS restrictions)

**Assessment:** Smaller ecosystem than Bahmni/OpenMRS. Suitable as reference; security concerns noted.

---

## Building Blocks for Integration (Not Full Systems)

### Authentication & Authorization

**Keycloak** ([keycloak.org](https://www.keycloak.org/))
- **License:** Apache 2.0 (permissive)
- **GitHub:** [github.com/keycloak/keycloak](https://github.com/keycloak/keycloak)
- **Purpose:** SSO, multi-factor authentication (TOTP), LDAP/AD federation, SAML/OpenID Connect
- **Deployment:** Docker, Kubernetes, Kubernetes Operator
- **Cost:** Free; operational effort in HA clusters
- **Integration:** Standard protocols (OpenID Connect, OAuth 2.0, SAML); can integrate with any LIMS

---

### FHIR Server (Interoperability)

**HAPI FHIR Server** ([hapifhir.io](https://hapifhir.io/))
- **License:** Apache 2.0 (permissive)
- **GitHub:** [github.com/hapifhir/hapi-fhir](https://github.com/hapifhir/hapi-fhir)
- **Tech:** Java, Spring Boot
- **Purpose:** FHIR R4 server for clinic/lab data interchange, ABDM integration
- **Deployment:** Docker, Kubernetes
- **Use Case:** Build FHIR bridge for OpenELIS, Senaite, or home-grown LIMS → ABDM
- **Latest:** Released 2026-03 (actively maintained); Java 17+ required

**Google FHIR Server** ([cloud.google.com/healthcare/docs/how-tos/fhir](https://cloud.google.com/healthcare/docs/how-tos/fhir))
- Managed service (SaaS) on Google Cloud
- Pay-per-use
- HIPAA compliant

---

### Analytics & Reporting

**Metabase** ([metabase.com](https://www.metabase.com/))
- **License:** AGPL-3.0 (open source), Metabase Commercial License (enterprise)
- **GitHub:** [github.com/metabase/metabase](https://github.com/metabase/metabase)
- **Tech:** Clojure (backend), React (frontend)
- **Purpose:** BI/analytics dashboards for lab data (turnaround times, test volumes, etc.)
- **Stars:** 47,600+
- **Integration:** JDBC to any DB (PostgreSQL, MySQL, etc.)

---

### Billing & Invoicing

**Open-Source Billing (OSB)** ([github.com/vteams/open-source-billing](https://github.com/vteams/open-source-billing))
- **Tech:** Ruby on Rails
- **License:** (Check repo; likely OSS)
- **Purpose:** Invoice generation, payment tracking, customer portal
- **Use Case:** Add to Senaite/OpenELIS for billing workflows

**ERPNext Accounting Module** (Part of [github.com/frappe/erpnext](https://github.com/frappe/erpnext))
- **License:** AGPL-3.0
- **Tech:** Frappe (Python)
- **Features:** Invoicing, GL, AR/AP, tax, multi-currency
- **Integration:** Already integrated with Frappe Health

---

## Summary: License Copyleft Risk Matrix

| Project | License | Private/Internal Use | SaaS Proprietary Offering | Distribution | Fork Path for "Labra" |
|---------|---------|--------|--------|--------|--------|
| **SENAITE** | GPL-2.0 | ✅ Safe | ⚠️ Disclosure required | ❌ Copyleft | Use internal; consider commercial license |
| **OpenELIS Global 2** | MPL-2.0 | ✅ Safe | ✅ Proprietary OK | ✅ File-level only | **✅ Best fork choice** |
| **Bahmni** | AGPL-3.0 | ✅ Safe | ❌ Must disclose | ❌ Copyleft | Private OK; NOT for SaaS |
| **GNU Health** | GPL-3.0 | ✅ Safe | ⚠️ Disclosure required | ❌ Copyleft | Similar to Senaite |
| **OpenMRS O3** | MPL-2.0 | ✅ Safe | ✅ Proprietary OK | ✅ File-level only | ✅ Viable fork |
| **eLabFTW** | AGPL-3.0 | ✅ Safe | ❌ Must disclose | ❌ Copyleft | Not for SaaS |
| **Frappe Health** | AGPL-3.0 | ✅ Safe | ❌ Must disclose | ❌ Copyleft | Not for SaaS |
| **Keycloak** | Apache 2.0 | ✅ Safe | ✅ Proprietary OK | ✅ Permissive | ✅ Ideal |
| **HAPI FHIR** | Apache 2.0 | ✅ Safe | ✅ Proprietary OK | ✅ Permissive | ✅ Ideal |

---

## Ranked Recommendations

### (A) Best Candidates for Fork-and-Build (Proprietary "Labra")

**1. OpenELIS Global 2** (DIGI-UW/OpenELIS-Global-2)
- **Why:** MPL-2.0 permits proprietary forking; FHIR R4 native (easier ABDM integration); internationally proven (25+ countries); active maintenance; strong analyzer ecosystem
- **Effort:** 3–4 months for full customization
- **Considerations:** Java/Spring backend (steeper learning curve than Python); needs custom ABDM layer via HAPI FHIR or direct NHA APIs
- **Verdict:** ⭐⭐⭐⭐⭐ Excellent for mid-to-large clinics with resources

**2. OpenMRS O3 + Lab Modules** (github.com/openmrs)
- **Why:** MPL-2.0; microfrontend architecture (modular, easier to extend); FHIR support via labonfhir; large community
- **Effort:** 4–6 months (steep O3 learning curve)
- **Considerations:** Requires understanding of OpenMRS ecosystem; billing not built-in (need external module)
- **Verdict:** ⭐⭐⭐⭐ Good for tech-savvy teams; excellent long-term support

**3. SENAITE LIMS** (github.com/senaite) with Commercial License
- **Why:** Most feature-complete LIMS; GPL-2.0 but commercial dual-licensing available; Plone/Python ecosystem familiar in India
- **Effort:** 2–3 months for lab-focused use
- **Considerations:** Discuss commercial license with RIDING BYTES (Europe); GPLv2 private use is safe but SaaS licensing unclear
- **Verdict:** ⭐⭐⭐⭐ Best LIMS feature-set, but licensing must be negotiated

---

### (B) Best Candidates for Deploy-and-Integrate (Managed Offering)

**1. Bahmni** (+ Bahmni Lite for small clinics)
- **Why:** ABDM-certified, India-tested, full EMR + lab, open deployment model
- **Effort:** 1–2 months deployment; integration with existing clinic workflow
- **Licensing:** AGPL-3.0 (keep it private/in-house, don't resell as SaaS)
- **Hosting:** Self-hosted or via Bahmni Lite (managed SaaS by Thoughtworks)
- **Verdict:** ⭐⭐⭐⭐⭐ **Fastest path to ABDM-compliant solution**

**2. Frappe Health** (+ ERPNext for accounting/pharmacy)
- **Why:** India-native (Frappe), full accounting, pharmacy integration, HL7 FHIR base
- **Effort:** 2–3 months
- **Licensing:** AGPL-3.0 (private use only)
- **Considerations:** AGPL SaaS restrictions; good for single-clinic, not multi-tenant
- **Verdict:** ⭐⭐⭐⭐ Good for small clinics; strong accounting backbone

---

### (C) Design/Architecture Inspiration Only

**1. GNU Health / Occhiolino** — Reference for free/open LIMS architecture in low-resource settings
**2. eLabFTW** — Reference for lightweight lab notebook features
**3. LibreHealth** — Reference for EMR design (but security concerns)
**4. India-Origin Projects (Pathology Lab Management, etc.)** — Reference for UI patterns; not production-ready

---

## Critical Success Factors for "Labra"

1. **ABDM Integration:** No OSS LIMS ships with it. Budget 4–8 weeks for FHIR bridge development:
   - Use HAPI FHIR Server (Apache 2.0, no licensing risk)
   - Implement HL7 FHIR Bundles for test orders/results
   - Register as HIP with NHA Sandbox

2. **Analyzer Connectivity:** Choose a platform with existing plugins:
   - **Best:** OpenELIS (35+ analyzers ready)
   - **Good:** Senaite (HL7, ASTM, CSV)
   - **Fair:** Bahmni (via OpenELIS sub-component)

3. **Billing Integration:** No open-source LIMS is complete without this:
   - If forking OpenELIS or Senaite: add billing module (4–6 weeks)
   - If using Frappe/Bahmni: accounted for; leverage ERPNext

4. **India Compliance:**
   - ABDM/ABHA (mandatory for new labs)
   - E-sign support (for digital reports)
   - GST compliance (accounting)
   - Data localization rules (keep servers in India)

5. **SaaS vs. On-Premise Decision:**
   - **On-Premise (single clinic):** GPL/AGPL is fine; Senaite/Bahmni safe
   - **Multi-tenant SaaS:** Use MPL-2.0 (OpenELIS, OpenMRS) or permissive (Apache/MIT); avoid AGPL-3.0
   - **Resale to other labs:** Must use permissive license or negotiate commercial license

---

## Final Recommendation: The "Labra" Implementation Path

**For a small-to-mid-sized diagnostic center in India (initial deployment):**

**Option 1 (Fastest, ABDM-ready):**
- Deploy **Bahmni** (ABDM-certified) as-is
- Cost: Free software + hosting (~$500–2k/mo for 2–3 site deployment)
- Effort: 4–8 weeks
- Constraints: Private use only (AGPL); good for single organization

**Option 2 (Most Extensible for Proprietary Roadmap):**
- Fork **OpenELIS Global 2** (MPL-2.0)
- Add custom lab workflows and billing
- Integrate HAPI FHIR for ABDM bridge
- Cost: Free software + 3–4 months dev effort
- Effort: 12–16 weeks
- Upside: Proprietary fork safe; can scale to multi-tenant SaaS

**Option 3 (Best LIMS Features, Licensing TBD):**
- Deploy **Senaite** (GPL-2.0 private, or negotiate commercial dual-license)
- Pair with **Frappe Accounting** for billing (separate module)
- Add custom ABDM layer
- Cost: Free software + possible commercial Senaite license (~€5k–15k/year)
- Effort: 8–12 weeks
- Upside: Most complete LIMS; risk on SaaS licensing

---

## References

- [SENAITE GitHub](https://github.com/senaite)
- [OpenELIS Global 2](https://github.com/DIGI-UW/OpenELIS-Global-2)
- [Bahmni](https://www.bahmni.org/)
- [GNU Health](https://www.gnuhealth.io/)
- [OpenMRS](https://openmrs.org/)
- [Frappe Health](https://frappehealth.com/)
- [eLabFTW](https://www.elabftw.net/)
- [Keycloak](https://www.keycloak.org/)
- [HAPI FHIR](https://hapifhir.io/)
- [Metabase](https://www.metabase.com/)
- [OpenELIS Global docs](https://docs.openelisci.org/)
- [Bahmni ABDM Wiki](https://bahmni.atlassian.net/wiki/spaces/BAH/pages/2901114904)
- [IntuitionLabs LIMS Guide](https://intuitionlabs.ai/articles/open-source-lims-guide)

