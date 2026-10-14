"""Uploaded SVG made safe to keep: an allowlist of drawing elements and attributes.

An SVG is markup, so a letterhead could carry a script, an event handler, embedded HTML or
links that make the renderer fetch something. The file is parsed with defusedxml (no DTD,
entities or external references), and everything not on the lists below is dropped:
`script`, `foreignObject`, `on*` attributes, any `href` that isn't `#id` or an inline PNG or
JPEG, and any CSS `url()` or `@import` that points outside the file. What was dropped is
returned so the admin screen can say so.
"""

import re
from collections import Counter
from dataclasses import dataclass
from xml.etree.ElementTree import Element, register_namespace, tostring

from defusedxml import ElementTree as SafeTree
from defusedxml.common import DefusedXmlException

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ELEMENTS = frozenset(
    {
        "svg", "g", "defs", "symbol", "use", "title", "desc", "style",
        "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
        "text", "tspan", "textPath", "image",
        "linearGradient", "radialGradient", "stop", "pattern", "clipPath", "mask",
    }
)  # fmt: skip

ATTRIBUTES = frozenset(
    {
        "id", "class", "style", "transform", "viewBox", "preserveAspectRatio", "version",
        "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "fx", "fy",
        "width", "height", "d", "points", "pathLength", "dx", "dy", "rotate",
        "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
        "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray",
        "stroke-dashoffset", "opacity", "color", "display", "visibility", "overflow",
        "clip-path", "clip-rule", "mask", "offset", "stop-color", "stop-opacity",
        "gradientUnits", "gradientTransform", "spreadMethod", "patternUnits",
        "patternContentUnits", "patternTransform", "clipPathUnits", "maskUnits",
        "maskContentUnits", "font-family", "font-size", "font-weight", "font-style",
        "font-variant", "text-anchor", "dominant-baseline", "alignment-baseline",
        "baseline-shift", "letter-spacing", "word-spacing", "text-decoration",
        "lengthAdjust", "textLength", "startOffset", "href",
    }
)  # fmt: skip

# Inline raster images only; the renderer re-reads nothing from outside the file.
_INLINE_IMAGE = re.compile(r"^data:image/(png|jpeg);base64,[A-Za-z0-9+/=\s]+$")
_LOCAL_REF = re.compile(r"^#[A-Za-z_][\w.:-]*$")
_CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
_CSS_BAD = re.compile(r"@import|expression\s*\(|javascript:|-moz-binding|behavio(u)?r\s*:", re.I)


class SvgRefusedError(ValueError):
    """The bytes are not an SVG document the sanitiser can read."""


@dataclass(frozen=True)
class CleanSvg:
    data: bytes
    removed: dict[str, int]  # what was dropped, e.g. {"script": 1, "external link": 2}


def _local(tag: str) -> tuple[str, str]:
    """(namespace, local name) of an ElementTree tag or attribute key."""
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return "", tag


def is_svg(data: bytes) -> bool:
    """Whether the bytes parse safely as XML whose root is an SVG element."""
    try:
        root = SafeTree.fromstring(data, forbid_dtd=True)
    except (SafeTree.ParseError, DefusedXmlException, ValueError):
        return False
    return _local(root.tag) == (SVG_NS, "svg")


def _safe_href(value: str) -> bool:
    value = value.strip()
    return bool(_LOCAL_REF.match(value) or _INLINE_IMAGE.match(value))


def _safe_css(css: str) -> bool:
    if _CSS_BAD.search(css):
        return False
    return all(_safe_href(m.group(2)) for m in _CSS_URL.finditer(css))


def _clean_attributes(el: Element, removed: Counter[str]) -> None:
    for key in list(el.attrib):
        ns, name = _local(key)
        value = el.attrib[key]
        if name.lower().startswith("on"):
            removed["event handler"] += 1
        elif name == "href" and ns in {"", XLINK_NS}:
            if _safe_href(value):
                continue
            removed["external link"] += 1
        elif ns == XML_NS and name == "space":
            continue
        elif ns or name not in ATTRIBUTES:
            removed["other attribute"] += 1
        elif name == "style" and not _safe_css(value):
            removed["unsafe style"] += 1
        elif "url(" in value.lower() and not _safe_css(value):
            removed["external link"] += 1
        else:
            continue
        del el.attrib[key]


def _clean(el: Element, removed: Counter[str]) -> None:
    for child in list(el):
        ns, name = _local(child.tag) if isinstance(child.tag, str) else ("", "")
        if ns != SVG_NS or name not in ELEMENTS:
            removed[name or "other element"] += 1
            el.remove(child)
            continue
        if name == "style" and not _safe_css(child.text or ""):
            removed["unsafe style"] += 1
            el.remove(child)
            continue
        _clean_attributes(child, removed)
        _clean(child, removed)


def sanitise_svg(data: bytes) -> CleanSvg:
    """The SVG with everything outside the allowlist removed, or SvgRefusedError."""
    try:
        root = SafeTree.fromstring(data, forbid_dtd=True)
    except (SafeTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise SvgRefusedError("This SVG file can't be read.") from exc
    if _local(root.tag) != (SVG_NS, "svg"):
        raise SvgRefusedError("This file is not an SVG drawing.")
    removed: Counter[str] = Counter()
    _clean_attributes(root, removed)
    _clean(root, removed)
    register_namespace("", SVG_NS)
    register_namespace("xlink", XLINK_NS)
    data = tostring(root, encoding="utf-8", xml_declaration=True)
    return CleanSvg(data=data, removed=dict(removed))
