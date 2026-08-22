"""Tests for biological audit rules."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kytos.audit.rules import (  # noqa: E402 - after sys.path bootstrap, matching test_smoke.py
    rule_housekeeping_shift,
    rule_pathway_coherence,
    run_all_rules,
)


def test_housekeeping_shift_flags_large_moves() -> None:
    flags = rule_housekeeping_shift({"housekeeping_shifts": {"ACTB": 2.1, "GAPDH": 0.2}})
    assert len(flags) == 1
    assert flags[0].rule == "housekeeping_shift"
    assert "ACTB" in flags[0].genes


def test_housekeeping_shift_clear_when_stable() -> None:
    flags = rule_housekeeping_shift({"housekeeping_shifts": {"ACTB": 0.1, "GAPDH": -0.2}})
    assert flags == []


def test_pathway_coherence_flags_mixed_direction() -> None:
    flags = rule_pathway_coherence(
        {
            "pathways": [
                {
                    "name": "interferon_response",
                    "genes": ["ISG15", "IFIT1"],
                    "gene_shifts": {"ISG15": 0.9, "IFIT1": -0.7},
                }
            ]
        }
    )
    assert len(flags) == 1
    assert flags[0].rule == "pathway_coherence"


def test_run_all_rules_on_k001_context() -> None:
    context_path = (
        Path(__file__).resolve().parent.parent
        / "experiments/k001-mean-shift-baseline/audit/context.json"
    )
    import json

    context = json.loads(context_path.read_text(encoding="utf-8"))
    flags = run_all_rules(context)
    rules = {item["rule"] for item in flags}
    assert "housekeeping_shift" in rules
    assert "pathway_coherence" in rules
