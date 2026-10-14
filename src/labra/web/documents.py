"""Server-made documents: their HTML from the same templates and filters as the screens, and
the finished PDF shown in the browser's viewer under a name Labra makes."""

import re
from typing import Any

from fastapi.responses import Response

from labra.core.uploads import PDF
from labra.web.templating import templates


def document_html(template: str, context: dict[str, Any]) -> str:
    """A template rendered outside a request, for the PDF engine."""
    return templates.env.get_template(template).render(context)


def pdf_inline(pdf: bytes, name: str) -> Response:
    """Shown in the browser's PDF viewer, which can print or save it."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "document"
    return Response(
        pdf, media_type=PDF, headers={"content-disposition": f'inline; filename="{safe}.pdf"'}
    )
