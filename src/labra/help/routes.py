"""The manual inside the app. Open without signing in: the sign-in screen has a help page
too, and the manual holds nothing private (it is the published documentation)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from labra import __version__
from labra.core.errors import NotFoundError
from labra.help import service
from labra.web.templating import page, render

router = APIRouter(prefix="/manual")


@router.get("/", response_class=HTMLResponse)
@page("getting-started/help", "help/index.html")
def contents(request: Request) -> Response:
    return render(request, "help/index.html", {"sections": service.sections()})


@router.get("/labra-manual.pdf")
@page("getting-started/help", "help/manual_pdf.html")
def manual_pdf() -> Response:
    return Response(
        service.manual_pdf(__version__),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="labra-manual.pdf"'},
    )


@router.get("/{name:path}/", response_class=HTMLResponse)
@page("getting-started/help", "help/page.html")
def manual_page(request: Request, name: str) -> Response:
    found = service.pages().get(name)
    if found is None:
        raise NotFoundError(f"no manual page {name!r}")
    return render(request, "help/page.html", {"page": found})
