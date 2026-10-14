"""The public check page a report's QR code opens (design §7): anyone holding the paper can
see that the lab issued this number and version, when, and whether it is still current.
Nothing about the patient or the results is shown."""

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from labra.core.errors import NotFoundError
from labra.core.lab_settings import get_value
from labra.reports.models import Report

# `secrets.token_urlsafe(16)`: 22 characters of the URL-safe base64 alphabet.
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{22}$")


@dataclass(frozen=True)
class Check:
    lab_name: str
    report_no: str
    version: int
    released_at: datetime
    current: bool


def check(db: Session, token: str) -> Check:
    """What the check page shows for a token; not found for anything else."""
    if not _TOKEN.fullmatch(token):
        raise NotFoundError()
    report = db.scalar(select(Report).where(Report.verify_token == token))
    if report is None:
        raise NotFoundError()
    return Check(
        lab_name=get_value(db, "lab.display_name"),
        report_no=report.report_no,
        version=report.version,
        released_at=report.released_at,
        current=report.status == "released",
    )
