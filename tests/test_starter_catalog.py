"""The starter catalog: its data file is consistent, and importing it is safe to repeat."""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.auth import service as auth
from labra.auth.principal import Principal
from labra.catalog import formula, starter
from labra.catalog import service as catalog
from labra.catalog.models import (
    RESULT_TYPES,
    Package,
    ReferenceBand,
    ReferenceRange,
    Test,
    TestMethod,
    TestParameter,
)
from labra.catalog.units import UNITS
from labra.core.errors import PermissionDeniedError
from labra.core.ids import utcnow
from labra.core.registry import Platform
from labra.seed import DEMO_PASSWORD

# Every test on the lab's current report sheets (design Appendix A), by starter code.
APPENDIX_A = {
    "cbc", "hb", "esr", "bg", "btct", "mp", "fbs", "ppbs", "rbs", "gtt", "hba1c", "lipid",
    "tc", "lft", "bil", "sgot", "sgpt", "urea", "creat", "ua", "ca", "phos", "crp", "ldh",
    "trop", "prog", "tft", "tsh", "urine", "usa", "upt", "fob", "hiv", "hbsag", "hcv", "vdrl",
    "widal", "dengue", "bmi", "bp", "mantoux",
}  # fmt: skip


def _as(db: Session, platform: Platform, username: str) -> Principal:
    signed = auth.login(db, platform.identity, username, DEMO_PASSWORD, "10.0.0.5", utcnow())
    return auth.principal_for(db, signed.session)


@pytest.fixture(scope="module")
def data() -> dict[str, Any]:
    return starter.load()


# The data file


@pytest.mark.item("M24")
def test_every_appendix_a_test_is_in_the_file(data: dict[str, Any]) -> None:
    assert {t["code"] for t in data["tests"]} >= APPENDIX_A


@pytest.mark.item("M24")
def test_every_reference_in_the_file_resolves(data: dict[str, Any]) -> None:
    params, citations, options = data["parameters"], data["citations"], data["option_sets"]
    departments = {d["name"] for d in data["departments"]}
    specimens = {s["code"] for s in data["specimens"]}
    for test in data["tests"]:
        assert test["department"] in departments, test["code"]
        assert test.get("specimen", "EDTA") in specimens, test["code"]
        assert set(test["parameters"]) <= params.keys(), test["code"]
    for code, p in params.items():
        assert p.get("type", "numeric") in RESULT_TYPES, code
        assert p.get("unit", "") in {"", *UNITS}, code
        if "options" in p:
            assert p["options"] in options, code
        for r in p.get("ranges", []):
            assert r["cite"] in citations, code
    tests = {t["code"] for t in data["tests"]}
    for package in data["packages"]:
        assert set(package["tests"]) <= tests, package["code"]


@pytest.mark.item("M24")
def test_calculated_parameters_use_only_their_test_s_parameters(data: dict[str, Any]) -> None:
    for test in data["tests"]:
        codes = set(test["parameters"])
        for code in codes:
            p = data["parameters"][code]
            if p.get("type") == "calculated":
                assert formula.parse(p["formula"])[1] <= codes, (test["code"], code)
                rule = p.get("valid_if", "")
                assert not rule or formula.parse(rule, condition=True)[1] <= codes


@pytest.mark.item("M24")
def test_disputed_printed_values_are_not_carried_over(data: dict[str, Any]) -> None:
    """The old sheets' spellings and the triglyceride cut-off at 160 are corrected."""
    names = {p["name"] for p in data["parameters"].values()}
    assert "Nitrite" in names and "Nitrate" not in names
    assert any("Westergren" in m for t in data["tests"] for m in t.get("methods", []))
    tg = data["parameters"]["TG"]["ranges"][0]
    assert tg["high"] == 149


# Importing


@pytest.mark.item("M24")
def test_import_creates_everything_unapproved_and_cited(
    seeded: Session, platform: Platform, data: dict[str, Any]
) -> None:
    admin = _as(seeded, platform, "anil")
    result = starter.import_starter(seeded, admin)
    assert result.tests == len(data["tests"])
    assert result.packages == len(data["packages"])
    assert result.skipped == []
    assert set(seeded.scalars(select(Test.code))) >= APPENDIX_A
    ranges = seeded.scalars(select(ReferenceRange)).all()
    assert len(ranges) == result.ranges > 0
    assert all(r.approved_at is None and r.source_citation for r in ranges)
    assert all(r.age_min_days == starter.ADULT_FROM_DAYS for r in ranges)
    assert (seeded.scalar(select(func.count()).select_from(ReferenceBand)) or 0) > 0
    assert len(catalog.unapproved_ranges(seeded, admin)) == len(ranges)

    lipid = seeded.scalar(select(Test).where(Test.code == "lipid"))
    assert lipid is not None
    params = {p.code: p for p in catalog.list_parameters(seeded, admin, lipid.id)}
    assert params["LDL"].formula_valid_if == "TG < 400"
    assert [p.code for p in catalog.list_parameters(seeded, admin, lipid.id)][:3] == [
        "TC",
        "TG",
        "HDL",
    ]
    methods = seeded.scalars(select(TestMethod).where(TestMethod.test_id == lipid.id)).all()
    assert [m.is_default for m in methods] == [True]


@pytest.mark.item("M24")
def test_import_again_adds_nothing_and_keeps_the_lab_s_own_tests(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    dept = catalog.save_department(seeded, admin, "Haematology", 5)
    own = catalog.save_test(
        seeded,
        admin,
        catalog.TestInput(code="hb", name="Hb (our method)", department_id=dept.id, aliases=["sf"]),
    )
    first = starter.import_starter(seeded, admin)
    assert first.skipped == ["hb"]
    assert seeded.get(Test, own.id).name == "Hb (our method)"  # type: ignore[union-attr]
    fbs = seeded.scalar(select(Test).where(Test.code == "fbs"))
    assert fbs is not None and "sf" not in fbs.aliases
    counts = [
        seeded.scalar(select(func.count()).select_from(model))
        for model in (Test, TestParameter, ReferenceRange, Package)
    ]
    second = starter.import_starter(seeded, admin)
    assert (second.departments, second.tests, second.packages, second.ranges) == (0, 0, 0, 0)
    assert counts == [
        seeded.scalar(select(func.count()).select_from(model))
        for model in (Test, TestParameter, ReferenceRange, Package)
    ]


@pytest.mark.item("M24")
def test_only_catalog_editors_import(seeded: Session, platform: Platform) -> None:
    with pytest.raises(PermissionDeniedError):
        starter.import_starter(seeded, _as(seeded, platform, "meera"))
    assert seeded.scalar(select(func.count()).select_from(Test)) == 0
