"""Tests for facts.json assembly."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kytos.audit.__main__ import audit_run  # noqa: E402 - after sys.path bootstrap
from kytos.eval.facts import assemble_facts, write_facts  # noqa: E402
from kytos.eval.metrics_io import load_agg_metrics, load_ceiling_metrics  # noqa: E402

K001 = Path(__file__).resolve().parent.parent / "experiments/k001-mean-shift-baseline"


def test_load_k001_metrics() -> None:
    agg = load_agg_metrics(K001 / "metrics")
    ceiling = load_ceiling_metrics(K001 / "metrics")
    assert agg["DESigGenesRecall"] == 0.12
    assert ceiling["pearson_delta"] == 0.31


def test_assemble_facts_matches_csvs() -> None:
    audit_run(K001)
    facts = assemble_facts(K001)
    assert facts["run_id"] == "k001-mean-shift-baseline"
    assert facts["headline_metrics"]["DESigGenesRecall"] == 0.12
    assert facts["ceiling_headroom"]["pearson_delta"] == 0.31
    assert len(facts["audit_flags"]) >= 2
    assert facts["hypotheses_preregistered"]


def test_write_facts_roundtrip() -> None:
    audit_run(K001)
    out = write_facts(K001)
    assert out.name == "facts.json"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["headline_metrics"]["pearson_delta"] == 0.08
