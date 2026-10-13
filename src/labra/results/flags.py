"""How a result is read against its range: which range applies, the flag, the tier (§1d).

Pure functions, so the rules can be tested as a table and live in one place. Nothing here is
copied into JavaScript; the screen shows what these functions returned and the database kept.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from labra.catalog.models import ReferenceBand, ReferenceRange

Flag = Literal["N", "L", "H", "LL", "HH", "A"]
# What the cell looks like on screen. Print never uses these, only bold and the flag.
State = Literal["empty", "normal", "borderline", "low", "high", "critical", "abnormal"]

CRITICAL_FLAGS: frozenset[str] = frozenset({"LL", "HH"})


@dataclass(frozen=True)
class Flagged:
    """A value read against its range. `flag` is None when there is nothing to compare."""

    flag: Flag | None = None
    band_label: str = ""
    band_severity: str | None = None

    @property
    def is_critical(self) -> bool:
        return self.flag in CRITICAL_FLAGS

    @property
    def state(self) -> State:
        return state_of(self.flag, self.band_severity)


def pick_range(
    ranges: Iterable[ReferenceRange],
    sex: str | None,
    age_days: int,
    condition: str | None = None,
    approved_only: bool = True,
) -> ReferenceRange | None:
    """The approved range for this sex and age in days at collection, or None. Only the
    typo guard asks for unapproved ranges too: a slip of the finger is one either way.

    A range for the patient's own sex wins over one for any sex, and a range for the stated
    condition (pregnancy and the like) over the plain one. A range that names a condition is
    never used for a patient who doesn't have it.
    """
    best: ReferenceRange | None = None
    best_rank: tuple[int, int, int] | None = None
    for r in ranges:
        if not r.is_active or (approved_only and r.approved_at is None):
            continue
        if not r.age_min_days <= age_days < r.age_max_days:
            continue
        if r.sex is not None and r.sex != sex:
            continue
        if r.condition is not None and r.condition != condition:
            continue
        rank = (
            int(r.condition is not None),
            int(r.sex is not None),
            -(r.age_max_days - r.age_min_days),
        )
        if best_rank is None or rank > best_rank:
            best, best_rank = r, rank
    return best


def is_absurd(value: Decimal, rng: ReferenceRange | None) -> bool:
    """Outside the typo guard: a value no patient has, such as haemoglobin 250."""
    if rng is None:
        return False
    if rng.absurd_low is not None and value < rng.absurd_low:
        return True
    return rng.absurd_high is not None and value > rng.absurd_high


def band_for(value: Decimal, bands: Sequence[ReferenceBand]) -> ReferenceBand | None:
    """The interpretation tier a value falls in.

    Tier limits are written as whole steps (up to 199, from 200), so a value between two tiers
    belongs to the lower one. A value below the first tier or above the last has none.
    """
    found: ReferenceBand | None = None
    for band in sorted(bands, key=lambda b: (b.low is not None, b.low or Decimal(0))):
        if band.low is None or value >= band.low:
            found = band
    if found is None:
        return None
    if found.high is not None and value > found.high:
        higher = [b for b in bands if b.low is not None and b.low > value]
        return found if higher else None
    return found


def compute_flag(
    value: Decimal | str | None,
    rng: ReferenceRange | None,
    bands: Sequence[ReferenceBand] = (),
    options: Sequence[dict[str, Any]] = (),
) -> Flagged:
    """The flag and tier for one value.

    A number is compared with the range: at or beyond a critical limit is LL or HH, below low
    is L, above high is H, anything else N. A one-sided range checks only its own side. A
    chosen option is A when the catalog marks it abnormal, else N. Free text and a number with
    no range get no flag. The absurd limits are checked separately, before saving.
    """
    if value is None:
        return Flagged()
    if isinstance(value, str):
        chosen = value.strip()
        if not chosen:
            return Flagged()
        for option in options:
            if option.get("value") == chosen:
                return Flagged("A" if option.get("abnormal") else "N")
        return Flagged()
    if rng is None:
        return Flagged()
    band = band_for(value, bands)
    label = band.label if band else ""
    severity = band.severity if band else None
    flag: Flag
    if rng.critical_low is not None and value <= rng.critical_low:
        flag = "LL"
    elif rng.critical_high is not None and value >= rng.critical_high:
        flag = "HH"
    elif rng.low is not None and value < rng.low:
        flag = "L"
    elif rng.high is not None and value > rng.high:
        flag = "H"
    else:
        flag = "N"
    return Flagged(flag, label, severity)


def state_of(flag: str | None, band_severity: str | None) -> State:
    """The screen state of a cell. Amber is only for a value inside its range whose tier is
    borderline; a value outside the range keeps its low or high colour whatever the tier."""
    match flag:
        case None:
            return "empty"
        case "LL" | "HH":
            return "critical"
        case "L":
            return "low"
        case "H":
            return "high"
        case "A":
            return "abnormal"
        case _:
            return "borderline" if band_severity == "borderline" else "normal"
