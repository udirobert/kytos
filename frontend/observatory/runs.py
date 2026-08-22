"""Discover experiment runs with facts.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    path: Path
    facts: dict
    meta: dict  # from meta.json — carries data_status (probe/mock/final)


def _load_meta(run_dir: Path) -> dict:
    """Load meta.json alongside facts.json; tolerate its absence."""
    meta_path = run_dir / "meta.json"
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def discover_runs(experiments_dir: Path) -> list[RunSummary]:
    experiments_dir = experiments_dir.resolve()
    if not experiments_dir.is_dir():
        raise FileNotFoundError(experiments_dir)

    runs: list[RunSummary] = []
    for child in sorted(experiments_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        facts_path = child / "facts.json"
        if not facts_path.is_file():
            continue
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        meta = _load_meta(child)
        runs.append(RunSummary(run_id=child.name, path=child, facts=facts, meta=meta))
    return runs
