"""Tests, parameters, ranges, methods and packages through the catalog service, against real
Postgres with the demo cast."""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth import service as auth
from labra.auth.principal import Principal
from labra.catalog import service as catalog
from labra.catalog.models import Department, Test, TestMethod
from labra.core.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from labra.core.ids import utcnow
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.seed import DEMO_PASSWORD
from tests.frontdesk import full_name


def _as(db: Session, platform: Platform, username: str) -> Principal:
    signed = auth.login(db, platform.identity, username, DEMO_PASSWORD, "10.0.0.5", utcnow())
    return auth.principal_for(db, signed.session)


def _department(db: Session, admin: Principal) -> Department:
    return catalog.save_department(db, admin, "Biochemistry", 20)


def _lipid(db: Session, admin: Principal) -> Test:
    """A lipid test with TC, TG and HDL measured and LDL calculated."""
    dept = _department(db, admin)
    test = catalog.save_test(
        db, admin, catalog.TestInput(code="lipid", name="Lipid profile", department_id=dept.id)
    )
    for order, code in enumerate(("TC", "TG", "HDL"), start=1):
        catalog.save_parameter(
            db,
            admin,
            test.id,
            catalog.ParameterInput(
                code=code, name=code, result_type="numeric", unit_ucum="mg/dL", display_order=order
            ),
        )
    catalog.save_parameter(
        db,
        admin,
        test.id,
        catalog.ParameterInput(
            code="LDL",
            name="LDL cholesterol",
            result_type="calculated",
            unit_ucum="mg/dL",
            formula="TC - HDL - TG / 5",
            formula_valid_if="TG < 400",
            display_order=4,
        ),
    )
    return test


def _param(db: Session, admin: Principal, test: Test, code: str) -> uuid.UUID:
    return next(p.id for p in catalog.list_parameters(db, admin, test.id) if p.code == code)


def _errors(exc: pytest.ExceptionInfo[ValidationFailedError]) -> dict[str, str]:
    return exc.value.errors


# Tests and codes


