"""Import the starter catalog (`starter_catalog.toml`) through the catalog service, so every row
is validated and audited like an admin's own edit.

Running it again adds only what is missing: a department, specimen type, test or package that
already exists (by name or code) is left exactly as the lab edited it. Every imported range is
unapproved until a signatory approves it.
"""

import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.catalog import service
from labra.catalog.models import Package, Test
from labra.core.dialect import list_items
from labra.core.errors import PermissionDeniedError

STARTER_FILE = "starter_catalog.toml"
# Starter ranges are adult ranges unless a range gives its own `age_days`.
ADULT_FROM_DAYS = int(18 * 365.25)


@dataclass
class ImportResult:
    departments: int = 0
    specimen_types: int = 0
    tests: int = 0
    packages: int = 0
    ranges: int = 0
    skipped: list[str] = field(default_factory=list)


def load() -> dict[str, Any]:
    """The starter catalog as shipped with this version of Labra."""
    text = resources.files("labra.catalog").joinpath(STARTER_FILE).read_text("utf-8")
    return tomllib.loads(text)


def _number(value: float | int | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _range_input(
    raw: dict[str, Any], absurd: list[float], citations: dict[str, str]
) -> service.RangeInput:
    age_min, age_max = raw.get("age_days", [ADULT_FROM_DAYS, service.MAX_AGE_DAYS])
    return service.RangeInput(
        sex=raw.get("sex"),
        age_min_days=age_min,
        age_max_days=age_max,
        condition=raw.get("condition"),
        low=_number(raw.get("low")),
        high=_number(raw.get("high")),
        absurd_low=_number(absurd[0]) if absurd else None,
        absurd_high=_number(absurd[1]) if absurd else None,
        display_text=raw.get("display", ""),
        source_citation=citations[raw["cite"]],
    )


def _add_test(
    db: Session,
    principal: Principal,
    data: dict[str, Any],
    raw: dict[str, Any],
    ids: dict[str, Any],
    taken: set[str],
) -> int:
    """Create one test with its parameters, ranges and methods; returns the ranges added."""
    test = service.save_test(
        db,
        principal,
        service.TestInput(
            code=raw["code"],
            name=raw["name"],
            department_id=ids["departments"][raw["department"]],
            aliases=[a for a in raw.get("aliases", []) if a not in taken],
            short_name=raw.get("short_name", ""),
            specimen_type_id=ids["specimens"].get(raw.get("specimen", "")),
            default_tat_hours=raw.get("tat_hours", 24),
            interpretation_text=raw.get("interpretation", ""),
        ),
    )
    ranges = 0
    for order, code in enumerate(raw["parameters"], start=1):
        spec = data["parameters"][code]
        options = spec.get("options", [])
        param = service.save_parameter(
            db,
            principal,
            test.id,
            service.ParameterInput(
                code=code,
                name=spec["name"],
                result_type=spec.get("type", "numeric"),
                unit_ucum=spec.get("unit", ""),
                decimals=spec.get("decimals", 0),
                formula=spec.get("formula", ""),
                formula_valid_if=spec.get("valid_if", ""),
                options=[dict(o) for o in data["option_sets"][options]] if options else [],
                text_pattern=spec.get("pattern", ""),
                display_order=order * 10,
            ),
        )
        for raw_range in spec.get("ranges", []):
            rng = service.save_range(
                db,
                principal,
                param.id,
                _range_input(raw_range, spec.get("absurd", []), data["citations"]),
            )
            bands = [
                service.BandInput(
                    label=b["label"],
                    severity=b["severity"],
                    low=_number(b.get("low")),
                    high=_number(b.get("high")),
                )
                for b in raw_range.get("bands", [])
            ]
            if bands:
                service.set_bands(db, principal, rng.id, bands)
            ranges += 1
    for i, name in enumerate(raw.get("methods", [])):
        service.save_method(db, principal, test.id, name, is_default=i == 0)
    return ranges


def import_starter(
    db: Session, principal: Principal, data: dict[str, Any] | None = None
) -> ImportResult:
    """Add whatever part of the starter catalog the lab doesn't have yet."""
    if not principal.can("catalog.edit"):
        raise PermissionDeniedError()
    data = data or load()
    result = ImportResult()

    departments = {d.name: d.id for d in service.list_departments(db, principal)}
    for order, raw in enumerate(data["departments"], start=1):
        if raw["name"] not in departments:
            dept = service.save_department(db, principal, raw["name"], order * 10)
            departments[dept.name] = dept.id
            result.departments += 1

    specimens = {s.code: s.id for s in service.list_specimen_types(db, principal)}
    for raw in data["specimens"]:
        if raw["code"] not in specimens:
            st = service.save_specimen_type(
                db, principal, raw["code"], raw["name"], raw.get("container", "")
            )
            specimens[st.code] = st.id
            result.specimen_types += 1

    ids = {"departments": departments, "specimens": specimens}
    # Codes and aliases share one namespace; a lab's own code wins over a starter alias.
    taken = {
        *db.scalars(select(Test.code)),
        *db.scalars(select(list_items(Test.aliases))),
        *db.scalars(select(Package.code)),
    }
    for raw in data["tests"]:
        if raw["code"] in taken:
            result.skipped.append(raw["code"])
            continue
        result.ranges += _add_test(db, principal, data, raw, ids, taken)
        taken |= {raw["code"], *raw.get("aliases", [])}
        result.tests += 1

    tests = {code: tid for tid, code in db.execute(select(Test.id, Test.code))}
    for raw in data["packages"]:
        if raw["code"] in taken or any(code not in tests for code in raw["tests"]):
            result.skipped.append(raw["code"])
            continue
        service.save_package(
            db, principal, raw["code"], raw["name"], [tests[code] for code in raw["tests"]]
        )
        result.packages += 1
    return result
