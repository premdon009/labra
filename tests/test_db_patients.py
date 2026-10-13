"""Patients and referrers: registering, the duplicate warning, branch scope, stale edits."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core import ids
from labra.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.patients import service
from labra.patients.models import Patient, Referrer
from tests.conftest import SEED_DAY
from tests.frontdesk import as_user, branch, patient_input, register, visit_at


def _audit(db: Session, entity_id: object) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog).where(AuditLog.entity_id == str(entity_id)).order_by(AuditLog.id)
        )
    )


@pytest.mark.item("M03")
def test_register_patient_number_and_audit(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    first = register(seeded, priya, full_name="  Sunita   Testcase ", title="Ms")
    second = register(seeded, priya, full_name="Ramesh Testcase", sex="M", phone="9000000002")
    assert (first.patient_no, second.patient_no) == ("B2/P/000001", "B2/P/000002")
    assert first.registered_branch_id == branch(seeded, "B2").id
    assert first.full_name == "Sunita Testcase"
    assert (first.dob, first.dob_is_estimated) == (date(1992, 10, 9), True)
    [row] = _audit(seeded, first.id)
    assert (row.action, row.user_id, row.branch_id) == (
        "patient.create",
        priya.user_id,
        first.registered_branch_id,
    )
    assert row.detail == {}


@pytest.mark.item("M03")
def test_patient_form_checks(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    bad = patient_input(
        full_name=" ",
        sex="X",
        age_years=None,
        phone="12345",
        alt_phone="5000000000",
        email="nobody",
        pincode="012345",
    )
    with pytest.raises(ValidationFailedError) as exc:
        service.register_patient(seeded, priya, bad, SEED_DAY)
    assert set(exc.value.errors) == {
        "full_name",
        "sex",
        "dob",
        "phone",
        "alt_phone",
        "email",
        "pincode",
    }
    for age in ({"age_years": 151}, {"age_months": 12}, {"age_days": 31}, {"age_years": -1}):
        with pytest.raises(ValidationFailedError) as exc:
            register(seeded, priya, **{"age_years": None, **age})
        assert set(exc.value.errors) == {"dob"}
    with pytest.raises(ValidationFailedError):
        register(seeded, priya, age_years=None, dob=date(1875, 10, 9))
    known = register(seeded, priya, age_years=None, dob=date(1876, 10, 9))
    assert (known.dob, known.dob_is_estimated) == (date(1876, 10, 9), False)
    assert seeded.scalar(select(Patient.id).where(Patient.phone == "12345")) is None


@pytest.mark.item("M03")
def test_future_dob_refused_ist_midnight(
    seeded: Session, platform: Platform, monkeypatch: pytest.MonkeyPatch
) -> None:
    priya = as_user(seeded, platform, "priya")

    def clock_at(moment: datetime) -> None:
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                return moment.astimezone(tz)

        monkeypatch.setattr(ids, "datetime", Clock)

    born = patient_input(age_years=None, dob=date(2026, 10, 10))
    # 23:30 in India on the 9th: a baby dated the 10th isn't born yet.
    clock_at(datetime(2026, 10, 9, 18, 0, tzinfo=UTC))
    with pytest.raises(ValidationFailedError) as exc:
        service.register_patient(seeded, priya, born)
    assert exc.value.errors == {"dob": "The date of birth can't be after today."}
    # 00:30 in India on the 10th, still the 9th in UTC.
    clock_at(datetime(2026, 10, 9, 19, 0, tzinfo=UTC))
    assert service.register_patient(seeded, priya, born).dob == date(2026, 10, 10)


@pytest.mark.item("M03")
@pytest.mark.item("EC-B03")
def test_duplicate_phone_name_warns(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    kavya = as_user(seeded, platform, "b3desk")
    first = register(seeded, priya)

    with pytest.raises(service.PossibleDuplicateError) as exc:
        register(seeded, priya, full_name="Suneeta Testcase")
    assert [p.id for p in exc.value.hint.matches] == [first.id]
    assert not exc.value.hint.elsewhere
    with pytest.raises(service.PossibleDuplicateError):
        register(seeded, priya, full_name="sunita  testcase")
    assert seeded.scalar(select(Patient.id).where(Patient.full_name == "Suneeta Testcase")) is None

    # Another branch learns only that someone like this may exist.
    with pytest.raises(service.PossibleDuplicateError) as exc:
        register(seeded, kavya)
    assert exc.value.hint.matches == []
    assert exc.value.hint.elsewhere
    assert "another branch" in exc.value.errors["duplicate"]

    # A family member on the same phone is not a duplicate.
    assert register(seeded, priya, full_name="Ramesh Testcase", sex="M").patient_no
    confirmed = service.register_patient(
        seeded, priya, patient_input(full_name="Suneeta Testcase"), SEED_DAY, confirm_new=True
    )
    assert confirmed.id != first.id


@pytest.mark.item("M03")
@pytest.mark.item("EC-A05")
def test_patient_scope_follows_branches(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    kavya = as_user(seeded, platform, "b3desk")
    patient = register(seeded, priya)
    assert service.get_patient(seeded, priya, patient.id) is patient
    assert service.find_patients(seeded, kavya, "", 1).items == []
    assert service.find_patients(seeded, kavya, "9000000001", 1).items == []
    with pytest.raises(NotFoundError):
        service.get_patient(seeded, kavya, patient.id)
    with pytest.raises(NotFoundError):
        service.update_patient(
            seeded, kavya, patient.id, patient_input(), patient.row_version, SEED_DAY
        )
    # A visit at B3 makes the patient known there.
    visit_at(seeded, patient, "B3")
    assert service.find_patients(seeded, kavya, "", 1).items == [patient]
    assert service.get_patient(seeded, kavya, patient.id) is patient
    # A technician has no patient permission at all.
    suresh = as_user(seeded, platform, "suresh")
    assert service.find_patients(seeded, suresh, "", 1).items == []
    with pytest.raises(PermissionDeniedError):
        register(seeded, suresh, phone="9000000009")


@pytest.mark.item("M03")
def test_find_patients(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    sunita = register(seeded, priya)
    ramesh = register(
        seeded,
        priya,
        full_name="Ramesh Testcase",
        sex="M",
        phone="9111111111",
        alt_phone="9000000777",
    )

    def found(q: str) -> list[Patient]:
        return service.find_patients(seeded, priya, q, 1).items

    assert {p.id for p in found("")} == {ramesh.id, sunita.id}
    assert found("9000000") == [ramesh, sunita]
    assert found("9111111111") == [ramesh]
    assert found("p/000001") == [sunita]
    assert found("Suneeta Testcase")[0] == sunita
    assert found("rames") == [ramesh]
    assert found("100%") == []
    assert found("Nobody Atall") == []


@pytest.mark.item("M03")
def test_stale_patient_edit(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    patient = register(seeded, priya)
    opened = patient.row_version
    changed = service.update_patient(
        seeded,
        priya,
        patient.id,
        patient_input(dob=patient.dob, age_years=None, city="Mysuru"),
        opened,
        SEED_DAY,
    )
    # The form sends the stored date back; an estimate stays an estimate.
    assert (changed.city, changed.dob_is_estimated) == ("Mysuru", True)
    assert changed.row_version == opened + 1
    with pytest.raises(ConflictError) as exc:
        service.update_patient(
            seeded, priya, patient.id, patient_input(city="Hubballi"), opened, SEED_DAY
        )
    assert "Priya Sharma changed this record" in exc.value.public_message
    assert patient.city == "Mysuru"
    rows = _audit(seeded, patient.id)
    assert [r.action for r in rows] == ["patient.create", "patient.update"]
    # Field names only: the values are personal data.
    assert rows[1].detail == {"fields": ["city"]}
    exact = service.update_patient(
        seeded,
        priya,
        patient.id,
        patient_input(dob=date(1992, 5, 1), age_years=None, city="Mysuru"),
        changed.row_version,
        SEED_DAY,
    )
    assert (exact.dob, exact.dob_is_estimated) == (date(1992, 5, 1), False)
    # Saving with nothing changed writes no audit row.
    service.update_patient(
        seeded,
        priya,
        patient.id,
        patient_input(dob=date(1992, 5, 1), age_years=None, city="Mysuru"),
        exact.row_version,
        SEED_DAY,
    )
    assert len(_audit(seeded, patient.id)) == 3


@pytest.mark.item("M04")
def test_referrer_create_update(seeded: Session, platform: Platform) -> None:
    priya = as_user(seeded, platform, "priya")
    kavya = as_user(seeded, platform, "b3desk")
    data = service.ReferrerInput("doctor", " Dr  Asha Testcase ", "MBBS", "KMC 00000", "9000000003")
    referrer = service.create_referrer(seeded, priya, data)
    assert (referrer.name, referrer.is_active) == ("Dr Asha Testcase", True)
    # One list for the whole lab.
    assert service.referrer_page(seeded, kavya, 1, "asha").items == [referrer]
    assert service.pick_referrers(seeded, kavya, "Dr Aasha Testcase") == [referrer]

    opened = referrer.row_version
    data.is_active = False
    service.update_referrer(seeded, kavya, referrer.id, data, opened)
    assert service.pick_referrers(seeded, priya, "asha") == []
    assert service.referrer_page(seeded, priya, 1).items == [referrer]
    with pytest.raises(ConflictError):
        service.update_referrer(seeded, priya, referrer.id, data, opened)
    rows = _audit(seeded, referrer.id)
    assert [(r.action, r.detail) for r in rows] == [
        ("referrer.create", {}),
        ("referrer.update", {"fields": ["is_active"]}),
    ]

    with pytest.raises(ValidationFailedError) as exc:
        service.create_referrer(seeded, priya, service.ReferrerInput("agent", " ", phone="123"))
    assert set(exc.value.errors) == {"kind", "name", "phone"}
    suresh = as_user(seeded, platform, "suresh")
    with pytest.raises(PermissionDeniedError):
        service.referrer_page(seeded, suresh, 1)
    with pytest.raises(PermissionDeniedError):
        service.create_referrer(seeded, suresh, data)
    assert seeded.scalar(select(Referrer).where(Referrer.kind == "agent")) is None
