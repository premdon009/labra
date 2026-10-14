"""The daily accounting export (`labra export accounting`): one day's figures for the
accountant, as CSV for a spreadsheet or JSON for software.

The figures come from the owner's daily screen (`labra.owner.service.daily`), so the file
and the screen always agree: money taken at each branch by mode less refunds, bills issued,
cancellations, what was owed at the end of the day, and outsourcing cost against revenue.
"""

import csv
import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.auth.principal import Principal
from labra.billing.models import PAYMENT_MODES
from labra.core import audit
from labra.core.errors import NotFoundError
from labra.core.money import money
from labra.exports.common import private_dir, private_file
from labra.org.models import Branch
from labra.owner import service as owner

FORMATS = ("csv", "json")
# One row per branch, then a total row when there is more than one branch.
COLUMNS = (
    "date",
    "branch_code",
    "branch",
    *PAYMENT_MODES,
    "refunds",
    "collected_net",
    "bills",
    "gross",
    "discount",
    "billed_net",
    "cancelled_bills",
    "cancelled_net",
    "dues_bills",
    "dues",
    "outsourced_tests",
    "outsourcing_cost",
    "outsourcing_revenue",
    "outsourcing_margin",
)


def _amount(value: Any) -> str:
    return str(money(value))


def _block(code: str, name: str, d: owner.Daily) -> dict[str, Any]:
    return {
        "branch_code": code,
        "branch": name,
        "collection": {
            **{m: _amount(d.total.modes[m]) for m in PAYMENT_MODES},
            "refunds": _amount(d.total.refunds),
            "net": _amount(d.total.net),
        },
        "bills": {
            "count": d.bills,
            "gross": _amount(d.gross),
            "discount": _amount(d.discount),
            "net": _amount(d.net),
        },
        "cancelled": {"count": d.cancelled, "net": _amount(d.cancelled_net)},
        "dues": {"bills": d.dues_bills, "amount": _amount(d.dues)},
        "outsourcing": {
            "tests": d.outsourced.tests,
            "cost": _amount(d.outsourced.cost),
            "revenue": _amount(d.outsourced.revenue),
            "margin": _amount(d.outsourced.margin),
        },
    }


def figures(
    db: Session, principal: Principal, day: date, branch_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """The day's figures for each branch counted and for all of them together."""
    whole = owner.daily(db, principal, day, branch_id)
    counted = [b for b in whole.branches if branch_id is None or b.id == branch_id]
    codes = dict(
        db.execute(
            select(Branch.id, Branch.code).where(Branch.id.in_([b.id for b in counted]))
        ).all()
    )
    return {
        "schema_version": 1,
        "date": day.isoformat(),
        "branches": [
            _block(codes[b.id], b.name, owner.daily(db, principal, day, b.id)) for b in counted
        ],
        "total": _block("", "All branches", whole),
    }


def _row(day: str, block: dict[str, Any]) -> list[object]:
    c, b, x, d, o = (
        block["collection"],
        block["bills"],
        block["cancelled"],
        block["dues"],
        block["outsourcing"],
    )
    return [
        day,
        block["branch_code"],
        block["branch"],
        *(c[m] for m in PAYMENT_MODES),
        c["refunds"],
        c["net"],
        b["count"],
        b["gross"],
        b["discount"],
        b["net"],
        x["count"],
        x["net"],
        d["bills"],
        d["amount"],
        o["tests"],
        o["cost"],
        o["revenue"],
        o["margin"],
    ]


def branch_by_code(db: Session, code: str) -> uuid.UUID:
    found = db.scalar(select(Branch.id).where(Branch.code == code.strip().upper()))
    if found is None:
        raise NotFoundError(f"There is no branch {code.strip().upper()}.")
    return found


def export(
    db: Session,
    principal: Principal,
    day: date,
    root: Path,
    fmt: str = "csv",
    branch_id: uuid.UUID | None = None,
) -> Path:
    """Write the day's figures to `root/accounting/` and audit it. Running it again for the
    same day and branches replaces the file with the figures as they are now."""
    if fmt not in FORMATS:
        raise ValueError(fmt)
    data = figures(db, principal, day, branch_id)
    which = data["branches"][0]["branch_code"] if branch_id is not None else "ALL"
    path = private_dir(root / "accounting") / f"accounting-{data['date']}-{which}.{fmt}"
    if fmt == "json":
        with private_file(path) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
    else:
        # A byte order mark so a spreadsheet opens the ₹ sign and Indian names correctly.
        with private_file(path, newline="", encoding="utf-8-sig") as f:
            out = csv.writer(f)
            out.writerow(COLUMNS)
            out.writerows(_row(data["date"], block) for block in data["branches"])
            if len(data["branches"]) > 1:
                out.writerow(_row(data["date"], data["total"]))
    audit.record(
        db,
        "export.accounting",
        "export",
        None,
        {
            "date": data["date"],
            "branch_id": str(branch_id) if branch_id else None,
            "format": fmt,
            "file": path.name,
        },
        user_id=principal.user_id,
    )
    return path
