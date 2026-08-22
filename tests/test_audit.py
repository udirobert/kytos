"""Tests for biological audit rules."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kytos.audit.rules import (  # noqa: E402 - after sys.path bootstrap, matching test_smoke.py
    rule_control_group_stability,
    rule_dose_response,
    rule_gene_group_coherence,
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


# ── control_group_stability ──────────────────────────────────────────────────


def test_control_group_stability_flags_large_shift() -> None:
    flags = rule_control_group_stability(
        {"control_group": {"gene_shifts": {"ACTB": 0.8, "GAPDH": 0.3}}}
    )
    assert len(flags) == 1
    assert flags[0].rule == "control_group_stability"
    assert flags[0].severity == "error"
    assert "ACTB" in flags[0].genes


def test_control_group_stability_clear_when_stable() -> None:
    flags = rule_control_group_stability(
        {"control_group": {"gene_shifts": {"ACTB": 0.1, "GAPDH": -0.2}}}
    )
    assert flags == []


def test_control_group_stability_uses_custom_threshold() -> None:
    flags = rule_control_group_stability(
        {"control_group": {"gene_shifts": {"ACTB": 0.35}, "max_shift_threshold": 0.3}}
    )
    assert len(flags) == 1


# ── dose_response ─────────────────────────────────────────────────────────────


def test_dose_response_flags_strong_knockdown_weak_shift() -> None:
    flags = rule_dose_response(
        {"dose_response": [{"gene": "MYC", "knockdown_pct": 85.0, "target_shift": 0.1}]}
    )
    assert len(flags) == 1
    assert flags[0].rule == "dose_response"
    assert "MYC" in flags[0].genes


def test_dose_response_flags_weak_knockdown_large_shift() -> None:
    flags = rule_dose_response(
        {"dose_response": [{"gene": "CDK4", "knockdown_pct": 15.0, "target_shift": 2.5}]}
    )
    assert len(flags) == 1
    assert "CDK4" in flags[0].genes


def test_dose_response_clear_when_proportionate() -> None:
    flags = rule_dose_response(
        {"dose_response": [{"gene": "BRCA1", "knockdown_pct": 80.0, "target_shift": 1.5}]}
    )
    assert flags == []


def test_dose_response_clear_at_boundary() -> None:
    """69% knockdown is below the strong threshold (70); should not flag."""
    flags = rule_dose_response(
        {"dose_response": [{"gene": "X", "knockdown_pct": 69.0, "target_shift": 0.0}]}
    )
    assert flags == []


# ── gene_group_coherence ──────────────────────────────────────────────────────


def test_gene_group_coherence_flags_incoherent_group() -> None:
    """Four genes in a group, two strongly oppose the mean."""
    flags = rule_gene_group_coherence(
        {
            "gene_groups": [
                {
                    "name": "ribosomal",
                    "genes": ["RPL5", "RPL11", "RPS20", "RPL10"],
                    "gene_shifts": {"RPL5": 1.2, "RPL11": 1.0, "RPS20": -0.8, "RPL10": -0.9},
                }
            ]
        }
    )
    assert len(flags) == 1
    assert flags[0].rule == "gene_group_coherence"
    assert "RPS20" in flags[0].genes
    assert "RPL10" in flags[0].genes


def test_gene_group_coherence_clear_when_coherent() -> None:
    flags = rule_gene_group_coherence(
        {
            "gene_groups": [
                {
                    "name": "proteasome",
                    "genes": ["PSMA1", "PSMA2", "PSMA3"],
                    "gene_shifts": {"PSMA1": 0.8, "PSMA2": 0.7, "PSMA3": 0.6},
                }
            ]
        }
    )
    assert flags == []


def test_gene_group_coherence_skips_small_groups() -> None:
    """Groups with <3 genes are too small to assess coherence."""
    flags = rule_gene_group_coherence(
        {
            "gene_groups": [
                {
                    "name": "duo",
                    "genes": ["A", "B"],
                    "gene_shifts": {"A": 2.0, "B": -2.0},
                }
            ]
        }
    )
    assert flags == []
