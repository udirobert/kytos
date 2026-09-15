#!/usr/bin/env python3
"""c005 — CTQW config sweep (H-form × T × full/coarse) + null z on winners."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cleveland.io import write_run_bundle  # noqa: E402
from cleveland.pdb import fetch_pdb  # noqa: E402
from cleveland.pipeline_c005 import run_all_sweeps  # noqa: E402
from cleveland.pipeline_phase2 import (  # noqa: E402
    PHASE1_GATE_RECEIPTS,
    TIGHTEST_PHASE1_TARGET,
)
from cleveland.targets import DEFAULT_GRAPH, PHASE1_PDB_JOBS, GraphConfig  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=ROOT / "data/cleveland/raw")
    p.add_argument("--out", type=Path, default=ROOT / "experiments/cleveland/c005-signal-sweep")
    p.add_argument("--n-null", type=int, default=24)
    p.add_argument("--n-times", type=int, default=32)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--cutoff", type=float, default=DEFAULT_GRAPH.cutoff_angstrom)
    p.add_argument("--targets", nargs="*", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    myo = PHASE1_GATE_RECEIPTS[TIGHTEST_PHASE1_TARGET]
    print(f"c005 sweep — myosin P1 margin ρ={myo['spearman_rho']:.4f} kept visible")
    for job in PHASE1_PDB_JOBS:
        fetch_pdb(job.pdb_id, args.raw_dir)

    cfg = GraphConfig(cutoff_angstrom=args.cutoff, seed=args.seed)
    results = run_all_sweeps(
        raw_dir=args.raw_dir,
        cfg=cfg,
        target_ids=args.targets,
        n_times=args.n_times,
        n_null=args.n_null,
        seed=args.seed,
    )

    lines = [
        "# c005 — signal sweep (H × T × resolution) + null on winners",
        "",
        f"Myosin Phase 1 compression margin: ρ=**{myo['spearman_rho']:.4f}** "
        f"(tightest P1 gate; still surfaced).",
        "",
        "| Target | Winner (res / H / T) | Best known | Mean known | z | Sig? |",
        "|---|---|---|---|---|---|",
    ]
    per = {}
    any_sig = False
    for r in results:
        per[r["target_id"]] = r
        w = r["winner"]
        star = " **← tightest P1**" if r["tightest_phase1_margin"] else ""
        cfg_s = f"{w['resolution']} / {w['hamiltonian']} / T={w['walk_time']}"
        print(
            f"  {r['target_id']:16s} {cfg_s}  best={w['best_known_rank']}  "
            f"mean={w['mean_known_rank']}  z={r['zscore_mean_known_rank']}  "
            f"sig={r['significant_better_than_null']}"
            + (" ← myosin" if r["tightest_phase1_margin"] else "")
        )
        if r["significant_better_than_null"]:
            any_sig = True
        lines.append(
            f"| {r['target_id']}{star} | `{cfg_s}` | {w['best_known_rank']} | "
            f"{w['mean_known_rank']} | {r['zscore_mean_known_rank']} | "
            f"{r['significant_better_than_null']} |"
        )

    run_id = "c005-signal-sweep"
    facts = {
        "run_id": run_id,
        "challenge": "cleveland-gqai-2026",
        "phase": "3b_signal_sweep",
        "method": "ctqw_grid_search_plus_rewire_null",
        "any_significant": any_sig,
        "phase1_compression": {
            "tightest_target": TIGHTEST_PHASE1_TARGET,
            "tightest_spearman_rho": myo["spearman_rho"],
            "tightest_margin_to_threshold": myo["margin_to_threshold"],
            "receipts": PHASE1_GATE_RECEIPTS,
        },
        "targets": per,
    }
    write_run_bundle(
        args.out,
        run_id=run_id,
        config={**asdict(cfg), "n_null": args.n_null, "n_times": args.n_times},
        facts=facts,
        meta={
            "task": "signal_sweep",
            "challenge": "cleveland-gqai-2026",
            "notes": "Grid H×T×resolution; myosin P1 ρ=0.823 visible.",
            "seed": args.seed,
        },
        metrics={
            "per_target": {
                t: {"winner": r["winner"], "z": r["zscore_mean_known_rank"]} for t, r in per.items()
            }
        },
        flags=[
            {
                "id": "phase1_tightest_compression_margin",
                "severity": "info",
                "detail": f"cardiac_myosin P1 ρ={myo['spearman_rho']:.4f}",
            }
        ],
        repo_root=ROOT,
    )
    narr = args.out / "narrative"
    narr.mkdir(exist_ok=True)
    (narr / "report.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote {args.out}  any_significant={any_sig}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
