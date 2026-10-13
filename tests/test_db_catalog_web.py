"""The catalog and price screens, through the web, against real Postgres."""

import re
import uuid
from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.catalog import routes, starter
from labra.catalog.models import (
    CommentPreset,
    Department,
    Package,
    Price,
    ReferenceRange,
    Test,
    TestMethod,
    TestParameter,
)
from labra.core import lab_settings
from labra.core.models import AuditLog
from labra.org.models import Branch
from labra.seed import DEMO_PASSWORD


def _sign_in(client: TestClient, username: str) -> None:
    client.cookies.clear()
    page = client.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert token is not None
    r = client.post(
        "/login",
        data={"username": username, "password": DEMO_PASSWORD, "csrf_token": token.group(1)},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


def _post(client: TestClient, url: str, data: Mapping[str, object]):
    page = client.get("/")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert token is not None
    return client.post(url, data={**data, "csrf_token": token.group(1)}, follow_redirects=False)


def _one[T](db: Session, model: type[T], **where: object) -> T:
    return db.scalars(select(model).filter_by(**where)).one()


def _department(client: TestClient, db: Session, name: str = "Biochemistry") -> uuid.UUID:
    r = _post(client, "/admin/catalog/departments", {"name": name, "report_order": "20"})
    assert r.status_code == 303, r.text
    return _one(db, Department, name=name).id


def _lipid(client: TestClient, db: Session) -> Test:
    """A lipid profile with TC, TG and HDL, made through the screens."""
    dept = _department(client, db)
    r = _post(
        client,
        "/admin/catalog/tests",
        {"code": "lipid", "name": "Lipid profile", "department_id": str(dept), "aliases": "lp"},
    )
    assert r.status_code == 303, r.text
    test = _one(db, Test, code="lipid")
    for order, (code, name) in enumerate(
        [("TC", "Total cholesterol"), ("TG", "Triglycerides"), ("HDL", "HDL cholesterol")]
    ):
        r = _post(
            client,
            "/admin/catalog/parameters",
            {
                "test_id": str(test.id),
                "code": code,
                "name": name,
                "result_type": "numeric",
                "unit_ucum": "mg/dL",
                "display_order": str(order * 10),
                "is_reportable": "true",
            },
        )
        assert r.status_code == 303, r.text
    return test


# Who sees what


@pytest.mark.item("M14")
def test_front_desk_sees_the_catalog_but_cannot_change_it(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    _sign_in(db_client, "priya")
    page = db_client.get("/admin/catalog")
    assert page.status_code == 200
    assert "lipid" in page.text and "Add test" not in page.text
    detail = db_client.get(f"/admin/catalog/tests/{test.id}")
    assert detail.status_code == 200 and '<fieldset class="form-grid" disabled' in detail.text
    assert db_client.get("/admin/prices").status_code == 200
    for url in ("/admin/catalog/tests/new", "/admin/catalog/starter"):
        assert db_client.get(url).status_code == 403, url
    for url, data in (
        ("/admin/catalog/tests", {"code": "x", "name": "X"}),
        ("/admin/catalog/starter", {}),
        (f"/admin/prices/test/{test.id}", {"amount": "100"}),
    ):
        assert _post(db_client, url, data).status_code == 403, url
    assert not seeded.scalars(select(Price)).all()


@pytest.mark.item("M14")
def test_every_catalog_screen_renders(seeded: Session, db_client: TestClient) -> None:
    _sign_in(db_client, "anil")
    assert "The catalog is empty." in db_client.get("/admin/catalog").text
    r = _post(db_client, "/admin/catalog/starter", {})
    assert r.status_code == 200 and "Starter catalog imported." in r.text
    lipid = _one(seeded, Test, code="lipid")
    ldl = _one(seeded, TestParameter, test_id=lipid.id, code="LDL")
    rng = seeded.scalars(
        select(ReferenceRange).where(ReferenceRange.parameter_id == ldl.id)
    ).first()
    package = seeded.scalars(select(Package)).first()
    assert rng is not None and package is not None
    for url in (
        "/admin/catalog",
        "/admin/catalog?q=lp",
        f"/admin/catalog?department={lipid.department_id}",
        "/admin/catalog/tests/new",
        f"/admin/catalog/tests/{lipid.id}",
        f"/admin/catalog/tests/{lipid.id}/parameters/new",
        f"/admin/catalog/parameters/{ldl.id}",
        f"/admin/catalog/parameters/{ldl.id}/ranges/new",
        f"/admin/catalog/ranges/{rng.id}",
        "/admin/catalog/ranges",
        "/admin/catalog/departments",
        "/admin/catalog/packages",
        "/admin/catalog/packages/new",
        f"/admin/catalog/packages/{package.id}",
        f"/admin/catalog/tests/{lipid.id}/methods",
        "/admin/catalog/presets",
        "/admin/catalog/starter",
        "/admin/prices",
        f"/admin/prices?branch={_one(seeded, Branch, code='B2').id}",
        f"/admin/prices/test/{lipid.id}",
        f"/admin/prices/package/{package.id}",
    ):
        page = db_client.get(url)
        assert page.status_code == 200, (url, page.text)
        assert 'class="btn-sm-ghost" href="' in page.text, url  # the manual link
    assert "waiting for a signatory" in db_client.get("/admin/catalog").text
    assert db_client.get("/admin/catalog/tests/not-an-id").status_code == 404
    assert db_client.get(f"/admin/prices/visit/{lipid.id}").status_code == 404


@pytest.mark.item("EC-F03")
def test_catalog_lists_paginate(seeded: Session, db_client: TestClient) -> None:
    _sign_in(db_client, "anil")
    assert _post(db_client, "/admin/catalog/starter", {}).status_code == 200
    first = db_client.get("/admin/catalog").text
    assert first.count(">Edit</a>") == 25
    assert 'href="/admin/catalog?page=2" rel="next"' in first
    assert 'rel="prev"' not in first
    second = db_client.get("/admin/catalog?page=2").text
    assert 'href="/admin/catalog?page=1" rel="prev"' in second
    # The pager keeps the search and filters.
    found = db_client.get("/admin/catalog?q=a&page=2").text
    assert 'href="/admin/catalog?q=a&amp;page=1" rel="prev"' in found
    # Search runs in the database: code or name contains the text, or an alias starts with it.
    assert "Lipid profile" in db_client.get("/admin/catalog?q=lp").text
    assert "Lipid profile" in db_client.get("/admin/catalog?q=LIPID").text
    assert "No tests found." in db_client.get("/admin/catalog?q=%25").text
    prices = db_client.get("/admin/prices").text
    assert prices.count('href="/admin/prices/test/') == 25
    assert 'href="/admin/prices?page=2" rel="next"' in prices
    for url in ("/admin/catalog/ranges", "/admin/catalog/ranges?page=2", "/admin/prices?page=9"):
        assert db_client.get(url).status_code == 200, url


@pytest.mark.item("M14.1")
def test_a_page_number_that_is_not_a_number_shows_the_first_page(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    assert _post(db_client, "/admin/catalog/starter", {}).status_code == 200
    for url in (
        "/admin/catalog",
        "/admin/catalog/packages",
        "/admin/catalog/ranges",
        "/admin/catalog/presets",
        "/admin/prices",
        "/admin/branches",
        "/admin/users",
    ):
        for page in ("abc", "-3", "0", "9" * 5000, "٣"):
            assert db_client.get(url, params={"page": page}).status_code == 200, (url, page)
    assert 'rel="prev"' not in db_client.get("/admin/catalog?page=abc").text


@pytest.mark.item("M14.1")
def test_a_list_edited_on_its_second_page_stays_there(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    for n in range(26):
        saved = _post(
            db_client, "/admin/catalog/presets", {"label": f"Note {n:02d}", "text": "Repeat."}
        )
        assert saved.status_code == 303
    second = db_client.get("/admin/catalog/presets?page=2").text
    assert second.count('action="/admin/catalog/presets?page=2"') == 2
    refused = _post(db_client, "/admin/catalog/presets?page=2", {"label": "", "text": ""})
    assert refused.status_code == 422
    assert "Page 2" in refused.text and 'rel="prev"' in refused.text
    saved = _post(
        db_client, "/admin/catalog/presets?page=2", {"label": "Note 26", "text": "Repeat."}
    )
    assert saved.headers["location"] == "/admin/catalog/presets?page=2"
    # The two lists on the setup screen keep their own page numbers.
    saved = _post(db_client, "/admin/catalog/specimens?dpage=2&spage=3", {"code": "", "name": ""})
    assert saved.status_code == 422
    assert 'action="/admin/catalog/departments?dpage=2&amp;spage=3"' in saved.text


# Saving


@pytest.mark.item("M05")
@pytest.mark.item("M14")
def test_a_refused_save_keeps_what_was_typed(seeded: Session, db_client: TestClient) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    r = _post(
        db_client,
        "/admin/catalog/tests",
        {"code": "Bad Code", "name": "Thyroid profile", "department_id": "", "aliases": "tp"},
    )
    assert r.status_code == 422
    assert 'value="Thyroid profile"' in r.text and 'value="tp"' in r.text
    r = _post(
        db_client,
        "/admin/catalog/parameters",
        {
            "test_id": str(test.id),
            "code": "LDL",
            "name": "LDL cholesterol",
            "result_type": "calculated",
            "formula": "TC - HDL - VLDL",
        },
    )
    assert r.status_code == 422 and 'value="TC - HDL - VLDL"' in r.text
    tc = _one(seeded, TestParameter, test_id=test.id, code="TC")
    r = _post(
        db_client,
        "/admin/catalog/parameters",
        {
            "test_id": str(test.id),
            "parameter_id": str(tc.id),
            "row_version": str(tc.row_version),
            "code": "TC",
            "name": "Total cholesterol",
            "result_type": "numeric",
            "unit_ucum": "not-a-unit",
            "is_active": "true",
        },
    )
    assert r.status_code == 422 and f'name="parameter_id" value="{tc.id}"' in r.text


@pytest.mark.item("M05")
@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("/admin/catalog/tests", "Enter the test name."),
        ("/admin/catalog/departments", "Enter the department name."),
        ("/admin/catalog/specimens", "Enter the specimen name."),
        ("/admin/catalog/packages", "Enter the package name."),
        ("/admin/catalog/presets", "Enter the comment."),
    ],
)
def test_an_empty_form_shows_the_problems_on_the_page(
    seeded: Session, db_client: TestClient, url: str, message: str
) -> None:
    _sign_in(db_client, "anil")
    r = _post(db_client, url, {})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("text/html") and message in r.text


@pytest.mark.item("M05")
@pytest.mark.item("EC-B03")
def test_a_stale_save_through_the_screen_names_who_changed_it(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    form = {
        "test_id": str(test.id),
        "row_version": str(test.row_version),
        "code": "lipid",
        "department_id": str(test.department_id),
        "is_active": "true",
    }
    assert _post(db_client, "/admin/catalog/tests", form | {"name": "Lipids"}).status_code == 303
    r = _post(db_client, "/admin/catalog/tests", form | {"name": "Lipid panel"})
    assert r.status_code == 409
    assert "Anil Kumar changed this record at " in r.text
    seeded.refresh(test)
    assert test.name == "Lipids"


@pytest.mark.item("M05.2")
def test_options_post_with_their_abnormal_and_default_marks(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    r = _post(
        db_client,
        "/admin/catalog/parameters",
        {
            "test_id": str(test.id),
            "code": "APP",
            "name": "Appearance",
            "result_type": "option",
            "option_value": ["Clear", "Turbid", "", "Milky"],
            "option_abnormal": ["1", "3"],
            "option_default": "0",
        },
    )
    assert r.status_code == 303, r.text
    assert _one(seeded, TestParameter, code="APP").options == [
        {"value": "Clear", "abnormal": False, "default": True},
        {"value": "Turbid", "abnormal": True, "default": False},
        {"value": "Milky", "abnormal": True, "default": False},
    ]


# Ranges


def _range_form(param: TestParameter, **extra: object) -> dict[str, object]:
    return {
        "parameter_id": str(param.id),
        "sex": "",
        "age_min": "18",
        "age_min_unit": "years",
        "low": "",
        "high": "200",
        "source_citation": "NCEP ATP III",
        "band_label": ["Desirable", "Borderline high", "High"],
        "band_severity": ["normal", "borderline", "abnormal"],
        "band_low": ["", "200", "240"],
        "band_high": ["199", "239", ""],
    } | extra


@pytest.mark.item("M05.2")
def test_a_range_saved_on_screen_waits_for_the_signatory(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    tc = _one(seeded, TestParameter, test_id=test.id, code="TC")
    r = _post(db_client, "/admin/catalog/ranges", _range_form(tc))
    assert r.status_code == 303, r.text
    rng = _one(seeded, ReferenceRange, parameter_id=tc.id)
    assert rng.age_min_days == starter.ADULT_FROM_DAYS and rng.approved_at is None
    page = db_client.get(f"/admin/catalog/ranges/{rng.id}")
    assert 'value="18"' in page.text and "Waiting for approval" in page.text
    assert "Approve this range" not in page.text
    approve = {"row_version": str(rng.row_version)}
    assert _post(db_client, f"/admin/catalog/ranges/{rng.id}/approve", approve).status_code == 403

    _sign_in(db_client, "meera")
    assert "NCEP ATP III" in db_client.get("/admin/catalog/ranges").text
    r = _post(db_client, f"/admin/catalog/ranges/{rng.id}/approve", approve)
    assert r.status_code == 303 and r.headers["location"] == "/admin/catalog/ranges"
    seeded.refresh(rng)
    assert rng.approved_at is not None
    assert "Every range in use is approved." in db_client.get("/admin/catalog/ranges").text
    assert _post(db_client, "/admin/catalog/ranges", _range_form(tc)).status_code == 403


@pytest.mark.item("M05.2")
def test_saving_a_range_with_its_tiers_unchanged_does_not_rewrite_them(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    tc = _one(seeded, TestParameter, test_id=test.id, code="TC")
    assert _post(db_client, "/admin/catalog/ranges", _range_form(tc)).status_code == 303
    rng = _one(seeded, ReferenceRange, parameter_id=tc.id)

    def band_audits() -> int:
        return (
            seeded.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "range.bands")
            )
            or 0
        )

    assert band_audits() == 1
    edit = {"range_id": str(rng.id), "row_version": str(rng.row_version), "is_active": "true"}
    r = _post(db_client, "/admin/catalog/ranges", _range_form(tc, display_text="Up to 200") | edit)
    assert r.status_code == 303, r.text
    assert band_audits() == 1
    seeded.refresh(rng)
    r = _post(
        db_client,
        "/admin/catalog/ranges",
        _range_form(tc, band_high=["199", "239", "999"])
        | edit
        | {"row_version": str(rng.row_version)},
    )
    assert r.status_code == 303, r.text
    assert band_audits() == 2


@pytest.mark.item("M05.2")
def test_a_refused_range_shows_the_problem_and_keeps_the_age(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    tc = _one(seeded, TestParameter, test_id=test.id, code="TC")
    r = _post(
        db_client,
        "/admin/catalog/ranges",
        _range_form(tc, age_min="6", age_min_unit="months", low="250", high="200"),
    )
    assert r.status_code == 422
    assert 'value="6"' in r.text and '<option value="months" selected>' in r.text
    r = _post(db_client, "/admin/catalog/ranges", _range_form(tc, age_min="1.5"))
    assert r.status_code == 422 and "whole number of years" in r.text
    assert not seeded.scalars(select(ReferenceRange)).all()


@pytest.mark.item("M05.2")
@pytest.mark.parametrize(
    "back", ["https://elsewhere.example/", "//elsewhere.example/admin/catalog", "/login"]
)
def test_approval_returns_only_to_a_catalog_screen(
    seeded: Session, db_client: TestClient, back: str
) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    tc = _one(seeded, TestParameter, test_id=test.id, code="TC")
    _post(db_client, "/admin/catalog/ranges", _range_form(tc))
    rng = _one(seeded, ReferenceRange, parameter_id=tc.id)
    _sign_in(db_client, "meera")
    r = _post(
        db_client,
        f"/admin/catalog/ranges/{rng.id}/approve",
        {"row_version": str(rng.row_version), "back": back},
    )
    assert r.headers["location"] == "/admin/catalog/ranges"


@pytest.mark.item("M05.2")
@pytest.mark.parametrize(
    ("days", "shown"), [(0, ("0", "years")), (6574, ("18", "years")), (182, ("6", "months"))]
)
def test_ages_are_shown_in_the_unit_they_were_typed_in(days: int, shown: tuple[str, str]) -> None:
    assert routes._age_parts(days) == shown
    assert routes._age_days(*shown, {}, "age", -1) == days


# Methods, presets and packages


@pytest.mark.item("M05")
def test_methods_and_presets_through_the_screen(seeded: Session, db_client: TestClient) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    url = f"/admin/catalog/tests/{test.id}/methods"
    assert (
        _post(db_client, url, {"name": "Enzymatic (CHOD-PAP)", "is_default": "true"}).status_code
        == 303
    )
    assert _post(db_client, url, {"name": "Direct"}).status_code == 303
    r = _post(db_client, url, {"name": "direct"})
    assert r.status_code == 422 and "already has the method" in r.text
    r = _post(db_client, url, {"name": " "})
    assert r.status_code == 422 and "Enter the method name." in r.text
    methods = seeded.scalars(select(TestMethod).where(TestMethod.test_id == test.id)).all()
    assert sorted((m.name, m.is_default) for m in methods) == [
        ("Direct", False),
        ("Enzymatic (CHOD-PAP)", True),
    ]

    form = {
        "label": "Lipaemic",
        "text": "Sample lipaemic; repeat fasting.",
        "test_id": str(test.id),
    }
    r = _post(db_client, "/admin/catalog/presets", form | {"back": url})
    assert r.status_code == 303 and r.headers["location"] == url
    assert "Sample lipaemic; repeat fasting." in db_client.get(url).text
    r = _post(db_client, "/admin/catalog/presets", form | {"text": "", "back": url})
    assert r.status_code == 422 and "methods and comments" in r.text
    r = _post(db_client, "/admin/catalog/presets", {"label": "Any", "text": "Repeat advised."})
    assert r.status_code == 303 and r.headers["location"] == "/admin/catalog/presets"


@pytest.mark.item("M05")
def test_a_package_through_the_screen(seeded: Session, db_client: TestClient) -> None:
    _sign_in(db_client, "anil")
    lipid = _lipid(db_client, seeded)
    r = _post(
        db_client,
        "/admin/catalog/tests",
        {"code": "lft", "name": "Liver function test", "department_id": str(lipid.department_id)},
    )
    assert r.status_code == 303
    lft = _one(seeded, Test, code="lft")
    r = _post(
        db_client,
        "/admin/catalog/packages",
        {"code": "lft+lp", "name": "Liver and lipid", "test_ids": [str(lipid.id)]},
    )
    assert r.status_code == 422 and 'value="Liver and lipid"' in r.text
    r = _post(
        db_client,
        "/admin/catalog/packages",
        {"code": "lft+lp", "name": "Liver and lipid", "test_ids": [str(lipid.id), str(lft.id)]},
    )
    assert r.status_code == 303, r.text
    assert "lft, lipid" in db_client.get("/admin/catalog/packages").text


@pytest.mark.item("M14.1")
def test_tests_are_picked_by_code_not_from_a_list_of_every_test(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    assert _post(db_client, "/admin/catalog/starter", {}).status_code == 200
    # Neither form lists the catalog: it is longer than any list may be.
    blank = db_client.get("/admin/catalog/packages/new").text
    assert 'name="test_codes"' in blank and 'name="test_ids"' not in blank
    presets = db_client.get("/admin/catalog/presets").text
    assert 'name="test_code"' in presets and 'name="test_id">' not in presets

    form = {"code": "sugar+fat", "name": "Sugar and lipids"}
    r = _post(db_client, "/admin/catalog/packages", form | {"test_codes": "FBS, nosuch  lipid"})
    assert r.status_code == 422
    assert "No test in use has the code nosuch." in r.text
    # What was found is ticked, and only the wrong code is left to correct.
    assert r.text.count('name="test_ids"') == 2 and 'name="test_codes" value="nosuch"' in r.text
    fbs, lipid = _one(seeded, Test, code="fbs"), _one(seeded, Test, code="lipid")
    r = _post(db_client, "/admin/catalog/packages", form | {"test_codes": "fbs lipid"})
    assert r.status_code == 303, r.text
    package = _one(seeded, Package, code="sugar+fat")
    edit = db_client.get(f"/admin/catalog/packages/{package.id}").text
    assert edit.count('name="test_ids"') == 2
    # Unticking one and typing another swaps them.
    changed = {
        "package_id": str(package.id),
        "row_version": package.row_version,
        "is_active": "true",
        "test_ids": [str(fbs.id)],
        "test_codes": "urm",
    }
    r = _post(db_client, "/admin/catalog/packages", form | changed)
    assert r.status_code == 303, r.text
    # "urm" is an alias of the urine test, and finds it as it does at the front desk.
    assert "fbs, urine" in db_client.get("/admin/catalog/packages").text

    note = {"label": "Lipaemic", "text": "Sample lipaemic; repeat fasting."}
    r = _post(db_client, "/admin/catalog/presets", note | {"test_code": "nosuch"})
    assert r.status_code == 422 and "Type the code of one test in use" in r.text
    r = _post(db_client, "/admin/catalog/presets", note | {"test_code": "LIPID"})
    assert r.status_code == 303
    assert _one(seeded, CommentPreset, label="Lipaemic").test_id == lipid.id
    listing = db_client.get("/admin/catalog/presets").text
    assert f'href="/admin/catalog/tests/{lipid.id}/methods">lipid<' in listing


# Prices


@pytest.mark.item("M06")
def test_prices_through_the_screen(seeded: Session, db_client: TestClient) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    b2 = _one(seeded, Branch, code="B2")
    url = f"/admin/prices/test/{test.id}"
    assert _post(db_client, url, {"amount": "600"}).status_code == 303
    assert _post(db_client, url, {"amount": "550", "branch_id": str(b2.id)}).status_code == 303
    r = _post(db_client, url, {"amount": "12.345", "reason": "typo"})
    assert r.status_code == 422 and 'value="12.345"' in r.text
    listing = db_client.get(f"/admin/prices?branch={b2.id}").text
    assert "600.00" in listing and "550.00" in listing
    page = db_client.get(url).text
    assert "Use the lab price again" in page and "Every branch" in page
    assert _post(db_client, f"{url}/end", {"branch_id": str(b2.id)}).status_code == 303
    assert "Use the lab price again" not in db_client.get(url).text
    open_prices = seeded.scalars(select(Price).where(Price.valid_to.is_(None))).all()
    assert [(p.branch_id, str(p.amount)) for p in open_prices] == [(None, "600.00")]


@pytest.mark.item("M23.1")
def test_price_headings_use_the_currency_symbol_from_settings(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    urls = ("/admin/catalog", "/admin/prices", f"/admin/prices/test/{test.id}")
    for symbol, heading in (("₹", "rice (₹)<"), ("Rs", "rice (Rs)<"), ("", "rice<")):
        lab_settings.set_value(seeded, "currency.symbol", symbol, None)
        for url in urls:
            page = db_client.get(url).text
            assert heading in page, (symbol, url)
            assert symbol == "₹" or "₹" not in page, (symbol, url)


# Starter catalog


@pytest.mark.item("M24")
def test_starter_import_through_the_screen_is_safe_to_repeat(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    page = db_client.get("/admin/catalog/starter")
    assert "Import the starter catalog" in page.text
    first = _post(db_client, "/admin/catalog/starter", {})
    tests = seeded.scalar(select(func.count()).select_from(Test))
    assert f"Added {tests} tests" in " ".join(first.text.split())
    again = _post(db_client, "/admin/catalog/starter", {})
    assert "Added 0 tests" in " ".join(again.text.split())
    assert seeded.scalar(select(func.count()).select_from(Test)) == tests


@pytest.mark.item("M14.2")
def test_a_version_that_is_not_a_number_counts_as_out_of_date(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    test = _lipid(db_client, seeded)
    form = {
        "test_id": str(test.id),
        "code": "lipid",
        "name": "Lipids",
        "department_id": str(test.department_id),
        "is_active": "true",
    }
    for version in ("abc", "", "-1", "1.5", "9" * 5000):
        r = _post(db_client, "/admin/catalog/tests", form | {"row_version": version})
        assert r.status_code == 409, version
        assert "changed this record" in r.text
    seeded.refresh(test)
    assert test.name != "Lipids"


@pytest.mark.item("M14.2")
def test_pager_links_after_a_refused_specimen_lead_back_to_the_list(
    seeded: Session, db_client: TestClient
) -> None:
    _sign_in(db_client, "anil")
    for n in range(26):
        saved = _post(
            db_client, "/admin/catalog/specimens", {"code": f"tube{n:02d}", "name": f"Tube {n:02d}"}
        )
        assert saved.status_code == 303, saved.text
    refused = _post(db_client, "/admin/catalog/specimens?spage=2", {"code": "", "name": ""})
    assert refused.status_code == 422
    assert 'href="/admin/catalog/departments?spage=1" rel="prev"' in refused.text
    assert 'href="/admin/catalog/specimens' not in refused.text
