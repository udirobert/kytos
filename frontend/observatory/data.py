"""Load run artifacts for static rendering."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


def load_metrics(metrics_dir: Path) -> tuple[list[str], list[float], list[float]]:
    agg_path = metrics_dir / "agg_results.csv"
    ceil_path = metrics_dir / "ceiling_results.csv"
    if not agg_path.is_file() or not ceil_path.is_file():
        return [], [], []

    agg = _metric_map(agg_path, "value")
    ceil = _metric_map(ceil_path, "ceiling")
    names = sorted(set(agg) | set(ceil))
    scores = [agg.get(name, 0.0) for name in names]
    ceilings = [ceil.get(name, 0.0) for name in names]
    return names, scores, ceilings


def _metric_map(path: Path, value_col: str) -> dict[str, float]:
    out: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return out
        key = reader.fieldnames[0]
        for row in reader:
            name = row[key].strip()
            if name:
                out[name] = float(row[value_col])
    return out


def load_narrative(run_dir: Path) -> str | None:
    path = run_dir / "narrative" / "report.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return None


def load_literature(run_dir: Path) -> list[dict[str, Any]]:
    lit_dir = run_dir / "literature"
    if not lit_dir.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(lit_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payload.setdefault("flag_id", path.stem)
            items.append(payload)
    return items


def markdown_to_html(text: str) -> str:
    """Minimal markdown → HTML (headings, paragraphs, links, bold)."""
    lines = text.strip().splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        body = " ".join(paragraph).strip()
        if body:
            blocks.append(f"<p>{_inline(body)}</p>")
        paragraph.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            blocks.append(f"<h3>{_inline(stripped[3:])}</h3>")
        elif stripped.startswith("# "):
            flush_paragraph()
            blocks.append(f"<h2>{_inline(stripped[2:])}</h2>")
        else:
            paragraph.append(stripped)
    flush_paragraph()
    return "\n".join(blocks)


def _inline(text: str) -> str:
    text = _escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" rel="noopener">\1</a>',
        text,
    )
    return text


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
