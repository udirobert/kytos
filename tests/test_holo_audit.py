"""Tests for Holo independent render-verification audit.

Must pass with NO HAI_API_KEY and NO Playwright — the tool degrades gracefully
and exits 0 (famile lesson: enrichment degrades, never blocks).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

sys.path.insert(0, str(TOOLS))

import holo_audit  # noqa: E402


SAMPLE_FACTS = {
    "run_id": "k001-mean-shift-baseline",
    "headline": "Mean-shift baseline with planted audit signals",
    "ceiling_headroom": {"mse": 0.42, "mae": 0.38, "DESigGenesRecall": 0.15},
    "audit_flags": [
        {"rule": "housekeeping_shift", "severity": "warn"},
        {"rule": "pathway_coherence", "severity": "warn"},
        {"rule": "info_flag", "severity": "info"},
    ],
}


def test_expected_from_facts_extracts_fill() -> None:
    """Fill % is the mean of ceiling_headroom values, clamped 6–100."""
    result = holo_audit._expected_from_facts(SAMPLE_FACTS)
    # mean(0.42, 0.38, 0.15) = 0.3167 → 32%
    assert result["fill_pct"] == 32


def test_expected_from_facts_counts_flags() -> None:
    """Warn count = warn+error flags; info count = info flags."""
    result = holo_audit._expected_from_facts(SAMPLE_FACTS)
    assert result["warn_count"] == 2
    assert result["info_count"] == 1


def test_expected_from_facts_empty_ceiling() -> None:
    """No ceiling values → fill clamped to minimum 6%."""
    facts = {"run_id": "test", "ceiling_headroom": {}, "audit_flags": []}
    result = holo_audit._expected_from_facts(facts)
    assert result["fill_pct"] == 6


def test_diff_detects_mismatch() -> None:
    expected = {"fill_pct": 32, "warn_count": 2, "info_count": 1, "run_id": "k001"}
    observed = {"fill_pct": 50, "warn_count": 2, "info_count": 1, "run_id": "k001"}
    mismatches = holo_audit._diff(expected, observed)
    assert len(mismatches) == 1
    assert mismatches[0][0] == "fill_pct"


def test_diff_passes_on_match() -> None:
    expected = {"fill_pct": 32, "warn_count": 2, "info_count": 1, "run_id": "k001"}
    observed = {"fill_pct": 32, "warn_count": 2, "info_count": 1, "run_id": "k001"}
    assert holo_audit._diff(expected, observed) == []


def test_diff_ignores_none_observed() -> None:
    """If Holo couldn't read a value (null), it's not a mismatch."""
    expected = {"fill_pct": 32, "warn_count": 2, "info_count": 1, "run_id": "k001"}
    observed = {"fill_pct": None, "warn_count": 2, "info_count": None, "run_id": "k001"}
    assert holo_audit._diff(expected, observed) == []


def test_diff_run_id_loose_match() -> None:
    """run_id match is loose — Holo may include extra text."""
    expected = {
        "fill_pct": 32,
        "warn_count": 2,
        "info_count": 1,
        "run_id": "k001-mean-shift-baseline",
    }
    observed = {
        "fill_pct": 32,
        "warn_count": 2,
        "info_count": 1,
        "run_id": "k001-mean-shift-baseline run page",
    }
    assert holo_audit._diff(expected, observed) == []


def test_holo_client_returns_none_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """No HAI_API_KEY → returns None (degrade, not error)."""
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    monkeypatch.delenv("hai_api_key", raising=False)
    assert holo_audit._holo_client() is None


def test_run_audit_skips_without_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Full audit degrades to 'skipped' when no key and no Playwright."""
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    monkeypatch.delenv("hai_api_key", raising=False)

    facts = SAMPLE_FACTS.copy()
    (tmp_path / "facts.json").write_text(json.dumps(facts))

    report = holo_audit.run_audit(tmp_path)
    assert report["status"] == "skipped"


def test_main_exits_zero_on_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI exits 0 when audit is skipped (degrade, never block)."""
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    monkeypatch.delenv("hai_api_key", raising=False)

    facts = SAMPLE_FACTS.copy()
    (tmp_path / "facts.json").write_text(json.dumps(facts))

    exit_code = holo_audit.main(["--run", str(tmp_path)])
    assert exit_code == 0
    assert (tmp_path / "holo_audit.json").exists()
