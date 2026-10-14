"""Made-up documents for the letterhead preview, so margins can be checked against short,
long and multi-page content before anything real is printed. All names are invented."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Sample:
    code: str
    label: str
    template: str
    data: dict[str, Any]


def _row(name: str, result: str, unit: str, range_: str) -> dict[str, str]:
    return {"name": name, "result": result, "unit": unit, "range": range_}


_CBC = [
    _row("Haemoglobin", "13.2", "g/dL", "13.0 - 17.0"),
    _row("Total leucocyte count", "7.4", "10^3/µL", "4.0 - 10.0"),
    _row("Platelet count", "245", "10^3/µL", "150 - 410"),
    _row("RBC count", "4.8", "10^6/µL", "4.5 - 5.5"),
    _row("PCV", "41.0", "%", "40 - 50"),
    _row("MCV", "86.0", "fL", "83 - 101"),
]
_LIPID = [
    _row("Total cholesterol", "182", "mg/dL", "< 200"),
    _row("Triglycerides", "140", "mg/dL", "< 150"),
    _row("HDL cholesterol", "46", "mg/dL", "> 40"),
    _row("LDL cholesterol", "108", "mg/dL", "< 100"),
]


def _patient(name: str, referrer: str) -> dict[str, Any]:
    return {
        "patient": name,
        "patient_no": "P-000123",
        "age_sex": "42 Y / F",
        "referrer": referrer,
        "signatory": "Dr. Sample Signatory, MD (Pathology)",
    }


def _short() -> dict[str, Any]:
    return _patient("Asha Testcase", "Dr. Ref Example") | {
        "panels": [{"name": "Complete blood count", "rows": _CBC}]
    }


def _three_pages() -> dict[str, Any]:
    panels = [
        {"name": f"{name} ({n})", "rows": rows}
        for n in range(1, 6)
        for name, rows in (("Complete blood count", _CBC), ("Lipid profile", _LIPID))
    ]
    return _patient("Asha Testcase", "Dr. Ref Example") | {"panels": panels}


def _long_names() -> dict[str, Any]:
    rows = [
        _row("Glycated haemoglobin (HbA1c), high performance liquid chromatography", "5.6", "%",
             "Non-diabetic: < 5.7; prediabetic: 5.7 - 6.4; diabetic: >= 6.5"),
        _row("Thyroid stimulating hormone, ultrasensitive (third generation)", "2.1", "µIU/mL",
             "0.27 - 4.20"),
    ]  # fmt: skip
    return _patient(
        "अनन्या लक्ष्मीनारायण वेंकटरमण सुब्रह्मण्यम (Ananya Lakshminarayana Testcase)",
        "डॉ. उदाहरण संदर्भ (Dr. Referrer With A Very Long Example Name)",
    ) | {"panels": [{"name": "दीर्घ नाम / Long names", "rows": rows}]}


def _bill() -> dict[str, Any]:
    lines = [
        {"name": f"Synthetic test {n:02d}", "amount": f"₹{100 + n * 10:,}.00"} for n in range(1, 26)
    ]
    total = sum(100 + n * 10 for n in range(1, 26))
    return {
        "bill_no": "B2/B/2627/000042",
        "patient": "Asha Testcase",
        "lines": lines,
        "total": f"₹{total:,}.00",
        "signatory": "Front desk",
    }


SAMPLES = {
    s.code: s
    for s in (
        Sample("short", "Short report (1 page)", "pdf/sample_report.html", _short()),
        Sample("three_pages", "Long report (3 pages)", "pdf/sample_report.html", _three_pages()),
        Sample("long_names", "Long names in Hindi", "pdf/sample_report.html", _long_names()),
        Sample("bill", "Bill with 25 lines", "pdf/sample_bill.html", _bill()),
    )
}
# Which samples the editor offers for each document kind, the first being the default.
FOR_KIND = {
    "report_a4": ("short", "three_pages", "long_names"),
    "bill_a4": ("bill",),
}
