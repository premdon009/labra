"""The units a parameter may use: UCUM codes, each with the label printed on reports.

A picklist, not free text, so a typo like `mgs/dl` can't reach a report (§1d). Add a unit here
when a lab needs one; the code must be valid UCUM (https://ucum.org).
"""

UNITS: dict[str, str] = {
    "mg/dL": "mg/dL",
    "g/dL": "g/dL",
    "mg/L": "mg/L",
    "ug/dL": "µg/dL",
    "ng/dL": "ng/dL",
    "ng/mL": "ng/mL",
    "pg/mL": "pg/mL",
    "mmol/L": "mmol/L",
    "umol/L": "µmol/L",
    "mEq/L": "mEq/L",
    "U/L": "U/L",
    "u[IU]/mL": "µIU/mL",
    "m[IU]/mL": "mIU/mL",
    "%": "%",
    "fL": "fL",
    "pg": "pg",
    "/uL": "cells/µL",
    "10*3/uL": "×10³/µL",  # noqa: RUF001  the printed multiplication sign
    "10*5/uL": "lakh/µL",
    "10*6/uL": "×10⁶/µL",  # noqa: RUF001
    "mm/h": "mm/h",
    "mL/min/{1.73_m2}": "mL/min/1.73 m²",
    "s": "seconds",
    "min": "minutes",
    "mm": "mm",
    "cm": "cm",
    "kg": "kg",
    "kg/m2": "kg/m²",
    "mm[Hg]": "mmHg",
    "{s_co_ratio}": "S/Co",
    "{ratio}": "ratio",
    "{titre}": "titre",
}


def label(code: str) -> str:
    """The printed label for a unit code; blank for a unitless parameter."""
    return UNITS.get(code, code)
