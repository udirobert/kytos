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
        runs.append(RunSummary(run_id=child.name, path=child, facts=facts))
    return runs
