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
        text = path.read_text(encoding="utf-8")
        # Strip generator provenance comment — not for display
        if text.lstrip().startswith("<!--"):
            text = re.sub(r"^\s*<!--.*?-->\s*", "", text, count=1, flags=re.DOTALL)
        return text
    return None


def load_literature(run_dir: Path) -> list[dict[str, Any]]:
    lit_dir = run_dir / "literature"
    if not lit_dir.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(lit_dir.glob("*.json")):
        # Skip .entities.json files — loaded separately
        if path.stem.endswith(".entities"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payload.setdefault("flag_id", path.stem)
            items.append(payload)
    return items


PIONEER_BASE_MODEL = "fastino/gliner2-base-v1"


def load_entity_extractions(run_dir: Path) -> list[dict[str, Any]]:
    """Load Pioneer GLiNER2 entity extraction results from literature/*.entities.json."""
    lit_dir = run_dir / "literature"
    if not lit_dir.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(lit_dir.glob("*.entities.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payload.setdefault("source_gene", path.stem.replace(".entities", ""))
            items.append(payload)
    return items


def entity_model_label(item: dict[str, Any]) -> str:
    """Human-readable label for how entities were extracted."""
    method = str(item.get("method") or "")
    model_id = str(item.get("model_id") or "")
    if method == "fallback" or model_id == "fallback":
        return "regex fallback"
    if model_id == PIONEER_BASE_MODEL:
        return "base GLiNER2"
    if method == "pioneer" and model_id and model_id not in ("fallback", PIONEER_BASE_MODEL):
        return "fine-tuned LoRA"
    return method or "unknown"


def summarize_entity_extractions(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate NER stats for the run-detail panel header and hero strip."""
    if not items:
        return {
            "total_entities": 0,
            "gene_count": 0,
            "model_label": None,
            "model_id": None,
            "method": None,
            "label_totals": {},
            "is_fine_tuned": False,
        }

    total_entities = sum(int(item.get("entity_count") or 0) for item in items)
    model_ids = {str(item.get("model_id")) for item in items if item.get("model_id")}
    methods = {str(item.get("method")) for item in items if item.get("method")}
    label_totals: dict[str, int] = {}
    for item in items:
        for label, texts in (item.get("by_label") or {}).items():
            label_totals[str(label)] = label_totals.get(str(label), 0) + len(texts)

    primary_model_id = next(iter(model_ids)) if len(model_ids) == 1 else None
    primary_method = "pioneer" if "pioneer" in methods else next(iter(methods), None)
    probe = {"method": primary_method, "model_id": primary_model_id}
    model_label = entity_model_label(probe) if primary_model_id else None
    is_fine_tuned = model_label == "fine-tuned LoRA"

    return {
        "total_entities": total_entities,
        "gene_count": len(items),
        "model_label": model_label,
        "model_id": primary_model_id,
        "method": primary_method,
        "label_totals": label_totals,
        "is_fine_tuned": is_fine_tuned,
    }


def load_holo_audit(run_dir: Path) -> dict[str, Any] | None:
    """Load the Holo independent-verification result (holo_audit.json)."""
    path = run_dir / "holo_audit.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def load_planted_signal(run_dir: Path) -> dict[str, Any] | None:
    """Load the planted-signal self-test result (verification/planted_signal.json)."""
    path = run_dir / "verification" / "planted_signal.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def load_narrative_check(run_dir: Path) -> dict[str, Any] | None:
    """Load the narrative grounding check (verification/narrative_check.json)."""
    path = run_dir / "verification" / "narrative_check.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def load_newsroom_research(run_dir: Path) -> list[dict[str, Any]]:
    """Load the newsroom field research (newsroom/research.json) — top results."""
    path = run_dir / "newsroom" / "research.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    results = payload.get("results") if isinstance(payload, dict) else None
    return results if isinstance(results, list) else []


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
