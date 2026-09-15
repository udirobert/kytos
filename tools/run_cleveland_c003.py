#!/usr/bin/env python3
"""c003 — full vs coarse CTQW compression audit (myosin margin first)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cleveland.io import write_run_bundle  # noqa: E402
from cleveland.pdb import fetch_pdb  # noqa: E402
from cleveland.pipeline_c003 import run_all_compression_audits  # noqa: E402
from cleveland.pipeline_phase2 import (  # noqa: E402
    PHASE1_GATE_RECEIPTS,
    TIGHTEST_PHASE1_TARGET,
)
from cleveland.targets import (  # noqa: E402
    DEFAULT_GRAPH,
    PHASE1_PDB_JOBS,
    GraphConfig,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=ROOT / "data/cleveland/raw")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments/cleveland/c003-ctqw-compression-audit",
    )
    p.add_argument("--cutoff", type=float, default=DEFAULT_GRAPH.cutoff_angstrom)
    p.add_argument("--walk-time", type=float, default=DEFAULT_GRAPH.walk_time)
    p.add_argument("--seed", type=int, default=DEFAULT_GRAPH.seed)
    p.add_argument("--n-times", type=int, default=48)
    p.add_argument("--hamiltonian", choices=("laplacian", "adjacency"), default="laplacian")
    p.add_argument("--targets", nargs="*", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    myo = PHASE1_GATE_RECEIPTS[TIGHTEST_PHASE1_TARGET]
    print(
        f"Compression audit — Phase 1 tightest margin: {TIGHTEST_PHASE1_TARGET} "
        f"ρ={myo['spearman_rho']:.4f} (margin {myo['margin_to_threshold']:.4f})"
    )
    for job in PHASE1_PDB_JOBS:
        fetch_pdb(job.pdb_id, args.raw_dir)

    cfg = GraphConfig(cutoff_angstrom=args.cutoff, walk_time=args.walk_time, seed=args.seed)
    results = run_all_compression_audits(
        raw_dir=args.raw_dir,
        cfg=cfg,
        target_ids=args.targets,
        hamiltonian=args.hamiltonian,
        n_times=args.n_times,
    )

    lines = [
        "# c003 — CTQW full vs coarse compression audit",
        "",
        f"**Phase 1 tightest margin:** `{TIGHTEST_PHASE1_TARGET}` ρ="
        f"**{myo['spearman_rho']:.4f}** (margin {myo['margin_to_threshold']:.4f}; "
        f"{myo['n_full']}→{myo['n_coarse']}).",
        "",
        "Question: does coarse-graining destroy CTQW known-site recovery?",
        "",
        "| Target | P1 ρ | Full↔coarse ρ | Full best | Coarse best | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    per = {}
    for r in results:
        per[r["target_id"]] = r
        star = " **← tightest P1**" if r["tightest_phase1_margin"] else ""
        fr = r["recovery_full"].get("best_known_rank")
        cr = r["recovery_coarse"].get("best_known_rank")
        print(
            f"  {r['target_id']:16s} full↔coarseρ="
            f"{r['ctqw_full_vs_coarse_spearman']['spearman_rho']:+.4f}  "
            f"full_best={fr} coarse_best={cr}  {r['compression_verdict']}"
            + (" ← myosin" if r["tightest_phase1_margin"] else "")
        )
        lines.append(
            f"| {r['target_id']}{star} | "
            f"{r['phase1_receipt'].get('spearman_rho', '')} | "
            f"{r['ctqw_full_vs_coarse_spearman']['spearman_rho']:.4f} | "
            f"{fr} | {cr} | `{r['compression_verdict']}` |"
        )

    myo_r = per.get(TIGHTEST_PHASE1_TARGET)
    myosin_note = ""
    if myo_r:
        myosin_note = (
            f"Myosin verdict: **{myo_r['compression_verdict']}** "
            f"(full best known rank={myo_r['recovery_full'].get('best_known_rank')}, "
            f"coarse={myo_r['recovery_coarse'].get('best_known_rank')})."
        )
        lines.extend(["", myosin_note, ""])

    run_id = "c003-ctqw-compression-audit"
    facts = {
        "run_id": run_id,
        "challenge": "cleveland-gqai-2026",
        "phase": "2b_compression_audit",
        "method": "ctqw_full_vs_coarse",
        "phase1_compression": {
            "tightest_target": TIGHTEST_PHASE1_TARGET,
            "tightest_spearman_rho": myo["spearman_rho"],
            "tightest_margin_to_threshold": myo["margin_to_threshold"],
            "receipts": PHASE1_GATE_RECEIPTS,
        },
        "myosin_compression_verdict": (myo_r["compression_verdict"] if myo_r else None),
        "targets": {
            tid: {
                "pdb_id": r["pdb_id"],
                "n_full": r["n_full"],
                "n_coarse": r["n_coarse"],
                "phase1_receipt": r["phase1_receipt"],
                "tightest_phase1_margin": r["tightest_phase1_margin"],
                "ctqw_full_vs_coarse_spearman": r["ctqw_full_vs_coarse_spearman"],
                "recovery_full": r["recovery_full"],
                "recovery_coarse": r["recovery_coarse"],
                "hit_list_full_top5": r["hit_list_full_top5"],
                "hit_list_coarse_top5": r["hit_list_coarse_top5"],
                "compression_verdict": r["compression_verdict"],
                "known_allosteric_label": r["known_allosteric_label"],
            }
            for tid, r in per.items()
        },
    }
    write_run_bundle(
        args.out,
        run_id=run_id,
        config={**asdict(cfg), "hamiltonian": args.hamiltonian, "n_times": args.n_times},
        facts=facts,
        meta={
            "task": "phase2b_compression_audit",
            "challenge": "cleveland-gqai-2026",
            "notes": (
                "Full vs coarse CTQW; myosin P1 ρ=0.823 kept visible. "
                "Mavacamten pocket labels updated to literature contacts."
            ),
            "seed": cfg.seed,
        },
        metrics={"per_target": facts["targets"], "phase1_compression": facts["phase1_compression"]},
        flags=[
            {
                "id": "phase1_tightest_compression_margin",
                "severity": "info",
                "detail": (
                    f"cardiac_myosin P1 ρ={myo['spearman_rho']:.4f}; "
                    f"c003 verdict={facts['myosin_compression_verdict']}"
                ),
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
