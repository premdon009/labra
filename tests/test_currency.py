"""Money as staff read it: grouping, symbol, decimals, and amounts in words."""

from decimal import Decimal

import pytest

from labra.core.currency import CurrencyFormat, amount_in_words, format_from
from labra.core.errors import ValidationFailedError
from labra.core.lab_settings import DEFINITIONS, coerce
from labra.web.money_format import format_money, money_filter

INDIAN = CurrencyFormat()
WESTERN = CurrencyFormat(grouping="international", words="international")


@pytest.mark.item("M23")
@pytest.mark.parametrize(
    ("amount", "fmt", "shown"),
    [
        ("0", INDIAN, "₹0.00"),
        ("1737", INDIAN, "₹1,737.00"),
        ("123456.5", INDIAN, "₹1,23,456.50"),
        ("10000000", INDIAN, "₹1,00,00,000.00"),
        ("123456.5", WESTERN, "₹123,456.50"),
        ("-0.40", INDIAN, "-₹0.40"),
        ("1737.50", CurrencyFormat(decimals=0), "₹1,738"),
        ("2.50", CurrencyFormat(decimals=0), "₹3"),
        ("1737", CurrencyFormat(symbol_position="before_space"), "₹ 1,737.00"),
        ("1737", CurrencyFormat(symbol_position="after"), "1,737.00₹"),
        ("1737", CurrencyFormat(symbol="Rs.", symbol_position="after_space"), "1,737.00 Rs."),
        ("1737", CurrencyFormat(symbol=""), "1,737.00"),
    ],
)
def test_format_money_table(amount: str, fmt: CurrencyFormat, shown: str) -> None:
    assert format_money(Decimal(amount), fmt) == shown


@pytest.mark.item("M23")
def test_money_in_columns() -> None:
    assert money_filter(Decimal(80), INDIAN, column=True) == "80.00"
    assert money_filter(Decimal(80), CurrencyFormat(show_in_columns="every"), column=True) == (
        "₹80.00"
    )
    assert money_filter(Decimal(80), INDIAN) == "₹80.00"


@pytest.mark.item("M23")
@pytest.mark.parametrize(
    ("amount", "fmt", "words"),
    [
        ("0", INDIAN, "Rupees zero only"),
        ("0.50", INDIAN, "Fifty paise only"),
        ("1", INDIAN, "Rupees one only"),
        ("1737", INDIAN, "Rupees one thousand seven hundred thirty-seven only"),
        (
            "99999.99",
            INDIAN,
            "Rupees ninety-nine thousand nine hundred ninety-nine and ninety-nine paise only",
        ),
        ("10000000", INDIAN, "Rupees one crore only"),
        ("10000000", WESTERN, "Rupees ten million only"),
        ("1000000000", INDIAN, "Rupees one hundred crore only"),
        ("1000000000", WESTERN, "Rupees one billion only"),
        (
            "2345678",
            INDIAN,
            "Rupees twenty-three lakh forty-five thousand six hundred seventy-eight only",
        ),
        (
            "12.05",
            CurrencyFormat(word_major="dirhams", word_minor="fils"),
            "Dirhams twelve and five fils only",
        ),
    ],
)
def test_amount_in_words_table(amount: str, fmt: CurrencyFormat, words: str) -> None:
    assert amount_in_words(Decimal(amount), fmt) == words


@pytest.mark.item("M23")
def test_amount_in_words_refuses_negative() -> None:
    with pytest.raises(ValueError):
        amount_in_words(Decimal("-1"), INDIAN)


@pytest.mark.item("M23")
def test_setting_choices_refused() -> None:
    assert coerce(DEFINITIONS["currency.grouping"], " international ") == "international"
    with pytest.raises(ValidationFailedError):
        coerce(DEFINITIONS["currency.grouping"], "chinese")
    with pytest.raises(ValidationFailedError):
        coerce(DEFINITIONS["currency.code"], "inr")
    with pytest.raises(ValidationFailedError):
        coerce(DEFINITIONS["currency.symbol"], "rupees")
    assert coerce(DEFINITIONS["currency.symbol"], "") == ""


@pytest.mark.item("M23")
def test_defaults_build_the_indian_format() -> None:
    defaults = {
        k.removeprefix("currency."): d.default
        for k, d in DEFINITIONS.items()
        if d.group == "currency"
    }
    assert format_from(defaults) == INDIAN
    assert format_from({**defaults, "round_off_to": "none"}).round_off_to is None
    assert INDIAN.snapshot()["round_off_to"] == "1.00"
