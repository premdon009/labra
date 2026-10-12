"""How a branch shows money, and amounts in words. Formatting digits is the web layer's job
(`labra.web.money_format`); this module only reads the settings and spells numbers."""

import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from labra.core import lab_settings
from labra.core.money import money


@dataclass(frozen=True)
class CurrencyFormat:
    code: str = "INR"
    symbol: str = "₹"
    symbol_position: str = "before"
    grouping: str = "indian"
    decimals: int = 2
    show_in_columns: str = "header"
    words: str = "indian"
    word_major: str = "rupees"
    word_minor: str = "paise"
    round_off_to: Decimal | None = Decimal("1.00")

    def snapshot(self) -> dict[str, Any]:
        """The format as plain JSON values, frozen into an issued bill."""
        data = asdict(self)
        data["round_off_to"] = None if self.round_off_to is None else str(self.round_off_to)
        return data


def format_from(values: dict[str, str]) -> CurrencyFormat:
    """Build a format from setting values keyed without the `currency.` prefix."""
    unit = values["round_off_to"]
    return CurrencyFormat(
        code=values["code"],
        symbol=values["symbol"],
        symbol_position=values["symbol_position"],
        grouping=values["grouping"],
        decimals=int(values["decimals"]),
        show_in_columns=values["show_in_columns"],
        words=values["words"],
        word_major=values["word_major"],
        word_minor=values["word_minor"],
        round_off_to=None if unit == "none" else Decimal(unit),
    )


def load_format(db: Session, branch_id: uuid.UUID | None) -> CurrencyFormat:
    keys = [k for k, d in lab_settings.DEFINITIONS.items() if d.group == "currency"]
    return format_from(
        {k.removeprefix("currency."): lab_settings.get_value(db, k, branch_id) for k in keys}
    )


# fmt: off
_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
# fmt: on
_INDIAN = ((10**7, "crore"), (10**5, "lakh"), (1000, "thousand"), (100, "hundred"))
_INTERNATIONAL = ((10**9, "billion"), (10**6, "million"), (1000, "thousand"), (100, "hundred"))


def number_in_words(n: int, system: str = "indian") -> str:
    """A whole number in lower-case English: 123456 → one lakh twenty-three thousand four
    hundred fifty-six. Above the largest scale the count repeats: one hundred crore."""
    if n < 0:
        raise ValueError("Only amounts of zero or more can be written in words.")
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    scales = _INDIAN if system == "indian" else _INTERNATIONAL
    for size, name in scales:
        if n >= size:
            count, rest = divmod(n, size)
            words = f"{number_in_words(count, system)} {name}"
            return words + (f" {number_in_words(rest, system)}" if rest else "")
    raise AssertionError("unreachable")


def amount_in_words(amount: Decimal, fmt: CurrencyFormat) -> str:
    """`Rupees one thousand seven hundred thirty-seven and fifty paise only`, cheque style,
    so one rupee reads `Rupees one only` without needing a singular word."""
    amount = money(amount)
    if amount < 0:
        raise ValueError("Only amounts of zero or more can be written in words.")
    major, minor = divmod(int(amount * 100), 100)
    paise = f"{number_in_words(minor, fmt.words)} {fmt.word_minor}"
    if major == 0 and minor:
        text = paise
    else:
        text = f"{fmt.word_major} {number_in_words(major, fmt.words)}"
        if minor:
            text += f" and {paise}"
    text = f"{text} only"
    return text[:1].upper() + text[1:]
