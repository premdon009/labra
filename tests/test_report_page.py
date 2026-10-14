"""How a report is laid out on its pages (design §7.0), from the made-up reports the letterhead
preview uses, and what `view` keeps for one copy."""

import io
from decimal import Decimal

import pdfplumber
import pytest
from pdfplumber.page import Page

from labra.printing import samples
from labra.printing.letterhead import A5, PageSpec
from labra.reports.content import Options, view

MM = 72 / 25.4
D = Decimal
SPEC = PageSpec(
    margin_top_mm=D(40),
    margin_bottom_mm=D(25),
    margin_left_mm=D(15),
    margin_right_mm=D(15),
    signature_area_mm=D(30),
    font_size_pt=D(10),
)


def _pages(code: str, spec: PageSpec = SPEC) -> list[Page]:
    pdf = samples.render(code, spec, "digital").pdf
    doc = pdfplumber.open(io.BytesIO(pdf))
    return list(doc.pages)


def _lines(page: Page) -> list[dict]:
    return page.extract_text_lines()


@pytest.mark.item("M12")
def test_the_band_repeats_and_the_signatory_signs_once_at_the_end() -> None:
    pages = _pages("three_pages")
    texts = [page.extract_text() for page in pages]
    assert len(texts) == 3
    for number, text in enumerate(texts, start=1):
        assert "Asha Testcase" in text and "B2/V/2627/000123" in text
        assert f"Report B2/R/2627/000123 v1 · Page {number} of 3" in text
    assert ["Dr. Sample Signatory" in text for text in texts] == [False, False, True]
    assert ["End of report" in text for text in texts] == [False, False, True]


@pytest.mark.item("M12")
def test_a_long_panel_runs_on_under_a_continued_heading_and_a_short_one_stays_whole() -> None:
    texts = [page.extract_text() for page in _pages("three_pages")]
    carried = [n for n, text in enumerate(texts) if "Allergy screen (made up) (continued)" in text]
    assert len(carried) == 1
    before = texts[carried[0] - 1]
    assert "Allergy screen (made up)" in before and "(continued)" not in before
    # Each blood count's six rows are on one page.
    for text in texts:
        assert text.count("Haemoglobin") == text.count("MCV")
    assert sum(text.count("Synthetic allergen") for text in texts) == 24


@pytest.mark.item("M12")
@pytest.mark.parametrize("spec", [SPEC, A5], ids=["A4", "A5"])
def test_a_band_with_long_names_never_reaches_the_letterhead_or_the_results(
    spec: PageSpec,
) -> None:
    (page,) = _pages("long_names", spec)
    top = float(spec.margin_top_mm) * MM
    assert min(c["top"] for c in page.chars) >= top - 0.5
    lines = _lines(page)
    reported = next(line for line in lines if "Reported" in line["text"])
    title = next(line for line in lines if line["text"] == "Laboratory report")
    assert reported["bottom"] < title["top"]
    width = page.width - float(spec.margin_right_mm) * MM
    assert max(c["x1"] for c in page.chars) <= width + 0.5


def _content() -> dict:
    """A snapshot of two tests, the second done by an outside lab."""

    def panel(key: str, department: str, **extra) -> dict:
        return {
            "key": key,
            "order_test_id": key,
            "department": department,
            "name": f"Test {key}",
            "research": False,
            "outside": None,
            "attached": None,
            "nabl": "MC-0000",
            "rows": [],
        } | extra

    return {
        "report_no": "B2/R/2627/000001",
        "version": 2,
        "header": {"name": "Sample Diagnostics", "lines": []},
        "patient": {"name": "Asha Testcase", "patient_no": "P-1", "age_sex": "42 Y / F"},
        "visit": {"visit_no": "B2/V/2627/000001"},
        "panels": [
            panel("a", "Haematology"),
            panel("b", "Haematology", research=True),
            panel(
                "c",
                "Serology",
                nabl="",
                outside={"lab": "Synthetic Referral Lab A", "nabl": "", "accession": "RL-1"},
            ),
        ],
        "pending": [],
        "signatory": {"name": "Dr. Sample Signatory", "signature_file_id": None},
        "footer_text": "",
    }


@pytest.mark.item("M12")
@pytest.mark.item("M20")
def test_a_copy_keeps_only_what_its_tests_need() -> None:
    whole = view(_content(), Options())
    assert whole["reference"] == "Report B2/R/2627/000001 v2"
    assert [d["name"] for d in whole["departments"]] == ["Haematology", "Serology"]
    assert whole["nabl"] == ""
    assert whole["outside"] == ["Test c: performed by Synthetic Referral Lab A, accession RL-1"]
    assert whole["research"] and whole["selected"] == ""
    assert not whole["partial"]

    first = view(_content(), Options(paper="A5", reference=False, tests=frozenset({"a"})))
    assert first["nabl"] == "MC-0000"
    assert first["outside"] == [] and not first["research"]
    assert not first["show_reference"]
    assert first["selected"] == "Selected tests only: 1 of 3 on this report"

    shown = view(_content(), Options(), preview=True)
    assert shown["preview"] and shown["reference"] == "Preview, not released"
