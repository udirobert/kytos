#!/usr/bin/env python3
"""c004 — Phase 3 randomization z-score for CTQW known-site ranks."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cleveland.io import write_run_bundle  # noqa: E402
from cleveland.pdb import fetch_pdb  # noqa: E402
from cleveland.pipeline_c004 import run_all_randomization  # noqa: E402
from cleveland.pipeline_phase2 import (  # noqa: E402
    PHASE1_GATE_RECEIPTS,
    TIGHTEST_PHASE1_TARGET,
)
from cleveland.targets import DEFAULT_GRAPH, PHASE1_PDB_JOBS, GraphConfig, TARGETS  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=ROOT / "data/cleveland/raw")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments/cleveland/c004-randomization",
    )
    p.add_argument("--n-null", type=int, default=50, help="null rewires per target")
    p.add_argument("--n-times", type=int, default=32)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--cutoff", type=float, default=DEFAULT_GRAPH.cutoff_angstrom)
    p.add_argument("--walk-time", type=float, default=DEFAULT_GRAPH.walk_time)
    p.add_argument("--hamiltonian", choices=("laplacian", "adjacency"), default="laplacian")
    p.add_argument("--targets", nargs="*", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    myo = PHASE1_GATE_RECEIPTS[TIGHTEST_PHASE1_TARGET]
    print(f"Phase 3 randomization — myosin P1 margin ρ={myo['spearman_rho']:.4f} kept visible")
    for job in PHASE1_PDB_JOBS:
        fetch_pdb(job.pdb_id, args.raw_dir)

    cfg = GraphConfig(cutoff_angstrom=args.cutoff, walk_time=args.walk_time, seed=args.seed)
    # Default: skip exploratory myc (no known site)
    target_ids = args.targets or [t for t in TARGETS if TARGETS[t].known_allosteric_residues]
    print(f"Null rewires per target: {args.n_null} (full-graph CTQW)…")
    results = run_all_randomization(
        raw_dir=args.raw_dir,
        cfg=cfg,
        target_ids=target_ids,
        hamiltonian=args.hamiltonian,
        n_null=args.n_null,
        n_times=args.n_times,
        seed=args.seed,
    )

    lines = [
        "# c004 — Phase 3 randomization (edge-rewire null)",
        "",
        f"Myosin Phase 1 compression margin: ρ=**{myo['spearman_rho']:.4f}** "
        f"(still the tightest P1 gate).",
        "",
        "| Target | Obs mean known rank | Null mean±std | z | empir. p | Sig (z<-2)? |",
        "|---|---|---|---|---|---|",
    ]
    per = {}
    for r in results:
        per[r["target_id"]] = r
        star = " **← tightest P1**" if r["tightest_phase1_margin"] else ""
        print(
            f"  {r['target_id']:16s} obs={r['observed_mean_known_rank']}  "
            f"z={r['zscore_mean_known_rank']}  p={r['empirical_p_lower_rank']}  "
            f"sig={r['significant_better_than_null']}"
            + (" ← myosin" if r["tightest_phase1_margin"] else "")
        )
        null_s = (
            f"{r['null_mean']:.1f}±{r['null_std']:.1f}"
            if r["null_mean"] is not None and r["null_std"] is not None
            else "—"
        )
        lines.append(
            f"| {r['target_id']}{star} | {r['observed_mean_known_rank']} | {null_s} | "
            f"{r['zscore_mean_known_rank']} | {r['empirical_p_lower_rank']} | "
            f"{r['significant_better_than_null']} |"
        )

    run_id = "c004-randomization"
    facts = {
        "run_id": run_id,
        "challenge": "cleveland-gqai-2026",
        "phase": 3,
        "method": "ctqw_edge_rewire_null_zscore",
        "phase1_compression": {
            "tightest_target": TIGHTEST_PHASE1_TARGET,
            "tightest_spearman_rho": myo["spearman_rho"],
            "tightest_margin_to_threshold": myo["margin_to_threshold"],
            "receipts": PHASE1_GATE_RECEIPTS,
        },
        "n_null": args.n_null,
        "targets": {tid: r for tid, r in per.items()},
    }
    write_run_bundle(
        args.out,
        run_id=run_id,
        config={
            **asdict(cfg),
            "hamiltonian": args.hamiltonian,
            "n_null": args.n_null,
            "n_times": args.n_times,
        },
        facts=facts,
        meta={
            "task": "phase3_randomization",
            "challenge": "cleveland-gqai-2026",
            "notes": "Edge-rewire null on full-graph CTQW; myosin P1 ρ=0.823 visible.",
            "seed": args.seed,
        },
        metrics={"per_target": facts["targets"]},
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
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
