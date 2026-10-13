"""The visit, bill, dues and print screens, through the browser's requests."""

import re
import uuid
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from labra.billing.models import Bill, Payment, Refund
from labra.core.registry import Platform
from labra.patients.models import Referrer
from labra.visits.models import Sample, Visit
from labra.web.shortcuts import SHORTCUTS
from tests.frontdesk import as_user, billed, menu, post, sample, sign_in

UTR = "426112345678"
MANUAL = Path(__file__).parent.parent / "docs" / "manual"
_SHORTCUT = re.compile(r'data-shortcut="([^"]+)"')


def _form(ids: Mapping[str, uuid.UUID], *codes: str, **changes: object) -> dict[str, object]:
    """The visit screen filled in for a new patient, consent ticked."""
    form: dict[str, object] = {
        "client_ref": str(uuid.uuid4()),
        "full_name": "Sunita Testcase",
        "sex": "F",
        "age_years": "34",
        "phone": "9000000001",
        "consent": "true",
        "item": [f"{'package' if code == 'basic' else 'test'}:{ids[code]}" for code in codes],
    }
    return form | changes


def _saved(seeded: Session, client: TestClient, form: Mapping[str, object]) -> Bill:
    response = post(client, "/frontdesk/visits", form)
    assert response.status_code == 303, response.text
    visit_id = response.headers["location"].split("/")[-1].split("?")[0]
    return seeded.scalars(select(Bill).where(Bill.visit_id == uuid.UUID(visit_id))).one()


