"""Assemble ``facts.json`` from committed run artifacts (metrics + audit flags)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from kytos.eval.metrics_io import load_agg_metrics, load_ceiling_metrics
from kytos.eval.provenance import provenance_from_run

# cell-eval renamed the DE recall metric between the 2025-era mock schema and
# the 0.8.2 release (k002, first real run). Accept both spellings and keep the
# key the committed CSV actually uses.
HEADLINE_METRICS: tuple[tuple[str, ...], ...] = (
    ("de_sig_genes_recall", "DESigGenesRecall"),
    ("pearson_delta",),
)


def _headline_subset(
    metrics: dict[str, float | None], keys: tuple[tuple[str, ...], ...]
) -> dict[str, float | None]:
    missing: list[str] = []
    out: dict[str, float | None] = {}
    for aliases in keys:
        key = next((a for a in aliases if a in metrics), None)
        if key is None:
            missing.append("/".join(aliases))
            continue
        out[key] = metrics[key]
    if missing:
        raise KeyError(f"missing headline metrics in agg_results.csv: {missing}")
    return out


def _visual_paths(run_dir: Path) -> dict[str, str]:
    visual: dict[str, str] = {}
    mapping = {
        "hero": "visual/hero.png",
        "share_card": "visual/share-card.png",
        # The Observatory cast: Dr. Kytos (presenter) is the anchor, the
        # vessel is the instrument, the bulletin is the 8s hero clip, and the
        # full briefing stays the watch-on-demand artifact (committed only
        # when small enough for git+Netlify — see the 4MB cap in tools/).
        "presenter": "visual/presenter.mp4",
        "bulletin": "visual/bulletin.mp4",
        "briefing": "visual/briefing.mp4",
    }
    for key, rel in mapping.items():
        if (run_dir / rel).is_file():
            visual[key] = rel
    return visual


def load_audit_flags(run_dir: Path) -> list[dict[str, Any]]:
    flags_path = run_dir / "audit" / "flags.json"
    if not flags_path.is_file():
        raise FileNotFoundError(
            f"{flags_path} missing — run `python -m kytos.audit --run {run_dir}` first"
        )
    payload = json.loads(flags_path.read_text(encoding="utf-8"))
    flags = payload.get("flags")
    if not isinstance(flags, list):
        raise ValueError(f"{flags_path}: expected object with 'flags' list")
    return flags


def assemble_facts(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    meta_path = run_dir / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(meta_path)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    metrics_dir = run_dir / "metrics"
    agg = load_agg_metrics(metrics_dir)
    ceiling = load_ceiling_metrics(metrics_dir)

    headline = _headline_subset(agg, HEADLINE_METRICS)
    ceiling_headline = _headline_subset(ceiling, HEADLINE_METRICS)

    facts: dict[str, Any] = {
        "run_id": meta.get("run_id", run_dir.name),
        "created": meta.get("created", ""),
        "headline": meta.get("headline", ""),
        "data_status": meta.get("data_status", "real"),
        "headline_metrics": headline,
        "ceiling_headroom": ceiling_headline,
        "audit_flags": load_audit_flags(run_dir),
        "hypotheses_preregistered": list(meta.get("hypotheses_preregistered") or []),
        "provenance": provenance_from_run(run_dir, meta),
    }

    visual = _visual_paths(run_dir)
    if visual:
        facts["visual"] = visual

    return facts


def write_facts(run_dir: Path, facts: dict[str, Any] | None = None) -> Path:
    run_dir = run_dir.resolve()
    if facts is None:
        facts = assemble_facts(run_dir)
    out_path = run_dir / "facts.json"
    out_path.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble facts.json for an experiment run.")
    parser.add_argument(
        "--run",
        type=Path,
        required=True,
        help="Experiment run directory (e.g. experiments/k001-mean-shift-baseline)",
    )
    args = parser.parse_args(argv)
    out = write_facts(args.run)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
