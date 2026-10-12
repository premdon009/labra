"""Money as staff read it: digit grouping and the currency symbol, from a `CurrencyFormat`.
Amounts are always stored in paise; `decimals=0` changes only what is shown."""

from decimal import ROUND_HALF_UP, Decimal

from babel.numbers import format_decimal

from labra.core.currency import CurrencyFormat
from labra.core.money import money

_PATTERNS = {
    ("indian", 2): "#,##,##0.00",
    ("indian", 0): "#,##,##0",
    ("international", 2): "#,##0.00",
    ("international", 0): "#,##0",
}


def format_money(amount: Decimal, fmt: CurrencyFormat, symbol: bool = True) -> str:
    """`₹1,23,456.50`, or `-₹0.40` for a negative round-off."""
    value = money(amount)
    if fmt.decimals == 0:
        # Babel rounds half to even; bills round half up everywhere.
        value = value.quantize(Decimal(1), ROUND_HALF_UP)
    digits = format_decimal(abs(value), format=_PATTERNS[(fmt.grouping, fmt.decimals)], locale="en")
    sign = "-" if value < 0 else ""
    if not symbol or not fmt.symbol:
        return sign + digits
    text = {
        "before": f"{fmt.symbol}{digits}",
        "before_space": f"{fmt.symbol} {digits}",
        "after": f"{digits}{fmt.symbol}",
        "after_space": f"{digits} {fmt.symbol}",
    }[fmt.symbol_position]
    return sign + text


def money_filter(amount: Decimal, fmt: CurrencyFormat, column: bool = False) -> str:
    """The `money` Jinja filter. In a table column the symbol is shown on every amount only
    when the branch asks for that; otherwise the column heading carries it."""
    return format_money(amount, fmt, symbol=not column or fmt.show_in_columns == "every")
