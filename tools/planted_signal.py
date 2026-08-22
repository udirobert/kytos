"""Planted-signal self-test for the audit layer (trust through falsification).

Every case plants a KNOWN-ANSWER perturbation through the deterministic audit
rules and requires the exact expected outcome. If the audit cannot catch what
we planted, it cannot be trusted to catch what we did not plant. Deterministic
and offline — no API calls, no network.

Cases mirror k001's own planted signals (housekeeping shift +2.10 log2FC;
mixed-directionality interferon response) plus boundary and negative controls.

Usage:
    python tools/planted_signal.py          # exit 0 = all planted signals caught
    python -m pytest tests/test_planted_signal.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from kytos.audit.rules import run_all_rules  # noqa: E402

# (name, context, expected [(rule, severity), ...] — empty list = must stay clean)
CASES: list[tuple[str, dict, list[tuple[str, str]]]] = [
    (
        "hk_clear",
        {"housekeeping_shifts": {"ACTB": 0.1, "GAPDH": -0.2}},
        [],
    ),
    (
        "hk_warn_planted_k001",
        {"housekeeping_shifts": {"ACTB": 2.10, "GAPDH": 0.2}},
        [("housekeeping_shift", "warn")],
    ),
    (
        "hk_threshold_boundary",
        {"housekeeping_shifts": {"GAPDH": 1.0}},
        [("housekeeping_shift", "warn")],
    ),
    (
        "pathway_clear_coherent",
        {
            "pathways": [
                {"name": "glycolysis", "genes": ["A", "B"], "gene_shifts": {"A": 0.9, "B": 0.7}}
            ]
        },
        [],
    ),
    (
        "pathway_mixed_planted_k001",
        {
            "pathways": [
                {
                    "name": "interferon_response",
                    "genes": ["ISG15", "IFIT1"],
                    "gene_shifts": {"ISG15": 0.9, "IFIT1": -0.7},
                }
            ]
        },
        [("pathway_coherence", "warn")],
    ),
    (
        "pathway_wrong_direction",
        {
            "pathways": [
                {
                    "name": "proteasome",
                    "genes": ["A", "B"],
                    "gene_shifts": {"A": 0.7, "B": 0.5},
                    "expected_direction": "down",
                }
            ]
        },
        [("pathway_coherence", "warn")],
    ),
]


def run_matrix() -> list[tuple[str, bool, str]]:
    """Run the planted-signal matrix; return (case, ok, detail) per case."""
    results: list[tuple[str, bool, str]] = []
    for name, context, expected in CASES:
        got = {(flag["rule"], flag["severity"]) for flag in run_all_rules(context)}
        want = set(expected)
        if got == want:
            results.append((name, True, f"expected {sorted(want) or 'clean'} — caught"))
        else:
            results.append((name, False, f"expected {sorted(want) or 'clean'}, got {sorted(got)}"))
    return results


def main(argv: list[str] | None = None) -> int:
    results = run_matrix()
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<28} {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\nplanted-signal self-test: {len(results) - failed}/{len(results)} caught")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
