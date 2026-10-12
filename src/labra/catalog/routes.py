import uuid
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.catalog import service, starter
from labra.catalog.models import BAND_SEVERITIES, RANGE_CONDITIONS, RESULT_TYPES, SEXES
from labra.catalog.units import UNITS
from labra.core.db import get_session
from labra.core.errors import NotFoundError, ValidationFailedError
from labra.org import service as org
from labra.web.templating import page, render

router = APIRouter(prefix="/admin")

DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require("catalog.view"))]
Editor = Annotated[Principal, Depends(require("catalog.edit"))]

# Blank rows offered under the existing options and tiers.
SPARE_ROWS = 3
DAYS_PER = {"years": Decimal("365.25"), "months": Decimal("30.4375"), "days": Decimal(1)}


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise NotFoundError() from None


def _optional_uuid(value: str) -> uuid.UUID | None:
    return _uuid(value) if value else None


def _int(value: str, errors: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(value) if value.strip() else default
    except ValueError:
        errors[key] = "Enter a whole number."
        return default


def _back(target: str, fallback: str) -> str:
    """Only return to a catalog screen, never to an address from outside."""
    return target if target.startswith("/admin/catalog") and "//" not in target else fallback


def _age_parts(days: int) -> tuple[str, str]:
    """Show 6574 days as 18 years and 180 days as 6 months, where they round-trip exactly."""
    for unit in ("years", "months"):
        n = round(Decimal(days) / DAYS_PER[unit])
        if int(n * DAYS_PER[unit]) == days:
            return str(n), unit
    return str(days), "days"


def _age_days(value: str, unit: str, errors: dict[str, str], key: str, default: int) -> int:
    if not value.strip():
        return default
    try:
        n = Decimal(value.strip())
    except InvalidOperation:
        n = Decimal(-1)
    if unit not in DAYS_PER or not n.is_finite() or n < 0 or n != n.to_integral_value():
        errors[key] = "Enter a whole number of years, months or days."
        return default
    return int(n * DAYS_PER[unit])


# Tests


@router.get("/catalog", response_class=HTMLResponse)
@page("admin/catalog", "catalog/tests.html")
def tests(
    request: Request, db: DB, principal: Viewer, q: str = "", department: str = ""
) -> Response:
    departments = service.list_departments(db, principal)
    dept_id = _optional_uuid(department)
    rows = service.list_tests(db, principal, dept_id)
    text = q.strip().lower()
    if text:
        rows = [
            t
            for t in rows
            if text in t.code
            or text in t.name.lower()
            or any(a.startswith(text) for a in t.aliases)
        ]
    prices = {
        r.item_id: r.lab_price for r in service.price_list(db, principal) if r.item_type == "test"
    }
    return render(
        request,
        "catalog/tests.html",
        {
            "tests": rows,
            "departments": {d.id: d for d in departments},
            "department": dept_id,
            "q": q,
            "prices": prices,
            "waiting": len(service.unapproved_ranges(db, principal)),
            "can_edit": principal.can("catalog.edit"),
        },
    )


def _test_form(
    request: Request,
    db: DB,
    principal: Principal,
    test: Any,
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    saved_id = getattr(test, "id", None)
    return render(
        request,
        "catalog/test_form.html",
        {
            "test": test,
            "errors": errors,
            "departments": service.list_departments(db, principal),
            "specimens": service.list_specimen_types(db, principal),
            "parameters": service.list_parameters(db, principal, saved_id) if saved_id else [],
            "methods": service.list_methods(db, principal, saved_id) if saved_id else [],
            "can_edit": principal.can("catalog.edit"),
        },
        status_code=status,
    )


@router.get("/catalog/tests/new", response_class=HTMLResponse)
@page("admin/catalog", "catalog/test_form.html")
def test_new(request: Request, db: DB, principal: Editor) -> Response:
    return _test_form(request, db, principal, None, {})


@router.get("/catalog/tests/{test_id}", response_class=HTMLResponse)
@page("admin/catalog", "catalog/test_form.html")
def test_edit(request: Request, test_id: str, db: DB, principal: Viewer) -> Response:
    return _test_form(request, db, principal, service.get_test(db, principal, _uuid(test_id)), {})


@router.post("/catalog/tests")
def test_save(
    request: Request,
    db: DB,
    principal: Editor,
    code: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    department_id: Annotated[str, Form()] = "",
    aliases: Annotated[str, Form()] = "",
    short_name: Annotated[str, Form()] = "",
    specimen_type_id: Annotated[str, Form()] = "",
    default_tat_hours: Annotated[str, Form()] = "24",
    in_house_available: Annotated[bool, Form()] = False,
    interpretation_text: Annotated[str, Form()] = "",
    is_active: Annotated[bool, Form()] = False,
    test_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    errors: dict[str, str] = {}
    tat = _int(default_tat_hours, errors, "default_tat_hours", 24)
    try:
        dept = _uuid(department_id)
    except NotFoundError:
        dept = uuid.UUID(int=0)
    data = service.TestInput(
        code=code,
        name=name,
        department_id=dept,
        aliases=[a.strip() for a in aliases.replace(",", " ").split() if a.strip()],
        short_name=short_name,
        specimen_type_id=_optional_uuid(specimen_type_id),
        default_tat_hours=tat,
        in_house_available=in_house_available,
        interpretation_text=interpretation_text,
        is_active=is_active or not test_id,
    )
    try:
        if errors:
            raise ValidationFailedError(errors)
        test = service.save_test(db, principal, data, _optional_uuid(test_id), row_version)
    except ValidationFailedError as exc:
        db.rollback()
        values = SimpleNamespace(
            **vars(data) | {"aliases": aliases.split()},
            id=_optional_uuid(test_id),
            row_version=row_version,
        )
        return _test_form(request, db, principal, values, errors | exc.errors, status=422)
    db.commit()
    return RedirectResponse(f"/admin/catalog/tests/{test.id}", status_code=303)


# Parameters


def _parameter_form(
    request: Request,
    db: DB,
    principal: Principal,
    test: Any,
    parameter: Any,
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    options = list(parameter.options) if parameter is not None else []
    saved_id = getattr(parameter, "id", None)
    return render(
        request,
        "catalog/parameter_form.html",
        {
            "test": test,
            "parameter": parameter,
            "options": options + [{}] * SPARE_ROWS,
            "ranges": service.list_ranges(db, principal, saved_id) if saved_id else [],
            "result_types": RESULT_TYPES,
            "units": UNITS,
            "errors": errors,
            "can_edit": principal.can("catalog.edit"),
        },
        status_code=status,
    )


@router.get("/catalog/tests/{test_id}/parameters/new", response_class=HTMLResponse)
@page("admin/catalog", "catalog/parameter_form.html")
def parameter_new(request: Request, test_id: str, db: DB, principal: Editor) -> Response:
    test = service.get_test(db, principal, _uuid(test_id))
    return _parameter_form(request, db, principal, test, None, {})


@router.get("/catalog/parameters/{parameter_id}", response_class=HTMLResponse)
@page("admin/catalog", "catalog/parameter_form.html")
def parameter_edit(request: Request, parameter_id: str, db: DB, principal: Viewer) -> Response:
    parameter = service.get_parameter(db, principal, _uuid(parameter_id))
    test = service.get_test(db, principal, parameter.test_id)
    return _parameter_form(request, db, principal, test, parameter, {})


@router.post("/catalog/parameters")
def parameter_save(
    request: Request,
    db: DB,
    principal: Editor,
    test_id: Annotated[str, Form()],
    code: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    result_type: Annotated[str, Form()] = "",
    unit_ucum: Annotated[str, Form()] = "",
    decimals: Annotated[str, Form()] = "0",
    formula: Annotated[str, Form()] = "",
    formula_valid_if: Annotated[str, Form()] = "",
    option_value: Annotated[list[str], Form()] = [],  # noqa: B006
    option_abnormal: Annotated[list[str], Form()] = [],  # noqa: B006
    option_default: Annotated[str, Form()] = "",
    text_pattern: Annotated[str, Form()] = "",
    display_order: Annotated[str, Form()] = "0",
    is_reportable: Annotated[bool, Form()] = False,
    is_active: Annotated[bool, Form()] = False,
    parameter_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    test = service.get_test(db, principal, _uuid(test_id))
    errors: dict[str, str] = {}
    # Options are posted as rows; the ticks carry the row number they belong to.
    options = [
        {
            "value": value.strip(),
            "abnormal": str(i) in option_abnormal,
            "default": str(i) == option_default,
        }
        for i, value in enumerate(option_value)
        if value.strip()
    ]
    data = service.ParameterInput(
        code=code,
        name=name,
        result_type=result_type,
        unit_ucum=unit_ucum,
        decimals=_int(decimals, errors, "decimals"),
        formula=formula,
        formula_valid_if=formula_valid_if,
        options=options if result_type == "option" else [],
        text_pattern=text_pattern,
        display_order=_int(display_order, errors, "display_order"),
        is_reportable=is_reportable,
        is_active=is_active or not parameter_id,
    )
    try:
        if errors:
            raise ValidationFailedError(errors)
        service.save_parameter(
            db, principal, test.id, data, _optional_uuid(parameter_id), row_version
        )
    except ValidationFailedError as exc:
        db.rollback()
        values = SimpleNamespace(
            **vars(data) | {"options": options},
            id=_optional_uuid(parameter_id),
            row_version=row_version,
        )
        return _parameter_form(
            request, db, principal, test, values, errors | exc.errors, status=422
        )
    db.commit()
    return RedirectResponse(f"/admin/catalog/tests/{test.id}", status_code=303)


# Departments and specimen types


def _setup_page(
    request: Request,
    db: DB,
    principal: Principal,
    errors: dict[str, str],
    error_for: str = "",
    status: int = 200,
) -> Response:
    return render(
        request,
        "catalog/departments.html",
        {
            "departments": service.list_departments(db, principal),
            "specimens": service.list_specimen_types(db, principal),
            "errors": errors,
            "error_for": error_for,
            "can_edit": principal.can("catalog.edit"),
        },
        status_code=status,
    )


@router.get("/catalog/departments", response_class=HTMLResponse)
@page("admin/catalog", "catalog/departments.html")
def departments(request: Request, db: DB, principal: Viewer) -> Response:
    return _setup_page(request, db, principal, {})


@router.post("/catalog/departments")
def department_save(
    request: Request,
    db: DB,
    principal: Editor,
    name: Annotated[str, Form()] = "",
    report_order: Annotated[str, Form()] = "0",
    is_active: Annotated[bool, Form()] = False,
    department_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    errors: dict[str, str] = {}
    order = _int(report_order, errors, "report_order")
    try:
        if errors:
            raise ValidationFailedError(errors)
        service.save_department(
            db,
            principal,
            name,
            order,
            is_active or not department_id,
            _optional_uuid(department_id),
            row_version,
        )
    except ValidationFailedError as exc:
        db.rollback()
        target = f"department-{department_id or 'new'}"
        return _setup_page(request, db, principal, errors | exc.errors, target, status=422)
    db.commit()
    return RedirectResponse("/admin/catalog/departments", status_code=303)


@router.post("/catalog/specimens")
def specimen_save(
    request: Request,
    db: DB,
    principal: Editor,
    code: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    container: Annotated[str, Form()] = "",
    is_active: Annotated[bool, Form()] = False,
    specimen_type_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    try:
        service.save_specimen_type(
            db,
            principal,
            code,
            name,
            container,
            is_active or not specimen_type_id,
            _optional_uuid(specimen_type_id),
            row_version,
        )
    except ValidationFailedError as exc:
        db.rollback()
        target = f"specimen-{specimen_type_id or 'new'}"
        return _setup_page(request, db, principal, exc.errors, target, status=422)
    db.commit()
    return RedirectResponse("/admin/catalog/departments", status_code=303)


# Packages


@router.get("/catalog/packages", response_class=HTMLResponse)
@page("admin/catalog", "catalog/packages.html")
def packages(request: Request, db: DB, principal: Viewer) -> Response:
    rows = service.list_packages(db, principal)
    return render(
        request,
        "catalog/packages.html",
        {
            "packages": [(p, service.package_tests(db, p.id)) for p in rows],
            "can_edit": principal.can("catalog.edit"),
        },
    )


def _package_form(
    request: Request,
    db: DB,
    principal: Principal,
    package: Any,
    chosen: set[uuid.UUID],
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    return render(
        request,
        "catalog/package_form.html",
        {
            "package": package,
            "chosen": chosen,
            "tests": [
                t for t in service.list_tests(db, principal) if t.is_active or t.id in chosen
            ],
            "errors": errors,
            "can_edit": principal.can("catalog.edit"),
        },
        status_code=status,
    )


@router.get("/catalog/packages/new", response_class=HTMLResponse)
@page("admin/catalog", "catalog/package_form.html")
def package_new(request: Request, db: DB, principal: Editor) -> Response:
    return _package_form(request, db, principal, None, set(), {})


@router.get("/catalog/packages/{package_id}", response_class=HTMLResponse)
@page("admin/catalog", "catalog/package_form.html")
def package_edit(request: Request, package_id: str, db: DB, principal: Viewer) -> Response:
    package = service.get_package(db, principal, _uuid(package_id))
    chosen = {t.id for t in service.package_tests(db, package.id)}
    return _package_form(request, db, principal, package, chosen, {})


@router.post("/catalog/packages")
def package_save(
    request: Request,
    db: DB,
    principal: Editor,
    code: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    test_ids: Annotated[list[str], Form()] = [],  # noqa: B006
    is_active: Annotated[bool, Form()] = False,
    package_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    chosen = {_uuid(t) for t in test_ids}
    try:
        service.save_package(
            db,
            principal,
            code,
            name,
            sorted(chosen),
            description,
            is_active or not package_id,
            _optional_uuid(package_id),
            row_version,
        )
    except ValidationFailedError as exc:
        db.rollback()
        values = SimpleNamespace(
            code=code,
            name=name,
            description=description,
            is_active=is_active,
            id=_optional_uuid(package_id),
            row_version=row_version,
        )
        return _package_form(request, db, principal, values, chosen, exc.errors, status=422)
    db.commit()
    return RedirectResponse("/admin/catalog/packages", status_code=303)


# Reference ranges


def _range_form(
    request: Request,
    db: DB,
    principal: Principal,
    parameter: Any,
    rng: Any,
    bands: list[Any],
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    test = service.get_test(db, principal, parameter.test_id)
    min_n, min_unit = _age_parts(rng.age_min_days) if rng is not None else ("0", "years")
    max_n, max_unit = (
        _age_parts(rng.age_max_days)
        if rng is not None and rng.age_max_days != service.MAX_AGE_DAYS
        else ("", "years")
    )
    return render(
        request,
        "catalog/range_form.html",
        {
            "test": test,
            "parameter": parameter,
            "range": rng,
            "age": {"min": min_n, "min_unit": min_unit, "max": max_n, "max_unit": max_unit},
            "bands": list(bands) + [None] * SPARE_ROWS,
            "sexes": SEXES,
            "conditions": RANGE_CONDITIONS,
            "severities": BAND_SEVERITIES,
            "unit": UNITS.get(parameter.unit_ucum, ""),
            "errors": errors,
            "can_edit": principal.can("catalog.edit"),
            "can_approve": principal.can("range.approve"),
        },
        status_code=status,
    )


@router.get("/catalog/ranges", response_class=HTMLResponse)
@page("admin/reference-ranges", "catalog/ranges.html")
def ranges_waiting(request: Request, db: DB, principal: Viewer) -> Response:
    return render(
        request,
        "catalog/ranges.html",
        {
            "rows": service.unapproved_ranges(db, principal),
            "can_approve": principal.can("range.approve"),
        },
    )


@router.get("/catalog/parameters/{parameter_id}/ranges/new", response_class=HTMLResponse)
@page("admin/reference-ranges", "catalog/range_form.html")
def range_new(request: Request, parameter_id: str, db: DB, principal: Editor) -> Response:
    parameter = service.get_parameter(db, principal, _uuid(parameter_id))
    return _range_form(request, db, principal, parameter, None, [], {})


@router.get("/catalog/ranges/{range_id}", response_class=HTMLResponse)
@page("admin/reference-ranges", "catalog/range_form.html")
def range_edit(request: Request, range_id: str, db: DB, principal: Viewer) -> Response:
    rng = service.get_range(db, principal, _uuid(range_id))
    parameter = service.get_parameter(db, principal, rng.parameter_id)
    bands = service.list_bands(db, principal, rng.id)
    return _range_form(request, db, principal, parameter, rng, bands, {})


def _band_key(b: Any) -> tuple[str, str, Decimal | None, Decimal | None]:
    def number(v: Any) -> Decimal | None:
        try:
            return Decimal(str(v)) if v not in (None, "") else None
        except InvalidOperation:
            return None

    return (b.label.strip(), b.severity, number(b.low), number(b.high))


@router.post("/catalog/ranges")
def range_save(
    request: Request,
    db: DB,
    principal: Editor,
    parameter_id: Annotated[str, Form()],
    sex: Annotated[str, Form()] = "",
    age_min: Annotated[str, Form()] = "",
    age_min_unit: Annotated[str, Form()] = "years",
    age_max: Annotated[str, Form()] = "",
    age_max_unit: Annotated[str, Form()] = "years",
    condition: Annotated[str, Form()] = "",
    low: Annotated[str, Form()] = "",
    high: Annotated[str, Form()] = "",
    critical_low: Annotated[str, Form()] = "",
    critical_high: Annotated[str, Form()] = "",
    absurd_low: Annotated[str, Form()] = "",
    absurd_high: Annotated[str, Form()] = "",
    display_text: Annotated[str, Form()] = "",
    source_citation: Annotated[str, Form()] = "",
    is_active: Annotated[bool, Form()] = False,
    band_label: Annotated[list[str], Form()] = [],  # noqa: B006
    band_severity: Annotated[list[str], Form()] = [],  # noqa: B006
    band_low: Annotated[list[str], Form()] = [],  # noqa: B006
    band_high: Annotated[list[str], Form()] = [],  # noqa: B006
    range_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    parameter = service.get_parameter(db, principal, _uuid(parameter_id))
    errors: dict[str, str] = {}
    data = service.RangeInput(
        sex=sex or None,
        age_min_days=_age_days(age_min, age_min_unit, errors, "age_min_days", 0),
        age_max_days=_age_days(age_max, age_max_unit, errors, "age_max_days", service.MAX_AGE_DAYS),
        condition=condition or None,
        low=low,
        high=high,
        critical_low=critical_low,
        critical_high=critical_high,
        absurd_low=absurd_low,
        absurd_high=absurd_high,
        display_text=display_text.strip(),
        source_citation=source_citation.strip(),
        is_active=is_active or not range_id,
    )
    bands = [
        service.BandInput(label, severity, lo, hi)
        for label, severity, lo, hi in zip(
            band_label, band_severity, band_low, band_high, strict=False
        )
        if label.strip() or lo.strip() or hi.strip()
    ]
    try:
        if errors:
            raise ValidationFailedError(errors)
        rng = service.save_range(
            db, principal, parameter.id, data, _optional_uuid(range_id), row_version
        )
        current = service.list_bands(db, principal, rng.id)
        # Saving the range alone must not re-write unchanged tiers into the audit log.
        if [_band_key(b) for b in current] != [_band_key(b) for b in bands]:
            service.set_bands(db, principal, rng.id, bands)
    except ValidationFailedError as exc:
        db.rollback()
        values = SimpleNamespace(**vars(data), id=_optional_uuid(range_id), row_version=row_version)
        values.approved_at = None
        return _range_form(
            request, db, principal, parameter, values, bands, errors | exc.errors, status=422
        )
    db.commit()
    return RedirectResponse(f"/admin/catalog/parameters/{parameter.id}", status_code=303)


@router.post("/catalog/ranges/{range_id}/approve")
def range_approve(
    request: Request,
    range_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("range.approve"))],
    row_version: Annotated[int, Form()],
    back: Annotated[str, Form()] = "",
) -> Response:
    service.approve_range(db, principal, _uuid(range_id), row_version)
    db.commit()
    return RedirectResponse(_back(back, "/admin/catalog/ranges"), status_code=303)


# Methods and comment presets


def _methods_page(
    request: Request,
    db: DB,
    principal: Principal,
    test: Any,
    errors: dict[str, str],
    error_for: str = "",
    status: int = 200,
) -> Response:
    return render(
        request,
        "catalog/methods.html",
        {
            "test": test,
            "methods": service.list_methods(db, principal, test.id),
            "presets": [
                p for p in service.list_presets(db, principal, test.id) if p.test_id == test.id
            ],
            "errors": errors,
            "error_for": error_for,
            "can_edit": principal.can("catalog.edit"),
        },
        status_code=status,
    )


@router.get("/catalog/tests/{test_id}/methods", response_class=HTMLResponse)
@page("admin/methods", "catalog/methods.html")
def methods(request: Request, test_id: str, db: DB, principal: Viewer) -> Response:
    test = service.get_test(db, principal, _uuid(test_id))
    return _methods_page(request, db, principal, test, {})


@router.post("/catalog/tests/{test_id}/methods")
def method_save(
    request: Request,
    test_id: str,
    db: DB,
    principal: Editor,
    name: Annotated[str, Form()] = "",
    is_default: Annotated[bool, Form()] = False,
    is_active: Annotated[bool, Form()] = False,
    method_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
) -> Response:
    test = service.get_test(db, principal, _uuid(test_id))
    try:
        service.save_method(
            db,
            principal,
            test.id,
            name,
            is_default,
            is_active or not method_id,
            _optional_uuid(method_id),
            row_version,
        )
    except ValidationFailedError as exc:
        db.rollback()
        target = f"method-{method_id or 'new'}"
        return _methods_page(request, db, principal, test, exc.errors, target, status=422)
    db.commit()
    return RedirectResponse(f"/admin/catalog/tests/{test.id}/methods", status_code=303)


def _presets_page(
    request: Request,
    db: DB,
    principal: Principal,
    errors: dict[str, str],
    error_for: str = "",
    status: int = 200,
) -> Response:
    tests = {t.id: t for t in service.list_tests(db, principal)}
    return render(
        request,
        "catalog/presets.html",
        {
            "presets": service.list_presets(db, principal),
            "tests": tests,
            "errors": errors,
            "error_for": error_for,
            "can_edit": principal.can("catalog.edit"),
        },
        status_code=status,
    )


@router.get("/catalog/presets", response_class=HTMLResponse)
@page("admin/methods", "catalog/presets.html")
def presets(request: Request, db: DB, principal: Viewer) -> Response:
    return _presets_page(request, db, principal, {})


@router.post("/catalog/presets")
def preset_save(
    request: Request,
    db: DB,
    principal: Editor,
    label: Annotated[str, Form()] = "",
    text: Annotated[str, Form()] = "",
    test_id: Annotated[str, Form()] = "",
    is_active: Annotated[bool, Form()] = False,
    preset_id: Annotated[str, Form()] = "",
    row_version: Annotated[int, Form()] = 0,
    back: Annotated[str, Form()] = "",
) -> Response:
    test = _optional_uuid(test_id)
    try:
        service.save_preset(
            db,
            principal,
            label,
            text,
            test,
            is_active or not preset_id,
            _optional_uuid(preset_id),
            row_version,
        )
    except ValidationFailedError as exc:
        db.rollback()
        target = f"preset-{preset_id or 'new'}"
        if test is not None and back.endswith("/methods"):
            parent = service.get_test(db, principal, test)
            return _methods_page(request, db, principal, parent, exc.errors, target, status=422)
        return _presets_page(request, db, principal, exc.errors, target, status=422)
    db.commit()
    return RedirectResponse(_back(back, "/admin/catalog/presets"), status_code=303)


# Prices


@router.get("/prices", response_class=HTMLResponse)
@page("admin/prices", "catalog/prices.html")
def prices(request: Request, db: DB, principal: Viewer, branch: str = "") -> Response:
    branch_id = _optional_uuid(branch)
    return render(
        request,
        "catalog/prices.html",
        {
            "rows": service.price_list(db, principal, branch_id),
            "branches": org.list_branches(db, principal),
            "branch": branch_id,
        },
    )


def _price_form(
    request: Request,
    db: DB,
    principal: Principal,
    item_type: str,
    item: Any,
    errors: dict[str, str],
    values: dict[str, str] | None = None,
    status: int = 200,
) -> Response:
    branches = org.list_branches(db, principal)
    history = service.price_history(db, principal, item_type, item.id)
    return render(
        request,
        "catalog/price_form.html",
        {
            "item_type": item_type,
            "item": item,
            "history": history,
            "overrides": [p for p in history if p.branch_id and p.valid_to is None],
            "branches": {b.id: b for b in branches},
            "values": values or {},
            "errors": errors,
            "can_edit": principal.can("price.edit"),
        },
        status_code=status,
    )


@router.get("/prices/{item_type}/{item_id}", response_class=HTMLResponse)
@page("admin/prices", "catalog/price_form.html")
def price_item(
    request: Request, item_type: str, item_id: str, db: DB, principal: Viewer
) -> Response:
    item = service.get_item(db, principal, item_type, _uuid(item_id))
    return _price_form(request, db, principal, item_type, item, {})


@router.post("/prices/{item_type}/{item_id}")
def price_save(
    request: Request,
    item_type: str,
    item_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("price.edit"))],
    amount: Annotated[str, Form()] = "",
    branch_id: Annotated[str, Form()] = "",
    reason: Annotated[str, Form()] = "",
) -> Response:
    item = service.get_item(db, principal, item_type, _uuid(item_id))
    try:
        service.set_price(
            db, principal, item_type, item.id, amount, _optional_uuid(branch_id), reason
        )
    except ValidationFailedError as exc:
        db.rollback()
        values = {"amount": amount, "branch_id": branch_id, "reason": reason}
        return _price_form(request, db, principal, item_type, item, exc.errors, values, status=422)
    db.commit()
    return RedirectResponse(f"/admin/prices/{item_type}/{item.id}", status_code=303)


@router.post("/prices/{item_type}/{item_id}/end")
def price_end(
    request: Request,
    item_type: str,
    item_id: str,
    db: DB,
    principal: Annotated[Principal, Depends(require("price.edit"))],
    branch_id: Annotated[str, Form()],
) -> Response:
    item = service.get_item(db, principal, item_type, _uuid(item_id))
    service.end_branch_price(db, principal, item_type, item.id, _uuid(branch_id))
    db.commit()
    return RedirectResponse(f"/admin/prices/{item_type}/{item.id}", status_code=303)


# Starter catalog


def _starter_page(
    request: Request, result: starter.ImportResult | None, status: int = 200
) -> Response:
    data = starter.load()
    return render(
        request,
        "catalog/starter.html",
        {
            "counts": {
                "departments": len(data["departments"]),
                "tests": len(data["tests"]),
                "packages": len(data["packages"]),
            },
            "result": result,
        },
        status_code=status,
    )


@router.get("/catalog/starter", response_class=HTMLResponse)
@page("admin/starter-catalog", "catalog/starter.html")
def starter_page(request: Request, principal: Editor) -> Response:
    return _starter_page(request, None)


@router.post("/catalog/starter")
def starter_import(request: Request, db: DB, principal: Editor) -> Response:
    result = starter.import_starter(db, principal)
    db.commit()
    return _starter_page(request, result)
