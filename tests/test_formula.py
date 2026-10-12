"""The calculated-parameter language: what it computes and what it refuses."""

from decimal import Decimal

import pytest

from labra.catalog import formula


@pytest.mark.item("M05")
def test_friedewald_ldl_and_its_validity_rule() -> None:
    values = {"TC": Decimal(200), "HDL": Decimal(50), "TG": Decimal(150)}
    assert formula.evaluate("TC - HDL - TG / 5", values) == Decimal("120.0")
    assert formula.holds("TG < 400", values)
    assert not formula.holds("TG < 400", {**values, "TG": Decimal(450)})


@pytest.mark.item("M05")
def test_parse_reports_the_parameter_codes_used() -> None:
    _, names = formula.parse("WT / (HT / 100) ** 2")
    assert names == {"WT", "HT"}
    assert formula.evaluate("WT / (HT / 100) ** 2", {"WT": 64, "HT": 160}) == Decimal("25.0")


@pytest.mark.item("M05")
def test_functions_are_allowed_but_not_as_names() -> None:
    assert formula.evaluate("max(A, B) - abs(C)", {"A": 1, "B": 3, "C": -1}) == Decimal("2.0")
    with pytest.raises(formula.FormulaError):
        formula.parse("max")


@pytest.mark.item("M05")
@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('true')",
        "TC.real",
        "TC[0]",
        "lambda: 1",
        "open('x')",
        "'text'",
        "TC if TG else HDL",
        "TC < 5",
        "TC and HDL",
        "True",
        "TC +",
        "max(TC)",
        "ln(TC, 2)",
        "1" * 201,
    ],
)
def test_anything_beyond_arithmetic_is_refused(source: str) -> None:
    with pytest.raises(formula.FormulaError):
        formula.parse(source)


@pytest.mark.item("M05")
def test_comparisons_only_in_validity_rules() -> None:
    _, names = formula.parse("TG < 400 and not HDL == 0", condition=True)
    assert names == {"TG", "HDL"}
    with pytest.raises(formula.FormulaError):
        formula.parse("TG < 400", condition=False)


@pytest.mark.item("M05")
@pytest.mark.parametrize(
    ("source", "values"),
    [
        ("TC / HDL", {"TC": 200, "HDL": 0}),
        ("TC - HDL", {"TC": 200, "HDL": None}),
        ("TC - HDL", {"TC": 200}),
        ("TC ** 99", {"TC": 2}),
        ("ln(TC)", {"TC": -1}),
        ("ln(TC)", {"TC": 0}),
        ("10 ** 10 ** 10", {}),
    ],
)
def test_missing_inputs_and_impossible_arithmetic_are_not_calculable(
    source: str, values: dict[str, int | None]
) -> None:
    with pytest.raises((formula.NotCalculable, formula.FormulaError)):
        formula.evaluate(source, values)


@pytest.mark.item("M05")
def test_a_rule_with_a_missing_input_does_not_hold_and_an_empty_one_does() -> None:
    assert not formula.holds("TG < 400", {})
    assert formula.holds("", {})
