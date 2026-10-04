#!/usr/bin/env python3
"""Assemble ``facts.json`` for a submission-receipt run dir.

The Observatory's run pages read ``facts.json`` (see ``kytos.eval.facts``
for the cell-eval pipeline variant). Submission-era run dirs instead ship
``leaderboard_result.json`` + ``meta.json`` — this tool normalizes the
three leaderboard schemas seen so far into the same facts.json shape so
``discover_runs`` picks the dir up.

Schemas handled (all observed under experiments/):

- ``score_avg`` + ``score_pds``/``score_nmae``/... (k015, k018)
- ``overall_score`` + ``rank`` + ``rank_of``          (k026, k027 — no
  public components; use ``--components-from`` when a byte-identical
  rescore supplies them, e.g. k037 supplies k027's)
- ``overall`` + ``pds``/``nmae``/``fid``/``reach``/``jac``/``mse``
  (k030, k034, k035, k037, k038)

Narrative fields (headline, hypotheses, next steps, provenance text) are
authored, not derived — pass them via flags so the artifact stays a
curated declaration like the other runs' facts.json. Only public
(leaderboard or qualitative) facts belong in them.

Usage::

    python3 tools/facts_from_receipt.py --run experiments/kNNN-... \
        --headline "..." --hypothesis "..." --next-step "..." \
        --vessel-fill 99 --strategy "..." --code tools/x.py --data "..."
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

OVERALL_KEYS = ("overall", "overall_score", "score_avg")
COMPONENT_KEYS = ("pds", "nmae", "fid", "reach", "jac", "mse")
# Same key order the cell-eval-era facts.json files use.
METRIC_ORDER = ("overall", "pds", "mse", "nmae", "fid", "reach", "jac")


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _pick(payload: dict, names: tuple[str, ...], *, prefix: str = "") -> float | None:
    for name in names:
        v = _num(payload.get(f"{prefix}{name}"))
        if v is not None:
            return v
    return None


def metrics_from_receipt(lb: dict[str, Any]) -> dict[str, float | None]:
    """Normalize a leaderboard_result.json into headline_metrics."""
    metrics: dict[str, float | None] = {
        "overall": _pick(lb, OVERALL_KEYS),
    }
    for key in COMPONENT_KEYS:
        metrics[key] = _pick(lb, (key,)) or _pick(lb, (key,), prefix="score_")
    return {k: metrics[k] for k in METRIC_ORDER}


def receipt_date(lb: dict[str, Any]) -> str:
    for key in (
        "submitted",
        "submitted_at",
        "submitted_at_utc",
        "submitted_utc",
        "submission_date",
        "published_utc",
    ):
        value = lb.get(key)
        if isinstance(value, str) and value[:10].count("-") == 2:
            return value[:10]
    return ""


def build_facts(
    run_dir: Path,
    *,
    headline: str,
    hypotheses: list[str],
    next_steps: list[str],
    vessel_fill: int | None,
    created: str | None,
    data_status: str,
    components_from: Path | None,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    lb_path = run_dir / "leaderboard_result.json"
    lb = json.loads(lb_path.read_text(encoding="utf-8"))
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}

    metrics = metrics_from_receipt(lb)
    if metrics["overall"] is None:
        raise ValueError(f"{lb_path}: no overall score found (tried {OVERALL_KEYS})")

    if components_from is not None:
        donor_path = components_from / "leaderboard_result.json"
        donor = metrics_from_receipt(json.loads(donor_path.read_text(encoding="utf-8")))
        for key in COMPONENT_KEYS:
            metrics[key] = donor[key]

    facts: dict[str, Any] = {
        "run_id": run_dir.name,
        "created": created or receipt_date(lb) or str(meta.get("created_at", ""))[:10],
        "headline": headline,
        "data_status": data_status,
        "headline_metrics": metrics,
        "ceiling_headroom": {},
        "audit_flags": [],
        "hypotheses_preregistered": hypotheses,
        "next_steps": next_steps,
        "provenance": {k: v for k, v in provenance.items() if v},
    }
    if vessel_fill is not None:
        facts["vessel_fill"] = vessel_fill
    return facts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--run", type=Path, required=True, help="run dir containing leaderboard_result.json"
    )
    p.add_argument("--headline", default="", help="one-line public result summary")
    p.add_argument("--hypothesis", action="append", default=[], dest="hypotheses")
    p.add_argument("--next-step", action="append", default=[], dest="next_steps")
    p.add_argument("--vessel-fill", type=int, default=None)
    p.add_argument("--created", default=None, help="YYYY-MM-DD; defaults to receipt submit date")
    p.add_argument("--data-status", default="final")
    p.add_argument(
        "--components-from",
        type=Path,
        default=None,
        help="run dir whose receipt supplies this run's per-component scores (same artifact)",
    )
    p.add_argument("--strategy", default=None, help="provenance.strategy")
    p.add_argument("--code", default=None, help="provenance.code (e.g. tools/run_kNNN_*.py)")
    p.add_argument("--data", default=None, help="provenance.data (source corpora)")
    p.add_argument("--commit", default=None, help="provenance.commit")
    p.add_argument("--dry-run", action="store_true", help="print the facts.json instead of writing")
    args = p.parse_args(argv)

    run_dir = args.run.resolve()
    facts = build_facts(
        run_dir,
        headline=args.headline,
        hypotheses=args.hypotheses,
        next_steps=args.next_steps,
        vessel_fill=args.vessel_fill,
        created=args.created,
        data_status=args.data_status,
        components_from=args.components_from.resolve() if args.components_from else None,
        provenance={
            "commit": args.commit,
            "strategy": args.strategy,
            "code": args.code,
            "data": args.data,
        },
    )
    if args.dry_run:
        print(json.dumps(facts, indent=2))
        return 0
    out = run_dir / "facts.json"
    out.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
