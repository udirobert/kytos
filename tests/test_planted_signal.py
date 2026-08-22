"""Planted-signal proof: the audit layer must catch what we plant.

Trust through falsification (NOTES §4 matcha-hack): if the deterministic audit
rules cannot catch known-answer perturbations, they cannot be trusted to catch
unknown ones. These tests pin the matrix in `tools/planted_signal.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "tools"))
import planted_signal  # noqa: E402


def test_all_planted_signals_caught() -> None:
    results = planted_signal.run_matrix()
    failures = [(name, detail) for name, ok, detail in results if not ok]
    assert not failures, f"audit missed planted signals: {failures}"


def test_matrix_has_positive_and_negative_controls() -> None:
    names = {name for name, _, _ in planted_signal.CASES}
    assert "hk_clear" in names
    assert "pathway_clear_coherent" in names
    assert "hk_warn_planted_k001" in names
    assert "pathway_mixed_planted_k001" in names
