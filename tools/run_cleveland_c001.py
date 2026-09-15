#!/usr/bin/env python3
"""Run Cleveland c001: classical CTRW full vs coarse-grain Spearman gate.

Usage (from repo root, with `.venv-cleveland`):

    .venv-cleveland/bin/python tools/run_cleveland_c001.py
    .venv-cleveland/bin/python tools/run_cleveland_c001.py --fetch-only
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cleveland.io import write_run_bundle  # noqa: E402
from cleveland.pdb import fetch_pdb  # noqa: E402
from cleveland.pipeline import run_all_apo  # noqa: E402
from cleveland.targets import (  # noqa: E402
    DEFAULT_GRAPH,
    PHASE1_PDB_JOBS,
    GraphConfig,
    TARGETS,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT / "data" / "cleveland" / "raw",
        help="PDB download directory",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments" / "cleveland" / "c001-ctrw-full-vs-coarse",
        help="experiment run directory",
    )
    p.add_argument("--fetch-only", action="store_true", help="download PDBs and exit")
    p.add_argument("--cutoff", type=float, default=DEFAULT_GRAPH.cutoff_angstrom)
    p.add_argument("--walk-time", type=float, default=DEFAULT_GRAPH.walk_time)
    p.add_argument("--seed", type=int, default=DEFAULT_GRAPH.seed)
    p.add_argument(
        "--targets",
        nargs="*",
        default=None,
        help=f"subset of {list(TARGETS)}",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching PDBs…")
    for job in PHASE1_PDB_JOBS:
        path = fetch_pdb(job.pdb_id, args.raw_dir)
        print(f"  {job.pdb_id} → {path}")

    if args.fetch_only:
        return 0

    cfg = GraphConfig(
        cutoff_angstrom=args.cutoff,
        walk_time=args.walk_time,
        seed=args.seed,
    )
    print("Running CTRW + coarse-grain gate…")
    results = run_all_apo(raw_dir=args.raw_dir, cfg=cfg, target_ids=args.targets)

    per_target = {}
    all_pass = True
    for r in results:
        per_target[r["target_id"]] = r
        status = "PASS" if r["gate"]["pass"] else "FAIL"
        if not r["gate"]["pass"]:
            all_pass = False
        print(
            f"  {r['target_id']:16s} {r['pdb_id']}  "
            f"n={r['n_graph_nodes']:4d}→{r['n_coarse']:2d}  "
            f"ρ={r['gate']['spearman_rho']:+.4f}  [{status}]"
        )

    run_id = "c001-ctrw-full-vs-coarse"
    config = {**asdict(cfg), "targets": args.targets or list(TARGETS)}
    metrics = {
        "per_target": {
            tid: {
                "spearman_rho": r["gate"]["spearman_rho"],
                "pass": r["gate"]["pass"],
                "n_full": r["n_graph_nodes"],
                "n_coarse": r["n_coarse"],
                "hit_list_top5": r["hit_list_top5"],
            }
            for tid, r in per_target.items()
        },
        "all_pass": all_pass,
        "threshold": cfg.spearman_threshold,
    }
    facts = {
        "run_id": run_id,
        "challenge": "cleveland-gqai-2026",
        "phase": 1,
        "method": "classical_ctrw_full_vs_coarse",
        "gate": "spearman_rank_correlation",
        "all_pass": all_pass,
        "targets": {
            tid: {
                "pdb_id": r["pdb_id"],
                "spearman_rho": r["gate"]["spearman_rho"],
                "pass": r["gate"]["pass"],
                "n_full": r["n_graph_nodes"],
                "n_coarse": r["n_coarse"],
                "hit_list_top5": r["hit_list_top5"],
                "flags": r["flags"],
            }
            for tid, r in per_target.items()
        },
    }
    meta = {
        "task": "phase1_ctrw_coarsegrain_gate",
        "challenge": "cleveland-gqai-2026",
        "notes": "Classical CTRW baseline + spectral coarse-grain Spearman gate (≥0.8).",
        "seed": cfg.seed,
    }
    flags = [f for r in results for f in r["flags"]]

    write_run_bundle(
        args.out,
        run_id=run_id,
        config=config,
        facts=facts,
        meta=meta,
        metrics=metrics,
        flags=flags,
        repo_root=ROOT,
    )
    print(f"Wrote {args.out}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
