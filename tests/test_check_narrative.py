"""Narrative grounding checker — deterministic trust for the LLM digest.

The checker enforces the hard rule that the LLM digest may only contain
numbers and gene-level claims that trace back to facts.json. Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_narrative  # noqa: E402

FACTS = {
    "run_id": "k-test",
    "headline_metrics": {"DESigGenesRecall": 0.12, "pearson_delta": 0.08},
    "ceiling_headroom": {"DESigGenesRecall": 0.45, "pearson_delta": 0.31},
    "audit_flags": [
        {
            "id": "hk",
            "severity": "warn",
            "genes": ["ACTB", "GAPDH"],
            "message": "Housekeeping genes shifted up to +2.10 log2FC (threshold ±1.0); peak ACTB.",
        }
    ],
    "hypotheses_preregistered": ["h1", "h2"],
}

PAD = "word " * 60


def _names(results):
    return {name: ok for name, ok, _ in results}


def test_grounded_digest_passes() -> None:
    digest = (
        "Recall 0.12 vs ceiling 0.45; pearson_delta 0.08 vs 0.31. "
        "Housekeeping genes shifted up, with ACTB at the peak. " + PAD
    )
    results = check_narrative.run_checks(digest, FACTS)
    assert all(ok for _, ok, _ in results), results


def test_invented_number_fails() -> None:
    digest = "DESigGenesRecall jumped to 0.99, a spectacular result. " + PAD
    names = _names(check_narrative.run_checks(digest, FACTS))
    assert names["numbers_grounded"] is False


def test_facts_annotation_leak_fails() -> None:
    digest = "Recall was 0.12 (facts: headline_metrics.DESigGenesRecall). " + PAD
    names = _names(check_narrative.run_checks(digest, FACTS))
    assert names["no_facts_annotation_leak"] is False


def test_per_gene_direction_assignment_fails() -> None:
    digest = "mixed directionality: ISG15, IFIT1 up; MX1, OAS1 down among flagged genes. " + PAD
    names = _names(check_narrative.run_checks(digest, FACTS))
    assert names["gene_direction_claims"] is False


def test_pathway_level_count_summary_passes() -> None:
    digest = (
        "The pathway shows mixed directionality — 2 up and 2 down across ISG15, IFIT1, MX1, OAS1. "
        + PAD
    )
    names = _names(check_narrative.run_checks(digest, FACTS))
    assert all(ok for ok in names.values()), names


def test_case_insensitive_gene_words_not_genes() -> None:
    digest = "Changes across conditions went up before settling down. " + PAD
    results = check_narrative.run_checks(digest, FACTS)
    assert _names(results)["gene_direction_claims"] is True


def test_stub_digest_fails() -> None:
    assert _names(check_narrative.run_checks("too short", FACTS))["non_empty_digest"] is False


def test_cli_skip_without_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "k-x"
    run_dir.mkdir()
    assert check_narrative.main(["--run", str(run_dir)]) == 0
    payload = json.loads((run_dir / "verification" / "narrative_check.json").read_text())
    assert payload["status"] == "skip"


def test_cli_end_to_end(tmp_path: Path) -> None:
    run_dir = tmp_path / "k-y"
    (run_dir / "narrative").mkdir(parents=True)
    (run_dir / "facts.json").write_text(json.dumps(FACTS))
    (run_dir / "narrative" / "report.md").write_text("Recall 0.12 against the 0.45 ceiling. " + PAD)
    assert check_narrative.main(["--run", str(run_dir)]) == 0
    payload = json.loads((run_dir / "verification" / "narrative_check.json").read_text())
    assert payload["status"] == "pass"
    assert payload["cases"]
