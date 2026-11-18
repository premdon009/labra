"""Jinja for server-made documents: the same template folder as the screens, but its own
environment, so a document never sees request globals and fails loudly on a missing value.
Sandboxed (EC-A08), as the screens' environment is."""

from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader, StrictUndefined, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

_env = SandboxedEnvironment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(default=True, default_for_string=True),
    undefined=StrictUndefined,
)


def render_html(template: str, **context: Any) -> str:
    return _env.get_template(template).render(**context)
