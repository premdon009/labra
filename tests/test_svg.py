"""The SVG sanitiser keeps drawings and drops anything that runs, embeds or fetches."""

import pytest
from defusedxml import ElementTree as SafeTree
from hypothesis import given
from hypothesis import strategies as st

from labra.core.svg import SVG_NS, XLINK_NS, SvgRefusedError, sanitise_svg

HEAD = f"<svg xmlns='{SVG_NS}' xmlns:xlink='{XLINK_NS}' viewBox='0 0 100 40'"
PNG_URI = "data:image/png;base64,iVBORw0KGgo="


def _clean(body: str, attrs: str = "") -> tuple[str, dict[str, int]]:
    result = sanitise_svg(f"{HEAD} {attrs}>{body}</svg>".encode())
    return result.data.decode(), result.removed


@pytest.mark.item("EC-A07")
def test_a_plain_drawing_keeps_its_shapes_text_and_gradients() -> None:
    body = (
        "<defs><linearGradient id='g'><stop offset='0' stop-color='#123'/></linearGradient></defs>"
        "<rect width='100' height='40' fill='url(#g)'/>"
        "<text x='4' y='20' font-family='serif'>Sample Diagnostics</text>"
        f"<image width='10' height='10' href='{PNG_URI}'/><use href='#g'/>"
    )
    out, removed = _clean(body)
    assert removed == {}
    for kept in ("linearGradient", "url(#g)", "Sample Diagnostics", PNG_URI, 'href="#g"'):
        assert kept in out


@pytest.mark.item("EC-A07")
@pytest.mark.parametrize(
    ("body", "attrs", "gone", "reason"),
    [
        ("<script>alert(1)</script>", "", "alert", "script"),
        ("<foreignObject><p>hi</p></foreignObject>", "", "<p", "foreignObject"),
        ("<rect width='1' onclick='alert(1)'/>", "", "onclick", "event handler"),
        ("", "onload='alert(1)'", "onload", "event handler"),
        ("<a href='javascript:alert(1)'><text>x</text></a>", "", "javascript", "a"),
        ("<use xlink:href='https://example.invalid/x.svg#a'/>", "", "invalid", "external link"),
        ("<image href='file:///etc/passwd'/>", "", "passwd", "external link"),
        ("<image href='data:image/svg+xml;base64,PHN2Zz4='/>", "", "svg+xml", "external link"),
        ("<rect fill='url(https://example.invalid/p)'/>", "", "invalid", "external link"),
        ("<rect style='fill:url(http://example.invalid/p)'/>", "", "invalid", "unsafe style"),
        ("<style>@import url(http://x.invalid/a.css);</style>", "", "@import", "unsafe style"),
        ("<animate attributeName='href' to='javascript:x'/>", "", "animate", "animate"),
        ("<set attributeName='onclick' to='x'/>", "", "<set", "set"),
        ("<iframe src='https://example.invalid'/>", "", "iframe", "iframe"),
        ("<rect width='1' formaction='x'/>", "", "formaction", "other attribute"),
    ],
)
def test_anything_that_runs_or_fetches_is_dropped(
    body: str, attrs: str, gone: str, reason: str
) -> None:
    out, removed = _clean(body, attrs)
    assert gone not in out
    assert removed.get(reason, 0) >= 1


@pytest.mark.item("EC-A07")
@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not xml",
        b"<html><body/></html>",
        b"<svg><rect/></svg>",
        b"<?xml version='1.0'?><!DOCTYPE svg SYSTEM 'http://example.invalid/x.dtd'>"
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        b"<?xml version='1.0'?><!DOCTYPE svg [<!ENTITY x SYSTEM 'file:///etc/passwd'>]>"
        b"<svg xmlns='http://www.w3.org/2000/svg'><text>&x;</text></svg>",
    ],
)
def test_what_is_not_a_safe_svg_document_is_refused(data: bytes) -> None:
    with pytest.raises(SvgRefusedError):
        sanitise_svg(data)


@pytest.mark.item("EC-A07")
@given(st.lists(st.sampled_from(["script", "foreignObject", "iframe", "rect", "g", "text"])))
def test_the_cleaned_file_only_ever_holds_allowed_elements(tags: list[str]) -> None:
    body = "".join(f"<{t} onload='x'><{t}/></{t}>" for t in tags)
    cleaned = sanitise_svg(f"{HEAD}>{body}</svg>".encode()).data
    root = SafeTree.fromstring(cleaned, forbid_dtd=True)
    for el in root.iter():
        assert el.tag.split("}")[1] in {"svg", "rect", "g", "text"}
        assert not any(key.lower().startswith("on") for key in el.attrib)
