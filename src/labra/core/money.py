"""All bill arithmetic: Decimal in paise, half-up rounding, no floats.

Screens and templates never add money themselves; they show what this module returns.
"""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Literal

PAISA = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Decimal | int | str) -> Decimal:
    """A finite amount quantized to paise. Floats are refused: 0.1 is not 0.10."""
    if isinstance(value, float | bool):
        raise TypeError("Money must be a Decimal, int or str, never a float.")
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError("Money must be a finite number.")
    return amount.quantize(PAISA, ROUND_HALF_UP)


@dataclass(frozen=True)
class Line:
    rate: Decimal
    discountable: bool = True


@dataclass(frozen=True)
class Discount:
    kind: Literal["pct", "amount"]
    value: Decimal


@dataclass(frozen=True)
class LineTotal:
    rate: Decimal
    discount: Decimal
    amount: Decimal


@dataclass(frozen=True)
class BillTotals:
    lines: list[LineTotal]
    gross: Decimal
    discount: Decimal
    round_off: Decimal
    net: Decimal


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` across `weights` in proportion, to the paisa, by largest remainder.
    Ties go to the earlier line, so the same bill always splits the same way."""
    total = money(total)
    paise = [int(money(w) / PAISA) for w in weights]
    whole = sum(paise)
    want = int(total / PAISA)
    if want == 0:
        return [ZERO for _ in weights]
    if whole <= 0 or want < 0 or want > whole:
        raise ValueError("Can't split this amount across these lines.")
    shares = [Decimal(want * p) / whole for p in paise]
    floors = [int(s.to_integral_value(ROUND_FLOOR)) for s in shares]
    left = want - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (-(shares[i] - floors[i]), i))
    for i in order[:left]:
        floors[i] += 1
    return [Decimal(f) * PAISA for f in floors]


def round_to_unit(amount: Decimal, unit: Decimal | None) -> Decimal:
    """Round to the nearest `unit` (1.00, 0.50, 0.10), half up; `None` leaves paise alone."""
    amount = money(amount)
    if unit is None:
        return amount
    unit = money(unit)
    if unit <= 0:
        raise ValueError("The round-off unit must be more than zero.")
    return money((amount / unit).quantize(Decimal(1), ROUND_HALF_UP) * unit)


def discount_amount(discount: Discount | None, discountable_gross: Decimal) -> Decimal:
    if discount is None:
        return ZERO
    value = money(discount.value)
    if value < 0:
        raise ValueError("A discount can't be negative.")
    if discount.kind == "pct":
        if value > 100:
            raise ValueError("A percentage discount can be at most 100.")
        return money(discountable_gross * value / 100)
    if value > discountable_gross:
        raise ValueError("The discount is more than the amount it applies to.")
    return value


def bill_totals(
    lines: list[Line], discount: Discount | None = None, unit: Decimal | None = None
) -> BillTotals:
    """Gross, discount spread over the discountable lines, round-off and net."""
    rates = [money(line.rate) for line in lines]
    if any(r < 0 for r in rates):
        raise ValueError("A rate can't be negative.")
    weights = [r if line.discountable else ZERO for r, line in zip(rates, lines, strict=True)]
    gross = money(sum(rates, ZERO))
    total_discount = discount_amount(discount, money(sum(weights, ZERO)))
    shares = allocate(total_discount, weights) if lines else []
    line_totals = [LineTotal(r, d, r - d) for r, d in zip(rates, shares, strict=True)]
    before = gross - total_discount
    net = round_to_unit(before, unit)
    return BillTotals(line_totals, gross, total_discount, net - before, net)


def bill_status(net: Decimal, paid: Decimal) -> Literal["open", "paid"]:
    """A bill with nothing left to pay, including one with net 0, is paid."""
    return "paid" if money(paid) >= money(net) else "open"


def apply_payment(
    net: Decimal, paid: Decimal, amount: Decimal
) -> tuple[Decimal, Decimal, Literal["open", "paid"]]:
    """New (paid, due, status) after taking `amount`. Over-payment is refused."""
    net, paid, amount = money(net), money(paid), money(amount)
    due = net - paid
    if amount <= 0:
        raise ValueError("A payment must be more than zero.")
    if amount > due:
        raise ValueError("The payment is more than the amount due.")
    paid += amount
    return paid, net - paid, bill_status(net, paid)