@pytest.mark.item("M18")
@pytest.mark.item("M07")
@pytest.mark.item("EC-B07")
def test_visit_saved_from_one_screen_only_once(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    sign_in(db_client, "priya")
    screen = db_client.get("/frontdesk/visits/new").text
    for name in ("client_ref", "phone", "full_name", "q", "discount_value", "pay_amount"):
        assert f'name="{name}"' in screen
    assert 'name="consent"' in screen
    # Every change to the order waits its turn, so a late reply can't show an old total.
    changes = screen.count('hx-post="/frontdesk/visits/new/preview"')
    assert changes >= 4
    assert screen.count('hx-sync="#visit-form:queue all"') == changes

    form = _form(ids, "fbs", "lipid", pay_mode="cash", pay_amount="530")
    first = post(db_client, "/frontdesk/visits", form)
    again = post(db_client, "/frontdesk/visits", form)

    assert first.status_code == again.status_code == 303
    assert first.headers["location"] == again.headers["location"]
    assert seeded.scalar(select(func.count()).select_from(Visit)) == 1
    assert seeded.scalar(select(func.count()).select_from(Payment)) == 1
    visit = seeded.scalars(select(Visit)).one()
    assert first.headers["location"] == f"/frontdesk/visits/{visit.id}?print=1"
    bill = seeded.scalars(select(Bill)).one()
    assert (bill.net, bill.paid, bill.status) == (Decimal(530), Decimal(530), "paid")

    # Saving goes straight to the bill, which prints itself and comes back to the visit.
    to_print = db_client.get(first.headers["location"], follow_redirects=False)
    assert to_print.headers["location"] == f"/frontdesk/bills/{bill.id}/print?auto=1&then=labels"
    printing = db_client.get(to_print.headers["location"]).text
    labels = f"/frontdesk/visits/{visit.id}/labels?print=1"
    assert f'data-autoprint data-after-print="{labels}"' in printing
    assert (
        f'data-autoprint data-after-print="/frontdesk/visits/{visit.id}"'
        in db_client.get(labels).text
    )
    alone = db_client.get(f"/frontdesk/bills/{bill.id}/print?auto=1").text
    assert f'data-after-print="/frontdesk/visits/{visit.id}"' in alone
    assert "data-autoprint" not in db_client.get(f"/frontdesk/bills/{bill.id}/print").text

    summary = db_client.get(f"/frontdesk/visits/{visit.id}").text
    assert visit.visit_no in summary and bill.bill_no in summary
    assert "Sunita Testcase" in summary and "Grey top" in summary
    assert "Take payment" not in summary

    # Someone already registered: the screen offers them by phone and skips the consent tick.
    match = db_client.get("/frontdesk/visits/new/patient?phone=9000000001").text
    assert f"/frontdesk/visits/new?patient_id={visit.patient_id}" in match
    assert "No patient here" in db_client.get("/frontdesk/visits/new/patient?phone=9000000009").text
    assert db_client.get("/frontdesk/visits/new/patient?phone=900").text.strip() == ""
    known = db_client.get(f"/frontdesk/visits/new?patient_id={visit.patient_id}").text
    assert "Consent on file" in known and 'name="consent"' not in known
    assert 'name="full_name"' not in known


@pytest.mark.item("M18")
@pytest.mark.item("EC-C01")
def test_visit_screen_says_what_is_wrong(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    sign_in(db_client, "priya")

    typed = post(db_client, "/frontdesk/visits", _form(ids, "fbs", q="lip"))
    assert typed.status_code == 422
    assert "is still in the test box" in typed.text
    # What was filled in is still there.
    assert 'name="full_name" value="Sunita Testcase"' in typed.text
    assert f'value="test:{ids["fbs"]}"' in typed.text

    unticked = _form(ids, "fbs")
    del unticked["consent"]
    no_tick = post(db_client, "/frontdesk/visits", unticked)
    assert no_tick.status_code == 422
    assert 'name="consent" value="true"  aria-invalid="true"' in no_tick.text

    bad = _form(ids, "fbs", promised_at="tomorrow", pay_mode="upi", pay_amount="80")
    refused = post(db_client, "/frontdesk/visits", bad)
    assert refused.status_code == 422
    assert "Enter the promised time as a date and a time." in refused.text
    assert (
        'id="e-pay_reference"'
        in post(db_client, "/frontdesk/visits", bad | {"promised_at": ""}).text
    )
    assert seeded.scalar(select(func.count()).select_from(Visit)) == 0

    # A second person on the same phone: the screen asks before registering them.
    _saved(seeded, db_client, _form(ids, "fbs"))
    twin = _form(ids, "lipid")
    asked = post(db_client, "/frontdesk/visits", twin)
    assert asked.status_code == 422
    assert 'name="confirm_new" value="true"' in asked.text
    assert 'name="patient_id"' in asked.text
    _saved(seeded, db_client, twin | {"confirm_new": "true"})
    assert seeded.scalar(select(func.count()).select_from(Visit)) == 2


@pytest.mark.item("M18")
def test_test_line_shows_outsourced_marker(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    sign_in(db_client, "priya")

    hits = db_client.get("/frontdesk/visits/new/tests?q=vit").text
    assert "Vitamin D, 25-hydroxy" in hits and "outsourced ★" in hits
    assert "in-house" in db_client.get("/frontdesk/visits/new/tests?q=sf").text
    assert "No test or package matches" in db_client.get("/frontdesk/visits/new/tests?q=zz").text

    base = {"client_ref": str(uuid.uuid4())}
    one = post(db_client, "/frontdesk/visits/new/preview", base | {"op": "code", "q": "sf"})
    assert one.status_code == 200
    assert "Glucose, fasting" in one.text and "in-house" in one.text
    assert 'data-done="code"' in one.text
    assert f'name="item" value="test:{ids["fbs"]}"' in one.text

    order = {"item": [f"test:{ids['fbs']}"]}
    two = post(
        db_client,
        "/frontdesk/visits/new/preview",
        base | order | {"op": "add", "arg": f"test:{ids['vitd']}"},
    ).text
    assert "outsourced ★" in two and "1,380.00" in two

    missing = post(
        db_client, "/frontdesk/visits/new/preview", base | order | {"op": "code", "q": "zz"}
    ).text
    assert "No test or package matches" in missing and "data-done" not in missing

    order["item"].append(f"test:{ids['vitd']}")
    charge = {"new_charge_desc": "Home collection", "new_charge_amount": "100"}
    refused = post(
        db_client, "/frontdesk/visits/new/preview", base | order | charge | {"op": "charge"}
    ).text
    assert "data-done" not in refused and 'name="charge_desc"' not in refused
    added = post(
        db_client,
        "/frontdesk/visits/new/preview",
        base | order | charge | {"op": "charge", "new_charge_reason": "Collected at home"},
    ).text
    assert 'data-done="charge"' in added and "1,480.00" in added
    assert 'name="charge_desc" value="Home collection"' in added

    less = post(
        db_client, "/frontdesk/visits/new/preview", base | order | {"op": "remove", "arg": "0"}
    ).text
    assert "Glucose, fasting" not in less and "1,300.00" in less
    tenth = post(
        db_client,
        "/frontdesk/visits/new/preview",
        base | order | {"discount_kind": "pct", "discount_value": "10"},
    ).text
    assert "1,242.00" in tenth


@pytest.mark.item("M04")
@pytest.mark.item("M18")
def test_referrer_quick_add_and_pick(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    sign_in(db_client, "priya")
    assert "No referrers yet." in db_client.get("/frontdesk/referrers/pick").text

    nameless = post(db_client, "/frontdesk/referrers/quick", {"kind": "doctor", "name": " "})
    assert nameless.status_code == 422 and "Enter the name." in nameless.text
    new = {"kind": "doctor", "name": "Dr Asha Testcase", "phone": "9000000002"}
    added = post(db_client, "/frontdesk/referrers/quick", new)
    assert added.status_code == 200
    referrer = seeded.scalars(select(Referrer)).one()
    assert f'data-pick="{referrer.id}" data-pick-label="Dr Asha Testcase" data-pick-auto' in (
        added.text
    )
    assert 'data-done="referrer"' in added.text

    assert "Dr Asha Testcase" in db_client.get("/frontdesk/referrers/pick?q=asha").text
    assert "No referrer matches" in db_client.get("/frontdesk/referrers/pick?q=zzz").text
    assert 'data-pick=""' in db_client.get("/frontdesk/referrers/pick?q=zzz").text

    bill = _saved(seeded, db_client, _form(ids, "fbs", referrer_id=str(referrer.id)))
    assert (
        "Referred by: Dr Asha Testcase" in db_client.get(f"/frontdesk/bills/{bill.id}/print").text
    )
    assert (
        "Referred by Dr Asha Testcase" in db_client.get(f"/frontdesk/visits/{bill.visit_id}").text
    )


def _full_bill(seeded: Session, platform: Platform, client: TestClient) -> Bill:
    ids = menu(seeded, as_user(seeded, platform, "anil"))
    sign_in(client, "priya")
    form = _form(
        ids,
        "fbs",
        "lipid",
        "urine",
        "vitd",
        discount_kind="pct",
        discount_value="10",
        discount_reason="Senior citizen",
        pay_mode="upi",
        pay_amount="1000",
        pay_reference=UTR,
        footer_note="Fasting sample taken at 8 am",
        internal_note="Called twice about the due",
    )
    return _saved(seeded, client, form)


@pytest.mark.item("M07.1")
def test_bill_print_has_rule49_fields(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    bill = _full_bill(seeded, platform, db_client)
    snap = bill.print_snapshot

    page = db_client.get(f"/frontdesk/bills/{bill.id}/print").text

    assert "Bill of Supply" in page
    assert "Tax Invoice" not in page and "GST @" not in page
    supplier = snap["supplier"]
    assert f"<h1>{supplier['legal_name']}</h1>" in page
    assert supplier["address"] in page
    assert (f"GSTIN {supplier['gstin']}" if supplier["gstin"] else "GSTIN: not registered") in page
    assert f"Bill number: <strong>{bill.bill_no}</strong>" in page
    assert re.fullmatch(r"B2/\d{4}/\d{5}", bill.bill_no)
    assert f"Date: {bill.bill_date.strftime('%d %b %Y')}" in page
    assert "Patient: <strong>Sunita Testcase</strong>" in page
    assert snap["recipient"]["patient_no"] in page
    assert page.count("<td>999316</td>") == 4
    for description in ("Glucose, fasting", "Lipid profile", "Urine routine", "Vitamin D"):
        assert description in page
    assert "<strong>Net amount</strong>" in page and "1,737.00" in page
    assert "Authorised signatory" in page
    assert f"For {supplier['legal_name']}" in page


@pytest.mark.item("M07")
@pytest.mark.item("M23")
@pytest.mark.item("EC-J03")
def test_bill_print_full_content(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    bill = _full_bill(seeded, platform, db_client)
    snap = bill.print_snapshot
    payment = seeded.scalars(select(Payment).where(Payment.bill_id == bill.id)).one()
    samples = seeded.scalars(select(Sample).where(Sample.visit_id == bill.visit_id)).all()

    page = db_client.get(f"/frontdesk/bills/{bill.id}/print").text

    assert f"Visit number: {snap['visit_no']}" in page
    assert f"Place of supply: state code {bill.place_of_supply_state}" in page
    assert "Referred by: Self" in page
    assert len(samples) == 3
    for tube in samples:
        assert tube.sample_no in page
    assert "Discount: Senior citizen" in page and "-₹193.00" in page
    assert f"Amount in words: {snap['amount_in_words']}" in page
    assert "Rupees" in snap["amount_in_words"]
    assert snap["exemption_note"] and snap["exemption_note"] in page
    assert f"Receipt {payment.receipt_no}" in page
    assert f"Paid by: UPI · UTR {UTR}" in page
    assert "Amount received: ₹1,000.00" in page
    assert "<strong>Balance due</strong>" in page and "₹737.00" in page
    assert "Fasting sample taken at 8 am" in page
    assert f"Billed by: {snap['counter_user']}" in page
    assert "Called twice about the due" not in page
    assert "CANCELLED" not in page
    # A sheet for paper: the print stylesheet, a Print button, and no app menu.
    assert 'href="/static/print.css"' in page and "data-print" in page
    assert "<nav" not in page
    assert db_client.get("/static/print.css").status_code == 200

    # The staff note is for the visit screen only.
    assert "Called twice about the due" in db_client.get(f"/frontdesk/visits/{bill.visit_id}").text


@pytest.mark.item("M07")
@pytest.mark.item("EC-B07")
def test_receipt_print_fields(seeded: Session, platform: Platform, db_client: TestClient) -> None:
    bill = _full_bill(seeded, platform, db_client)
    dues = db_client.get("/frontdesk/dues").text
    assert bill.bill_no in dues and f'href="/frontdesk/bills/{bill.id}/pay"' in dues
    pay_screen = db_client.get(f"/frontdesk/bills/{bill.id}/pay").text
    assert 'name="amount" value="737.00"' in pay_screen
    ref = re.search(r'name="client_ref" value="([^"]+)"', pay_screen)
    assert ref is not None
    pay = {"client_ref": ref.group(1), "mode": "card", "amount": "737"}

    no_digits = post(db_client, f"/frontdesk/bills/{bill.id}/pay", pay)
    assert no_digits.status_code == 422 and 'id="e-reference"' in no_digits.text
    too_much = post(db_client, f"/frontdesk/bills/{bill.id}/pay", pay | {"amount": "800"})
    assert too_much.status_code == 422 and 'id="e-amount"' in too_much.text

    pay["reference"] = "4321"
    taken = post(db_client, f"/frontdesk/bills/{bill.id}/pay", pay)
    again = post(db_client, f"/frontdesk/bills/{bill.id}/pay", pay)
    assert taken.status_code == again.status_code == 303
    payments = seeded.scalars(
        select(Payment).where(Payment.bill_id == bill.id).order_by(Payment.received_at)
    ).all()
    assert len(payments) == 2
    receipt = payments[-1]
    assert taken.headers["location"] == again.headers["location"]
    assert taken.headers["location"] == f"/frontdesk/payments/{receipt.id}/print?auto=1&then=dues"

    page = db_client.get(taken.headers["location"]).text
    assert 'data-autoprint data-after-print="/frontdesk/dues"' in page
    assert f"Receipt {receipt.receipt_no}" in page
    assert f"Bill number: {bill.bill_no}" in page
    assert "Received from: Sunita Testcase" in page
    assert "Paid by: Card · card ending 4321" in page
    assert "Amount received: ₹737.00" in page
    assert f"Date: {receipt.received_at.astimezone().year}" not in page
    assert bill.print_snapshot["supplier"]["legal_name"] in page
    # Only this receipt, and no way to be sent somewhere else afterwards.
    assert UTR not in page
    elsewhere = db_client.get(f"/frontdesk/payments/{receipt.id}/print?auto=1&then=//example.test")
    assert f'data-after-print="/frontdesk/visits/{bill.visit_id}"' in elsewhere.text

    seeded.refresh(bill)
    assert (bill.status, bill.paid) == ("paid", Decimal(1737))
    assert "Nothing is due." in db_client.get("/frontdesk/dues").text
    assert "This bill is fully paid." in db_client.get(f"/frontdesk/bills/{bill.id}/pay").text


@pytest.mark.item("EC-F03")
@pytest.mark.item("M07")
def test_frontdesk_lists_paginate(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    priya = as_user(seeded, platform, "priya")
    bills = [billed(seeded, priya, lines=(("100", "0"),)) for _ in range(26)]
    sign_in(db_client, "priya")

    for url in ("/frontdesk/bills", "/frontdesk/dues"):
        first = db_client.get(url).text
        second = db_client.get(f"{url}?page=2").text
        assert "page=2" in first
        shown = [sum(b.bill_no in page for b in bills) for page in (first, second)]
        assert shown == [25, 1]

    day = bills[0].bill_date.isoformat()
    assert "status=open" in db_client.get(f"/frontdesk/bills?status=open&from={day}&to={day}").text
    assert "No bills match." in db_client.get("/frontdesk/bills?status=paid").text
    assert "No bills match." in db_client.get("/frontdesk/bills?to=2020-01-01").text


@pytest.mark.item("EC-J01")
@pytest.mark.item("M18")
def test_shortcuts_rendered_from_registry(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    bill = billed(seeded, as_user(seeded, platform, "priya"))
    sample(seeded, seeded.get_one(Visit, bill.visit_id))
    sign_in(db_client, "priya")
    pages = {
        url: db_client.get(url).text
        for url in (
            "/",
            "/frontdesk/visits/new",
            f"/frontdesk/visits/{bill.visit_id}",
            f"/frontdesk/bills/{bill.id}/pay",
            "/frontdesk/patients/new",
            "/frontdesk/referrers/new",
        )
    }

    seen: set[str] = set()
    for html in pages.values():
        keys = _SHORTCUT.findall(html)
        assert len(keys) == len(set(keys)), "one key, one element on a screen"
        assert {"alt+n", "alt+f", "alt+d"} <= set(keys)
        assert '<script src="/static/frontdesk.js" defer></script>' in html
        seen |= set(keys)
        for key in keys:
            assert f'aria-keyshortcuts="{SHORTCUTS[key].label}"' in html
    assert seen == set(SHORTCUTS)
    assert {"alt+s", "f2"} <= set(_SHORTCUT.findall(pages["/frontdesk/visits/new"]))
    assert {"alt+r", "alt+l"} <= set(_SHORTCUT.findall(pages[f"/frontdesk/visits/{bill.visit_id}"]))

    # Keys the browser or the operating system owns are never taken.
    assert not {"alt+p", "alt+h", "ctrl+n", "ctrl+p", "ctrl+w"} & set(SHORTCUTS)
    script = db_client.get("/static/frontdesk.js")
    assert script.status_code == 200 and "data-shortcut" in script.text


@pytest.mark.item("EC-J01")
def test_manual_lists_every_shortcut() -> None:
    page = (MANUAL / "getting-started" / "keyboard-shortcuts.md").read_text()
    for shortcut in SHORTCUTS.values():
        assert f"| **{shortcut.label}** | {shortcut.action} | {shortcut.where} |" in page
    assert "Alt+P" in page and "Alt+H" in page


@pytest.mark.item("EC-J02")
def test_empty_states_and_error_region(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    sign_in(db_client, "priya")
    for url, words in (
        ("/frontdesk/bills", "No bills yet."),
        ("/frontdesk/dues", "Nothing is due."),
        ("/frontdesk/visits/new", "Nothing ordered yet."),
    ):
        html = db_client.get(url).text
        assert words in html
        # Where a failed background request is reported, and never swapped into the page.
        assert '<div id="flash" class="alert-destructive" role="alert" hidden>' in html
        assert '"noSwap": [204, 304, 401, 403, 404, 409, "5xx"]' in html
    # Each background search shows that it is working.
    screen = db_client.get("/frontdesk/visits/new").text
    for busy in ("phone-busy", "code-busy", "referrer-busy"):
        assert f'hx-indicator="#{busy}"' in screen and f'id="{busy}" role="status"' in screen
    assert "style=" not in screen and "hx-on" not in screen

    bill = billed(seeded, as_user(seeded, platform, "priya"))
    summary = db_client.get(f"/frontdesk/visits/{bill.visit_id}").text
    assert "Nothing paid yet." in summary and "No samples:" in summary
    # A background request for something missing gets a short error, not a login page.
    gone = db_client.get(f"/frontdesk/visits/{uuid.uuid4()}", headers={"hx-request": "true"})
    assert gone.status_code == 404 and "text/html" in gone.headers["content-type"]


@pytest.mark.item("EC-B05")
@pytest.mark.item("M07")
def test_cancel_post_without_confirm_refused(
    seeded: Session, platform: Platform, db_client: TestClient
) -> None:
    from labra.billing.service import PaymentInput

    bill = billed(
        seeded, as_user(seeded, platform, "b3desk"), payment=PaymentInput("cash", Decimal(300))
    )
    sign_in(db_client, "b3desk")
    url = f"/frontdesk/bills/{bill.id}/cancel"
    assert f'href="{url}"' in db_client.get(f"/frontdesk/visits/{bill.visit_id}").text
    screen = db_client.get(url).text
    assert f'name="row_version" value="{bill.row_version}"' in screen
    assert 'name="refund_mode"' in screen and 'name="confirm" value="yes"' in screen
    form = {"reason": "Entered twice", "row_version": str(bill.row_version)}

    unticked = post(db_client, url, form)
    assert unticked.status_code == 422
    assert 'name="reason" value="Entered twice"' in unticked.text
    no_reason = post(db_client, url, form | {"confirm": "yes", "reason": " "})
    assert no_reason.status_code == 422 and 'id="e-reason"' in no_reason.text
    seeded.refresh(bill)
    assert bill.status == "open"
    assert seeded.scalar(select(func.count()).select_from(Refund)) == 0

    done = post(db_client, url, form | {"confirm": "yes", "refund_mode": "cash"})
    assert done.status_code == 303
    assert done.headers["location"] == f"/frontdesk/visits/{bill.visit_id}"
    seeded.refresh(bill)
    assert bill.status == "cancelled"
    refund = seeded.scalars(select(Refund)).one()
    assert refund.amount == Decimal(300)

    summary = db_client.get(done.headers["location"]).text
    assert "This visit is cancelled: Entered twice" in summary
    assert f"Refund {refund.refund_no}" in summary
    assert f'href="{url}"' not in summary and "Take payment" not in summary
    printed = db_client.get(f"/frontdesk/bills/{bill.id}/print").text
    assert "CANCELLED" in printed and "Entered twice" in printed
    assert f"Refund {refund.refund_no}" in printed
    assert "already cancelled" in db_client.get(url).text
    assert "This bill is cancelled." in db_client.get(f"/frontdesk/bills/{bill.id}/pay").text
    assert post(db_client, url, form | {"confirm": "yes"}).status_code in (409, 422)