@pytest.mark.item("M05.1")
def test_codes_are_lowercased_and_share_one_namespace(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    dept = _department(seeded, admin)
    hb = catalog.save_test(
        seeded,
        admin,
        catalog.TestInput(code=" HB ", name="Haemoglobin", department_id=dept.id, aliases=["HGB"]),
    )
    assert (hb.code, hb.aliases) == ("hb", ["hgb"])
    for code in ("hb", "hgb"):
        with pytest.raises(ValidationFailedError) as exc:
            catalog.save_test(
                seeded, admin, catalog.TestInput(code=code, name="Other", department_id=dept.id)
            )
        assert "code" in _errors(exc)
    with pytest.raises(ValidationFailedError) as exc:
        catalog.save_package(seeded, admin, "hgb", "Clash", [hb.id, hb.id])
    assert "code" in _errors(exc)


@pytest.mark.item("M05.1")
@pytest.mark.parametrize("code", ["", "has space", "x" * 21, "-lead"])
def test_bad_codes_are_refused(seeded: Session, platform: Platform, code: str) -> None:
    admin = _as(seeded, platform, "anil")
    dept = _department(seeded, admin)
    with pytest.raises(ValidationFailedError) as exc:
        catalog.save_test(
            seeded, admin, catalog.TestInput(code=code, name="X", department_id=dept.id)
        )
    assert "code" in _errors(exc)


@pytest.mark.item("M05")
def test_only_catalog_editors_change_the_catalog(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    dept = _department(seeded, admin)
    for username in ("priya", "suresh", "meera"):
        someone = _as(seeded, platform, username)
        assert catalog.list_departments(seeded, someone)  # everyone can read it
        with pytest.raises(PermissionDeniedError):
            catalog.save_test(
                seeded, someone, catalog.TestInput(code="x", name="X", department_id=dept.id)
            )


@pytest.mark.item("M05")
@pytest.mark.item("EC-K02")
def test_an_edit_audits_before_and_after_of_changed_fields(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    data = catalog.TestInput(code="lipid", name="Lipid panel", department_id=test.department_id)
    catalog.save_test(seeded, admin, data, test.id, test.row_version)
    detail = seeded.scalar(
        select(AuditLog.detail).where(
            AuditLog.action == "test.update", AuditLog.entity_id == str(test.id)
        )
    )
    assert detail == {"before": {"name": "Lipid profile"}, "after": {"name": "Lipid panel"}}


@pytest.mark.item("EC-B03")
def test_a_stale_catalog_edit_names_who_changed_it(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    old_version = test.row_version
    data = catalog.TestInput(code="lipid", name="Lipid panel", department_id=test.department_id)
    catalog.save_test(seeded, admin, data, test.id, old_version)
    data = catalog.TestInput(code="lipid", name="Lipids", department_id=test.department_id)
    with pytest.raises(ConflictError) as exc:
        catalog.save_test(seeded, admin, data, test.id, old_version)
    assert f"{full_name(seeded, 'anil')} changed this record at" in exc.value.public_message
    assert test.name == "Lipid panel"


# Parameters and formulas


@pytest.mark.item("M05")
def test_formula_must_use_parameters_of_the_same_test(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    bad = catalog.ParameterInput(code="X", name="X", result_type="calculated", formula="TC / CREAT")
    with pytest.raises(ValidationFailedError) as exc:
        catalog.save_parameter(seeded, admin, test.id, bad)
    assert "CREAT" in _errors(exc)["formula"]


@pytest.mark.item("M05")
def test_formula_refuses_unsafe_code_and_cycles(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    unsafe = catalog.ParameterInput(
        code="X", name="X", result_type="calculated", formula="__import__('os')"
    )
    with pytest.raises(ValidationFailedError) as exc:
        catalog.save_parameter(seeded, admin, test.id, unsafe)
    assert "formula" in _errors(exc)
    a = catalog.save_parameter(
        seeded,
        admin,
        test.id,
        catalog.ParameterInput(code="A", name="A", result_type="calculated", formula="LDL / 2"),
    )
    loop = catalog.ParameterInput(code="LDL2", name="B", result_type="calculated", formula="A")
    catalog.save_parameter(seeded, admin, test.id, loop)
    back = catalog.ParameterInput(code="A", name="A", result_type="calculated", formula="LDL2")
    with pytest.raises(ValidationFailedError) as exc:
        catalog.save_parameter(seeded, admin, test.id, back, a.id, a.row_version)
    assert _errors(exc)["formula"] == "The formula depends on itself."


@pytest.mark.item("M05")
def test_units_come_from_the_list(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    typo = catalog.ParameterInput(code="X", name="X", result_type="numeric", unit_ucum="mgs/dl")
    with pytest.raises(ValidationFailedError) as exc:
        catalog.save_parameter(seeded, admin, test.id, typo)
    assert "unit_ucum" in _errors(exc)


@pytest.mark.item("M05.2")
def test_option_lists_keep_abnormal_marks_and_one_default(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    options = [
        {"value": "Nil", "default": True},
        {"value": "Trace", "abnormal": True},
        {"value": "+", "abnormal": True, "colour": "red"},
    ]
    sugar = catalog.save_parameter(
        seeded,
        admin,
        test.id,
        catalog.ParameterInput(code="SUG", name="Sugar", result_type="option", options=options),
    )
    assert sugar.options == [
        {"value": "Nil", "abnormal": False, "default": True},
        {"value": "Trace", "abnormal": True, "default": False},
        {"value": "+", "abnormal": True, "default": False},
    ]
    for bad in (
        [],
        [{"value": "Nil"}, {"value": "Nil"}],
        [{"value": "A", "default": True}, {"value": "B", "default": True}],
    ):
        data = catalog.ParameterInput(code="S2", name="S", result_type="option", options=bad)
        with pytest.raises(ValidationFailedError):
            catalog.save_parameter(seeded, admin, test.id, data)


@pytest.mark.item("M05")
def test_a_text_parameter_may_check_a_pattern(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    bp = catalog.save_parameter(
        seeded,
        admin,
        test.id,
        catalog.ParameterInput(
            code="BP", name="BP", result_type="text", text_pattern=r"^\d{2,3}/\d{2,3}$"
        ),
    )
    assert bp.text_pattern
    broken = catalog.ParameterInput(code="X", name="X", result_type="text", text_pattern="(")
    with pytest.raises(ValidationFailedError):
        catalog.save_parameter(seeded, admin, test.id, broken)


# Reference ranges


@pytest.mark.item("M05.2")
@pytest.mark.parametrize(
    ("limits", "field"),
    [
        ({"low": "5", "high": "4"}, "high"),
        ({"low": "4", "critical_low": "5"}, "critical_low"),
        ({"low": "4", "critical_low": "3", "absurd_low": "3.5"}, "absurd_low"),
        ({"high": "10", "critical_high": "9"}, "critical_high"),
        ({"high": "10", "absurd_high": "9"}, "absurd_high"),
        ({"low": "four"}, "low"),
        ({"sex": "X"}, "sex"),
        ({"condition": "fasting"}, "condition"),
        ({"age_min_days": 365, "age_max_days": 30}, "age_max_days"),
    ],
)
def test_range_limits_must_nest(
    seeded: Session, platform: Platform, limits: dict[str, Any], field: str
) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    with pytest.raises(ValidationFailedError) as exc:
        catalog.save_range(
            seeded, admin, _param(seeded, admin, test, "TC"), catalog.RangeInput(**limits)
        )
    assert field in _errors(exc)


@pytest.mark.item("M05.2")
def test_ranges_in_use_for_one_sex_and_condition_must_not_share_an_age(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    tc = _param(seeded, admin, _lipid(seeded, admin), "TC")
    adult = catalog.save_range(seeded, admin, tc, catalog.RangeInput(age_min_days=6574, high="199"))
    # Touching ages, another sex, a condition and a range out of use are all fine.
    catalog.save_range(seeded, admin, tc, catalog.RangeInput(age_max_days=6574, high="169"))
    catalog.save_range(seeded, admin, tc, catalog.RangeInput(sex="F", high="189"))
    catalog.save_range(seeded, admin, tc, catalog.RangeInput(condition="pregnancy_t3", high="300"))
    catalog.save_range(seeded, admin, tc, catalog.RangeInput(high="1", is_active=False))
    with pytest.raises(ValidationFailedError) as exc:
        catalog.save_range(seeded, admin, tc, catalog.RangeInput(age_min_days=21915, high="210"))
    assert "age_min_days" in _errors(exc)
    # A range may be saved again over its own ages.
    catalog.save_range(
        seeded,
        admin,
        tc,
        catalog.RangeInput(age_min_days=6574, high="200"),
        adult.id,
        adult.row_version,
    )


@pytest.mark.item("M05.2")
def test_ranges_only_on_numeric_and_calculated_parameters(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    sugar = catalog.save_parameter(
        seeded,
        admin,
        test.id,
        catalog.ParameterInput(
            code="SUG", name="Sugar", result_type="option", options=[{"value": "Nil"}]
        ),
    )
    with pytest.raises(ValidationFailedError):
        catalog.save_range(seeded, admin, sugar.id, catalog.RangeInput(high="1"))
    ldl = catalog.save_range(
        seeded, admin, _param(seeded, admin, test, "LDL"), catalog.RangeInput(high="99")
    )
    assert ldl.high == Decimal(99)


@pytest.mark.item("M05.2")
def test_only_a_signatory_approves_and_any_change_needs_approval_again(
    seeded: Session, platform: Platform
) -> None:
    admin = _as(seeded, platform, "anil")
    signatory = _as(seeded, platform, "meera")
    test = _lipid(seeded, admin)
    hdl = _param(seeded, admin, test, "HDL")
    rng = catalog.save_range(
        seeded, admin, hdl, catalog.RangeInput(low="40", absurd_low="2", source_citation="NCEP")
    )
    assert [r.id for _, _, r in catalog.unapproved_ranges(seeded, admin).items] == [rng.id]
    with pytest.raises(PermissionDeniedError):
        catalog.approve_range(seeded, admin, rng.id, rng.row_version)
    catalog.approve_range(seeded, signatory, rng.id, rng.row_version)
    assert rng.approved_by == signatory.user_id
    assert catalog.unapproved_ranges(seeded, admin).items == []

    # Saving the same values is not a change; a new limit is.
    same = catalog.RangeInput(low="40", absurd_low="2", source_citation="NCEP")
    catalog.save_range(seeded, admin, hdl, same, rng.id, rng.row_version)
    assert rng.approved_at is not None
    new = catalog.RangeInput(low="45", absurd_low="2", source_citation="NCEP")
    catalog.save_range(seeded, admin, hdl, new, rng.id, rng.row_version)
    assert rng.approved_at is None

    catalog.approve_range(seeded, signatory, rng.id, rng.row_version)
    catalog.set_bands(
        seeded, admin, rng.id, [catalog.BandInput(label="Low", severity="abnormal", high="39")]
    )
    assert rng.approved_at is None
    with pytest.raises(ConflictError):
        catalog.approve_range(seeded, signatory, rng.id, rng.row_version - 1)


@pytest.mark.item("M05.2")
@pytest.mark.item("EC-K02")
def test_bands_replace_the_old_ones_and_are_audited(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    rng = catalog.save_range(
        seeded, admin, _param(seeded, admin, test, "TC"), catalog.RangeInput(high="199")
    )
    first = [
        catalog.BandInput(label="Desirable", severity="normal", high="199"),
        catalog.BandInput(label="High", severity="abnormal", low="240"),
    ]
    catalog.set_bands(seeded, admin, rng.id, first)
    catalog.set_bands(
        seeded, admin, rng.id, [catalog.BandInput(label="Desirable", severity="normal", high="189")]
    )
    bands = catalog.list_bands(seeded, admin, rng.id)
    assert [(b.label, b.high) for b in bands] == [("Desirable", Decimal(189))]
    details = list(
        seeded.scalars(
            select(AuditLog.detail)
            .where(AuditLog.action == "range.bands", AuditLog.entity_id == str(rng.id))
            .order_by(AuditLog.id)
        )
    )
    assert [b["label"] for b in details[1]["before"]] == ["Desirable", "High"]
    assert details[1]["after"][0]["high"] == "189"
    with pytest.raises(ValidationFailedError):
        catalog.set_bands(seeded, admin, rng.id, [catalog.BandInput(label="", severity="normal")])
    with pytest.raises(ValidationFailedError):
        catalog.set_bands(seeded, admin, rng.id, [catalog.BandInput(label="X", severity="bad")])


# Methods, presets and packages


@pytest.mark.item("M05")
def test_one_default_method_per_test(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    first = catalog.save_method(seeded, admin, test.id, "Enzymatic", is_default=True)
    second = catalog.save_method(seeded, admin, test.id, "Direct", is_default=True)
    seeded.refresh(first)
    assert (first.is_default, second.is_default) == (False, True)
    defaults = seeded.scalars(
        select(TestMethod).where(TestMethod.test_id == test.id, TestMethod.is_default)
    ).all()
    assert len(defaults) == 1


@pytest.mark.item("M05")
def test_comment_presets_for_one_test_or_any(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    test = _lipid(seeded, admin)
    catalog.save_preset(seeded, admin, "Lipaemic", "Sample lipaemic; repeat fasting.", test.id)
    catalog.save_preset(seeded, admin, "Haemolysed", "Sample haemolysed.")
    assert {p.label for p in catalog.list_presets(seeded, admin, test.id)} == {
        "Lipaemic",
        "Haemolysed",
    }
    with pytest.raises(ValidationFailedError):
        catalog.save_preset(seeded, admin, "", "")


@pytest.mark.item("M05")
def test_a_package_needs_two_tests(seeded: Session, platform: Platform) -> None:
    admin = _as(seeded, platform, "anil")
    lipid = _lipid(seeded, admin)
    hb = catalog.save_test(
        seeded,
        admin,
        catalog.TestInput(code="hb", name="Haemoglobin", department_id=lipid.department_id),
    )
    with pytest.raises(ValidationFailedError):
        catalog.save_package(seeded, admin, "pk", "Package", [lipid.id])
    pkg = catalog.save_package(seeded, admin, "pk", "Package", [lipid.id, hb.id])
    assert {t.code for t in catalog.package_tests(seeded, pkg.id)} == {"lipid", "hb"}
    catalog.save_package(
        seeded,
        admin,
        "pk",
        "Package",
        [lipid.id, hb.id, hb.id],
        package_id=pkg.id,
        row_version=pkg.row_version,
    )
    with pytest.raises(ValidationFailedError):
        catalog.save_test(
            seeded, admin, catalog.TestInput(code="pk", name="X", department_id=lipid.department_id)
        )
