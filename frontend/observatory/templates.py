"""Jinja2 template rendering engine for Kytos Observatory."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import jinja2

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_template(template_name: str, **context: Any) -> str:
    """Render a template by name with context dictionary."""
    template = _env.get_template(template_name)
    return template.render(**context)
