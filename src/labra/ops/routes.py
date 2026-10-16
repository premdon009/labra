from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from labra import __version__
from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core.config import get_settings
from labra.core.db import get_session
from labra.core.health import DISK_ALERT_PERCENT
from labra.core.ids import utcnow
from labra.ops import service
from labra.web.templating import page, render

router = APIRouter(prefix="/admin")

DB = Annotated[Session, Depends(get_session)]


@router.get("/system", response_class=HTMLResponse)
@page("admin/system", "ops/system.html")
def system(
    request: Request, db: DB, principal: Annotated[Principal, Depends(require("setting.view"))]
) -> Response:
    settings = get_settings()
    now = utcnow()
    return render(
        request,
        "ops/system.html",
        {
            "version": __version__,
            "jobs": service.job_statuses(db, now),
            "disk": service.disk_status(settings.files_dir),
            "disk_alert": DISK_ALERT_PERCENT,
            "db_bytes": service.database_bytes(db),
            "migrations": service.migration_status(db),
            "cert": service.cert_status(settings.cert_check_host, settings.cert_check_name, now),
            "cert_warn_days": service.CERT_WARN.days,
        },
    )
