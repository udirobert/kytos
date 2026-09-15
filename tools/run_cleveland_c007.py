#!/usr/bin/env python3
"""c007 — cutoff × multi-scale × community-source × residual CTQW vs null."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cleveland.io import write_run_bundle  # noqa: E402
from cleveland.pdb import fetch_pdb  # noqa: E402
from cleveland.pipeline_c007 import run_all_c007  # noqa: E402
from cleveland.pipeline_phase2 import (  # noqa: E402
    PHASE1_GATE_RECEIPTS,
    TIGHTEST_PHASE1_TARGET,
)
from cleveland.targets import PHASE1_PDB_JOBS, GraphConfig  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=ROOT / "data/cleveland/raw")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments/cleveland/c007-topology-levers",
    )
    p.add_argument("--n-null", type=int, default=30)
    p.add_argument("--n-times", type=int, default=24)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--targets", nargs="*", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    myo = PHASE1_GATE_RECEIPTS[TIGHTEST_PHASE1_TARGET]
    print(f"c007 topology levers — myosin P1 ρ={myo['spearman_rho']:.4f} kept visible")
    for job in PHASE1_PDB_JOBS:
        fetch_pdb(job.pdb_id, args.raw_dir)

    cfg = GraphConfig(seed=args.seed)
    results = run_all_c007(
        raw_dir=args.raw_dir,
        base_cfg=cfg,
        target_ids=args.targets,
        n_times=args.n_times,
        n_null=args.n_null,
        seed=args.seed,
    )

    lines = [
        "# c007 — topology levers vs edge-rewire null",
        "",
        f"Myosin Phase 1 compression margin: ρ=**{myo['spearman_rho']:.4f}** "
        f"(tightest P1; still surfaced).",
        "",
        "Levers: cutoff ∈ {8,9,10}, sources ∈ {active, +neighbors}, "
        "H ∈ {laplacian, adjacency}, score ∈ {T=10, multiscale, CTQW−CTRW}, "
        "resolution ∈ {coarse, full≤350}.",
        "",
        "| Target | Winner | Best | z_best | z_mean | Sig? |",
        "|---|---|---|---|---|---|",
    ]
    per = {}
    any_sig = False
    for r in results:
        per[r["target_id"]] = r
        w = r["winner"]
        star = " **← tightest P1**" if r["tightest_phase1_margin"] else ""
        cfg_s = (
            f"cut={w['cutoff']} {w['resolution']}/{w['hamiltonian']}/"
            f"{w['score_mode']}/{w['source_mode']}"
            f"{'+distal' if w.get('distal_upweight') else ''}"
        )
        print(
            f"  {r['target_id']:16s} {cfg_s}  best={w['best_known_rank']}  "
            f"z_best={r['zscore_best_known_rank']}  z_mean={r['zscore_mean_known_rank']}  "
            f"sig={r['significant_better_than_null']}"
            + (" ← myosin" if r["tightest_phase1_margin"] else "")
        )
        if r["significant_better_than_null"]:
            any_sig = True
        lines.append(
            f"| {r['target_id']}{star} | `{cfg_s}` | {w['best_known_rank']} | "
            f"{r['zscore_best_known_rank']} | {r['zscore_mean_known_rank']} | "
            f"{r['significant_better_than_null']} |"
        )

    lines.extend(
        [
            "",
            f"**Any significant (z&lt;-2)?** `{any_sig}`",
            "",
        ]
    )

    run_id = "c007-topology-levers"
    facts = {
        "run_id": run_id,
        "challenge": "cleveland-gqai-2026",
        "phase": "3c_topology_levers",
        "method": "cutoff_multiscale_community_residual_sweep",
        "any_significant": any_sig,
        "phase1_compression": {
            "tightest_target": TIGHTEST_PHASE1_TARGET,
            "tightest_spearman_rho": myo["spearman_rho"],
            "tightest_margin_to_threshold": myo["margin_to_threshold"],
            "receipts": PHASE1_GATE_RECEIPTS,
        },
        "targets": per,
    }
    # Drop top_trials recovery bulk from facts if huge — keep top_trials as-is
    write_run_bundle(
        args.out,
        run_id=run_id,
        config={**asdict(cfg), "n_null": args.n_null, "n_times": args.n_times},
        facts=facts,
        meta={
            "task": "topology_lever_sweep",
            "challenge": "cleveland-gqai-2026",
            "notes": ("Cutoff/multiscale/community/residual CTQW; myosin P1 ρ=0.823 visible."),
            "seed": args.seed,
        },
        metrics={
            "any_significant": any_sig,
            "per_target": {
                t: {
                    "winner": r["winner"],
                    "z": r["zscore_mean_known_rank"],
                    "sig": r["significant_better_than_null"],
                }
                for t, r in per.items()
            },
        },
        flags=[
            {
                "id": "phase1_tightest_compression_margin",
                "severity": "info",
                "detail": f"cardiac_myosin P1 ρ={myo['spearman_rho']:.4f}",
            },
            {
                "id": "null_significance",
                "severity": "info" if any_sig else "warn",
                "detail": f"any_significant_z_lt_minus2={any_sig}",
            },
        ],
        repo_root=ROOT,
    )
    narr = args.out / "narrative"
    narr.mkdir(exist_ok=True)
    (narr / "report.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote {args.out}  any_significant={any_sig}")
    return 0 if True else 1


if __name__ == "__main__":
    raise SystemExit(main())
