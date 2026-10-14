"""An outside lab's PDF pages added after a report (design §7).

Only the pages are copied, never the document around them, so nothing the outside PDF
carried at document level (its scripts, open actions, attached files, forms) comes across.
Each copied page loses its links and page actions too; what is left is what it draws.
"""

import io
from collections.abc import Sequence

from pypdf import PasswordType, PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject

from labra.core.errors import ValidationFailedError
from labra.printing.pdf import Rendered

UNREADABLE = "The outside lab's PDF can't be added to the report: it can't be read."
LOCKED = (
    "The outside lab's PDF can't be added to the report: it is password-protected. Ask the"
    " lab for a copy without a password and attach it."
)
# Page keys that can run something or point elsewhere when the page is shown.
_PAGE_ACTIONS = ("/Annots", "/AA")
_DOCUMENT_ACTIONS = ("/OpenAction", "/AA", "/AcroForm")
_NAMED = ("/JavaScript", "/EmbeddedFiles")


def append_pages(rendered: Rendered, documents: Sequence[bytes]) -> Rendered:
    """The report with every page of each document after it, or ValidationFailedError."""
    if not documents:
        return rendered
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(rendered.pdf)))
    for data in documents:
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
                raise ValidationFailedError({"release": LOCKED})
            for page in reader.pages:
                # Dropped before the copy, so what they point to is never copied at all.
                for key in _PAGE_ACTIONS:
                    if key in page:
                        del page[NameObject(key)]
                writer.add_page(page)
        except (PdfReadError, ValueError, KeyError) as exc:
            raise ValidationFailedError({"release": UNREADABLE}) from exc
    root = writer.root_object
    for key in _DOCUMENT_ACTIONS:
        if key in root:
            del root[key]
    names = root.get("/Names")
    if names is not None:
        names = names.get_object()
        for key in _NAMED:
            if key in names:
                del names[NameObject(key)]
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    out = io.BytesIO()
    writer.write(out)
    return Rendered(pdf=out.getvalue(), pages=len(writer.pages), refused=rendered.refused)
