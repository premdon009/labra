"""Made-up documents for the letterhead preview, so margins can be checked against short,
long and multi-page content before anything real is printed. The reports use the real
report template. All names are invented."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from labra.printing.letterhead import NO_RESERVE, PageSpec, compose
from labra.printing.pdf import FileReader, Rendered
from labra.printing.reportpage import TEMPLATE as REPORT
from labra.printing.reportpage import barcode, compose_report, qr
from labra.printing.templates import render_html


@dataclass(frozen=True)
class Sample:
    code: str
    label: str
    template: str
    data: dict[str, Any]


def _row(name: str, result: str, unit: str, range_: str, flag: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "calc": False,
        "result": result,
        "flag": flag,
        "unit": unit,
        "range": range_,
        "note": "",
        "text_only": False,
    }


_CBC = [
    _row("Haemoglobin", "13.2", "g/dL", "13.0 - 17.0"),
    _row("Total leucocyte count", "7.4", "10³/µL", "4.0 - 10.0"),
    _row("Platelet count", "132", "10³/µL", "150 - 410", "L"),
    _row("RBC count", "4.8", "10⁶/µL", "4.5 - 5.5"),
    _row("PCV", "41.0", "%", "40 - 50"),
    _row("MCV", "86.0", "fL", "83 - 101"),
]
_LIPID = [
    _row("Total cholesterol", "182", "mg/dL", "< 200"),
    _row("Triglycerides", "140", "mg/dL", "< 150"),
    _row("HDL cholesterol", "46", "mg/dL", "> 40"),
    _row("LDL cholesterol", "108", "mg/dL", "< 100", "H") | {"calc": True},
]
_ALLERGENS = [
    _row(f"Synthetic allergen {n:02d}", f"0.{n:02d}", "kU/L", "< 0.35") for n in range(1, 25)
]


def _panel(key: str, name: str, rows: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "specimen": "Serum",
        "sample_no": "2627-000123",
        "remarks": "",
        "method": "",
        "research": False,
        "outside": None,
        "attached": None,
        "rows": rows,
        "tiers": [],
        "critical": [],
        "interpretation": "",
    } | extra


def _report(name: str, referrer: str, departments: list[dict[str, Any]]) -> dict[str, Any]:
    """A made-up report in the shape `labra.reports.content.view` gives the template."""
    return {
        "preview": False,
        "title": "Laboratory report",
        "amended": None,
        "reference": "Report B2/R/2627/000123 v1",
        "header": {
            "name": "Sample Diagnostics",
            "lines": ["Main Lab", "1 Example Road, Sampletown"],
        },
        "patient": {"name": name, "patient_no": "P-000123", "age_sex": "42 Y / F"},
        "visit": {
            "visit_no": "B2/V/2627/000123",
            "branch": "Branch 2",
            "referrer": referrer,
            "collected": "14 Oct 2026 08:50",
            "received": "14 Oct 2026 10:05",
            "reported": "14 Oct 2026 15:00",
        },
        "barcode": barcode("B2/V/2627/000123"),
        "qr": qr("Report B2/R/2627/000123 v1 0123456789abcdef"),
        "nabl": "",
        "departments": departments,
        "show_reference": True,
        "partial": False,
        "pending": [],
        "outside": [],
        "separately": [],
        "attachments": [],
        "research": False,
        "selected": "",
        "signatory": {
            "name": "Signatory Name",
            "qualification": "MD (Pathology)",
            "council_reg_no": "XMC 00000",
            "signature": "",
        },
        "footer_text": "Results relate only to the sample received.",
    }


def _short() -> dict[str, Any]:
    cbc = _panel("cbc", "Complete blood count", _CBC, specimen="EDTA whole blood")
    return _report("Patient Name", "Referring Doctor", [{"name": "Haematology", "panels": [cbc]}])


def _three_pages() -> dict[str, Any]:
    haematology = [
        _panel(f"cbc{n}", f"Complete blood count ({n})", _CBC, specimen="EDTA whole blood")
        for n in range(1, 3)
    ]
    biochemistry = [_panel(f"lipid{n}", f"Lipid profile ({n})", _LIPID) for n in range(1, 3)]
    immunology = [_panel("allergy", "Allergy screen (made up)", _ALLERGENS)]
    return _report(
        "Patient Name",
        "Referring Doctor",
        [
            {"name": "Haematology", "panels": haematology},
            {"name": "Biochemistry", "panels": biochemistry},
            {"name": "Immunology", "panels": immunology},
        ],
    )


def _long_names() -> dict[str, Any]:
    rows = [
        _row("Glycated haemoglobin (HbA1c), high performance liquid chromatography", "5.6", "%",
             "Non-diabetic: < 5.7; prediabetic: 5.7 - 6.4; diabetic: ≥ 6.5"),
        _row("Thyroid stimulating hormone, ultrasensitive (third generation)", "2.1", "µIU/mL",
             "0.27 - 4.20"),
    ]  # fmt: skip
    panel = _panel("long", "दीर्घ नाम / Long names", rows)
    return _report(
        "रोगी का बहुत लंबा पूरा नाम यहाँ (Patient With A Very Long Full Name Here)",
        "डॉ. उदाहरण संदर्भ (Dr. Referrer With A Very Long Example Name)",
        [{"name": "Biochemistry", "panels": [panel]}],
    )


def _bill() -> dict[str, Any]:
    lines = [
        {"name": f"Synthetic test {n:02d}", "amount": f"₹{100 + n * 10:,}.00"} for n in range(1, 26)
    ]
    total = sum(100 + n * 10 for n in range(1, 26))
    return {
        "bill_no": "B2/B/2627/000042",
        "patient": "Patient Name",
        "lines": lines,
        "total": f"₹{total:,}.00",
        "signatory": "Front desk",
    }


SAMPLES = {
    s.code: s
    for s in (
        Sample("short", "Short report (1 page)", REPORT, _short()),
        Sample("three_pages", "Long report (3 pages)", REPORT, _three_pages()),
        Sample("long_names", "Long names in Hindi", REPORT, _long_names()),
        Sample("bill", "Bill with 25 lines", "pdf/sample_bill.html", _bill()),
    )
}
# Which samples the editor offers for each document kind, the first being the default.
FOR_KIND = {
    "report_a4": ("short", "three_pages", "long_names"),
    "bill_a4": ("bill",),
}


def render(
    code: str,
    spec: PageSpec,
    output: str,
    *,
    files: FileReader | None = None,
    offset_mm: tuple[Decimal, Decimal] = NO_RESERVE,
    guides: str = "",
    header: Mapping[str, Any] | None = None,
) -> Rendered:
    """A sample on this layout. `header` is the branch's own name and address, shown in
    place of the made-up one when no letterhead file is drawn."""
    chosen = SAMPLES[code]
    if chosen.template == REPORT:
        report = chosen.data | ({"header": header} if header else {})
        return compose_report(report, spec, output, files=files, offset_mm=offset_mm, guides=guides)
    html = render_html(
        chosen.template,
        sample=chosen.data,
        guides=guides,
        builtin_header=header if spec.file_id is None else None,
    )
    return compose(html, spec, output, files=files, offset_mm=offset_mm)
