"""An outside lab's PDF added after a report: its pages come across, nothing it could run
does."""

import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from labra.core.errors import ValidationFailedError
from labra.printing.attach import LOCKED, UNREADABLE, append_pages
from labra.printing.pdf import render_pdf

SCRIPT = "app.beep()"


def scripted_pdf(text: str) -> bytes:
    """A one-page PDF saying `text` that also carries what a viewer could run or open: a
    script on opening, a named script, an attached file, a page action and a link."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(render_pdf(f"<p>{text}</p>").pdf)))
    script = DictionaryObject(
        {
            NameObject("/S"): NameObject("/JavaScript"),
            NameObject("/JS"): TextStringObject(SCRIPT),
        }
    )
    ref = writer._add_object(script)
    root = writer.root_object
    root[NameObject("/OpenAction")] = ref
    root[NameObject("/Names")] = DictionaryObject(
        {
            NameObject("/JavaScript"): DictionaryObject(
                {NameObject("/Names"): ArrayObject([TextStringObject("synthetic"), ref])}
            )
        }
    )
    writer.add_attachment("synthetic.txt", b"synthetic")
    page = writer.pages[0]
    link = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): ArrayObject([]),
            NameObject("/A"): ref,
        }
    )
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(link)])
    page[NameObject("/AA")] = DictionaryObject({NameObject("/O"): ref})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def runnable(pdf: bytes) -> list[str]:
    """What in the PDF a viewer could run or open."""
    reader = PdfReader(io.BytesIO(pdf))
    root = reader.root_object
    found = [key for key in ("/OpenAction", "/AA", "/AcroForm") if key in root]
    names = root.get("/Names")
    if names is not None:
        found += [key for key in ("/JavaScript", "/EmbeddedFiles") if key in names.get_object()]
    for page in reader.pages:
        found += [key for key in ("/Annots", "/AA") if key in page]
    if b"/JavaScript" in pdf:
        found.append("script object")
    return found


@pytest.mark.item("M12")
def test_an_outside_pdf_keeps_its_pages_and_loses_what_it_could_run() -> None:
    outside = scripted_pdf("Synthetic outside value 32.5")
    assert len(runnable(outside)) == 6
    report = render_pdf("<p>Synthetic report body</p>")

    joined = append_pages(report, [outside, outside])

    reader = PdfReader(io.BytesIO(joined.pdf))
    assert joined.pages == len(reader.pages) == 3
    texts = [page.extract_text() or "" for page in reader.pages]
    assert "Synthetic report body" in texts[0]
    assert all("Synthetic outside value 32.5" in t for t in texts[1:])
    assert runnable(joined.pdf) == []


@pytest.mark.item("M12")
def test_nothing_to_add_leaves_the_report_as_it_was() -> None:
    report = render_pdf("<p>Synthetic report body</p>")
    assert append_pages(report, []) is report


@pytest.mark.item("M12")
def test_a_locked_or_broken_outside_pdf_is_refused() -> None:
    plain = render_pdf("<p>Synthetic outside value</p>").pdf
    locked = PdfWriter(clone_from=PdfReader(io.BytesIO(plain)))
    locked.encrypt("synthetic")
    restricted = PdfWriter(clone_from=PdfReader(io.BytesIO(plain)))
    restricted.encrypt("", owner_password="synthetic")
    out_locked, out_restricted = io.BytesIO(), io.BytesIO()
    locked.write(out_locked)
    restricted.write(out_restricted)
    report = render_pdf("<p>Synthetic report body</p>")

    for data, message in ((out_locked.getvalue(), LOCKED), (b"%PDF-1.7\n%%EOF", UNREADABLE)):
        with pytest.raises(ValidationFailedError) as refused:
            append_pages(report, [data])
        assert refused.value.errors == {"release": message}

    # Only an owner password, which any viewer opens without asking: added as usual.
    joined = append_pages(report, [out_restricted.getvalue()])
    assert joined.pages == 2
