"""Bill arithmetic: properties that hold for any bill, plus the worked examples."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labra.core.money import (
    Discount,
    Line,
    allocate,
    apply_payment,
    bill_status,
    bill_totals,
    money,
    round_to_unit,
)

rates = st.decimals(min_value=0, max_value=Decimal("99999.99"), places=2)
lines = st.lists(st.builds(Line, rate=rates, discountable=st.booleans()), min_size=1, max_size=30)
units = st.sampled_from([None, Decimal("1.00"), Decimal("0.50"), Decimal("0.10")])


@st.composite
def bills(draw: st.DrawFn) -> tuple[list[Line], Discount | None, Decimal | None]:
    items = draw(lines)
    base = sum((x.rate for x in items if x.discountable), Decimal(0))
    kind = draw(st.sampled_from(["none", "pct", "amount"]))
    if kind == "pct":
        discount = Discount("pct", draw(st.decimals(min_value=0, max_value=100, places=2)))
    elif kind == "amount":
        discount = Discount("amount", draw(st.decimals(min_value=0, max_value=base, places=2)))
    else:
        discount = None
    return items, discount, draw(units)


@pytest.mark.item("EC-B01")
@given(bills())
def test_money_property_line_discounts_sum_to_bill_discount(bill) -> None:
    totals = bill_totals(*bill)
    assert sum(t.discount for t in totals.lines) == totals.discount


@pytest.mark.item("EC-B01")
@given(bills())
def test_money_property_line_discount_within_rate(bill) -> None:
    items = bill[0]
    totals = bill_totals(*bill)
    for line, t in zip(items, totals.lines, strict=True):
        assert 0 <= t.discount <= t.rate
        if not line.discountable:
            assert t.discount == 0


@pytest.mark.item("EC-B01")
@given(bills())
def test_money_property_line_amounts_sum_to_gross_less_discount(bill) -> None:
    totals = bill_totals(*bill)
    assert sum(t.amount for t in totals.lines) == totals.gross - totals.discount


@pytest.mark.item("EC-B01")
@given(bills())
def test_money_property_round_off_within_half_unit(bill) -> None:
    unit = bill[2]
    totals = bill_totals(*bill)
    assert totals.net == totals.gross - totals.discount + totals.round_off
    assert abs(totals.round_off) <= (unit or 0) / 2
    assert totals.net >= 0


@pytest.mark.item("EC-B01")
@given(bills())
def test_money_property_net_is_whole_units(bill) -> None:
    unit = bill[2]
    totals = bill_totals(*bill)
    if unit is not None:
        assert totals.net % unit == 0


@pytest.mark.item("EC-B01")
@given(bills())
def test_money_property_two_decimal_places(bill) -> None:
    totals = bill_totals(*bill)
    values = [totals.gross, totals.discount, totals.round_off, totals.net]
    values += [v for t in totals.lines for v in (t.rate, t.discount, t.amount)]
    assert all(v.as_tuple().exponent == -2 for v in values)


@pytest.mark.item("EC-B01")
@given(rates, st.lists(rates, max_size=10))
def test_money_property_payments_never_overpay(net, attempts) -> None:
    paid = money(0)
    for amount in attempts:
        try:
            paid, due, status = apply_payment(net, paid, amount)
        except ValueError:
            continue
        assert paid <= net
        assert due >= 0
        assert (status == "paid") == (due == 0)


@pytest.mark.item("EC-B01")
def test_allocation_tie_goes_to_earlier_line() -> None:
    assert allocate(Decimal("0.01"), [Decimal(100)] * 3) == [Decimal("0.01"), 0, 0]


@pytest.mark.item("EC-B01")
def test_money_rejects_float() -> None:
    with pytest.raises(TypeError):
        money(0.1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        money("NaN")


@pytest.mark.item("EC-B01")
def test_half_paisa_rounds_up() -> None:
    assert money("0.005") == Decimal("0.01")
    assert round_to_unit(Decimal("10.50"), Decimal("1.00")) == Decimal("11.00")


@pytest.mark.item("EC-B01")
@pytest.mark.item("M07")
def test_day_one_arithmetic() -> None:
    items = [Line(Decimal(r)) for r in ("80", "500", "150", "1200")]
    totals = bill_totals(items, Discount("pct", Decimal(10)), Decimal("1.00"))
    assert totals.gross == Decimal("1930.00")
    assert totals.discount == Decimal("193.00")
    assert totals.net == Decimal("1737.00")
    paid, due, status = apply_payment(totals.net, money(0), Decimal(1000))
    assert (paid, due, status) == (Decimal("1000.00"), Decimal("737.00"), "open")


@pytest.mark.item("EC-B01")
@pytest.mark.item("M07")
def test_zero_net_is_paid() -> None:
    totals = bill_totals([Line(Decimal(0))])
    assert totals.net == 0
    assert bill_status(totals.net, money(0)) == "paid"


@pytest.mark.item("EC-B01")
def test_flat_discount_over_discountable_part_refused() -> None:
    with pytest.raises(ValueError):
        bill_totals(
            [Line(Decimal(100)), Line(Decimal(50), False)], Discount("amount", Decimal(101))
        )
