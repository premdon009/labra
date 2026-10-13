from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from labra.auth.deps import require
from labra.auth.principal import Principal
from labra.core.db import get_session
from labra.core.errors import ValidationFailedError
from labra.results import service
from labra.web.labels import SEX_LABELS
from labra.web.templating import page, render

router = APIRouter(prefix="/lab")

DB = Annotated[Session, Depends(get_session)]
Receiver = Annotated[Principal, Depends(require("sample.receive"))]


# Receiving samples


def _receive_page(
    request: Request,
    db: Session,
    principal: Principal,
    sample_no: str = "",
    errors: dict[str, str] | None = None,
    done: str = "",
    status: int = 200,
) -> Response:
    return render(
        request,
        "lab/receive.html",
        {
            "sample_no": sample_no,
            "errors": errors or {},
            "done": service.lab_sample(db, principal, done) if done else None,
            "sexes": SEX_LABELS,
        },
        status_code=status,
    )


@router.get("/receive", response_class=HTMLResponse)
@page("lab/receiving-samples", "lab/receive.html")
def receive(request: Request, db: DB, principal: Receiver, done: str = "") -> Response:
    return _receive_page(request, db, principal, done=done)


@router.post("/receive")
def receive_save(
    request: Request, db: DB, principal: Receiver, sample_no: Annotated[str, Form()] = ""
) -> Response:
    try:
        sample = service.receive_sample(db, principal, sample_no)
    except ValidationFailedError as exc:
        db.rollback()
        return _receive_page(request, db, principal, sample_no, exc.errors, status=422)
    db.commit()
    return RedirectResponse(f"/lab/receive?done={sample.sample_no}", status_code=303)
