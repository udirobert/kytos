#!/usr/bin/env python3
"""Run Cleveland c002: CTQW on coarse graphs + classical comparison.

Surfaces Phase 1 coarse-grain gate receipts on every target — cardiac myosin
(ρ=0.823, tightest margin) is called out explicitly so compression questions
are answerable if Phase 2 looks weaker there.

Usage:

    .venv-cleveland/bin/python tools/run_cleveland_c002.py
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cleveland.io import write_run_bundle  # noqa: E402
from cleveland.pdb import fetch_pdb  # noqa: E402
from cleveland.pipeline_phase2 import (  # noqa: E402
    PHASE1_GATE_RECEIPTS,
    TIGHTEST_PHASE1_TARGET,
    run_all_phase2,
)
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
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments" / "cleveland" / "c002-ctqw-coarse",
    )
    p.add_argument("--cutoff", type=float, default=DEFAULT_GRAPH.cutoff_angstrom)
    p.add_argument("--walk-time", type=float, default=DEFAULT_GRAPH.walk_time)
    p.add_argument("--seed", type=int, default=DEFAULT_GRAPH.seed)
    p.add_argument("--hamiltonian", choices=("laplacian", "adjacency"), default="laplacian")
    p.add_argument("--targets", nargs="*", default=None)
    return p.parse_args()


def _print_banner() -> None:
    myo = PHASE1_GATE_RECEIPTS[TIGHTEST_PHASE1_TARGET]
    print(
        "Phase 1 compression receipts (c001) — tightest margin: "
        f"{TIGHTEST_PHASE1_TARGET} ρ={myo['spearman_rho']:.4f} "
        f"(margin {myo['margin_to_threshold']:.4f} above 0.8; "
        f"{myo['n_full']}→{myo['n_coarse']} nodes)"
    )


def main() -> int:
    args = parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    _print_banner()

    print("Fetching PDBs…")
    for job in PHASE1_PDB_JOBS:
        print(f"  {job.pdb_id} → {fetch_pdb(job.pdb_id, args.raw_dir)}")

    cfg = GraphConfig(
        cutoff_angstrom=args.cutoff,
        walk_time=args.walk_time,
        seed=args.seed,
    )
    print(f"Running CTQW (H={args.hamiltonian}) on coarse graphs…")
    results = run_all_phase2(
        raw_dir=args.raw_dir,
        cfg=cfg,
        target_ids=args.targets,
        hamiltonian=args.hamiltonian,
    )

    per_target: dict = {}
    gate_ok = True
    for r in results:
        tid = r["target_id"]
        per_target[tid] = r
        g = r["phase1_gate"]
        if not g["pass"]:
            gate_ok = False
        mark = " ← tightest Phase 1 margin" if g.get("tightest_phase1_margin") else ""
        rec = r["ctqw"]["known_site_recovery"]
        print(
            f"  {tid:16s} {r['pdb_id']}  coarse={r['n_coarse']:2d}  "
            f"P1ρ={g['spearman_rho']:+.4f}  "
            f"Q-vs-Cρ={r['quantum_vs_classical']['spearman_rho']:+.4f}  "
            f"known@top5={rec.get('n_known_in_top_k')}/"
            f"{rec.get('n_known_on_graph')}  "
            f"best_known_rank={rec.get('best_known_rank')}{mark}"
        )

    run_id = "c002-ctqw-coarse"
    metrics_dir = args.out / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    # Persist connectivity matrices (small; coarse only)
    conn_index = {}
    for tid, r in per_target.items():
        path = metrics_dir / f"connectivity_{tid}.npy"
        np.save(path, r["connectivity_matrix"])
        conn_index[tid] = str(path.relative_to(args.out))

    myo_receipt = PHASE1_GATE_RECEIPTS[TIGHTEST_PHASE1_TARGET]
    facts = {
        "run_id": run_id,
        "challenge": "cleveland-gqai-2026",
        "phase": 2,
        "method": "ctqw_exact_unitary_on_coarse_graph",
        "hamiltonian": args.hamiltonian,
        "backend": "exact_unitary_expm",
        "phase1_compression": {
            "source_run": "c001-ctrw-full-vs-coarse",
            "threshold": 0.8,
            "tightest_target": TIGHTEST_PHASE1_TARGET,
            "tightest_spearman_rho": myo_receipt["spearman_rho"],
            "tightest_margin_to_threshold": myo_receipt["margin_to_threshold"],
            "tightest_note": myo_receipt["note"],
            "receipts": PHASE1_GATE_RECEIPTS,
        },
        "phase1_gates_still_pass": gate_ok,
        "targets": {
            tid: {
                "pdb_id": r["pdb_id"],
                "n_full": r["n_graph_nodes"],
                "n_coarse": r["n_coarse"],
                "phase1_gate": {
                    "spearman_rho": r["phase1_gate"]["spearman_rho"],
                    "pass": r["phase1_gate"]["pass"],
                    "tightest_phase1_margin": r["phase1_gate"]["tightest_phase1_margin"],
                    "c001_receipt": r["phase1_gate"]["c001_receipt"],
                },
                "ctqw_hit_list_top5": r["ctqw"]["hit_list_top5"],
                "ctrw_hit_list_top5": r["ctrw_coarse"]["hit_list_top5"],
                "quantum_vs_classical_spearman": r["quantum_vs_classical"]["spearman_rho"],
                "known_site_recovery_ctqw": r["ctqw"]["known_site_recovery"],
                "known_site_recovery_ctrw": r["ctrw_coarse"]["known_site_recovery"],
                "known_allosteric_label": r["known_allosteric_label"],
                "connectivity_matrix_path": conn_index[tid],
                "flags": r["flags"],
            }
            for tid, r in per_target.items()
        },
    }

    metrics = {
        "phase1_compression": facts["phase1_compression"],
        "per_target": {
            tid: {
                "phase1_spearman_rho": facts["targets"][tid]["phase1_gate"]["spearman_rho"],
                "quantum_vs_classical_spearman": facts["targets"][tid][
                    "quantum_vs_classical_spearman"
                ],
                "known_site_recovery_ctqw": facts["targets"][tid]["known_site_recovery_ctqw"],
                "ctqw_hit_list_top5": facts["targets"][tid]["ctqw_hit_list_top5"],
            }
            for tid in per_target
        },
        "connectivity_matrices": conn_index,
    }

    # Human-readable note for reviewers
    report_lines = [
        "# c002 — CTQW on coarse graphs",
        "",
        "## Phase 1 compression receipts (do not drop)",
        "",
        f"**Tightest margin: `{TIGHTEST_PHASE1_TARGET}`** — Spearman "
        f"**ρ={myo_receipt['spearman_rho']:.4f}** "
        f"(only {myo_receipt['margin_to_threshold']:.4f} above the 0.8 gate; "
        f"{myo_receipt['n_full']}→{myo_receipt['n_coarse']} nodes).",
        "",
        myo_receipt["note"],
        "",
        "If Phase 2 connectivity / known-site recovery looks weaker specifically "
        "on cardiac myosin, that is the first place to ask whether compression "
        "held up — these receipts answer that question either way.",
        "",
        "## Per-target snapshot",
        "",
        "| Target | P1 ρ | Q↔C ρ | CTQW known in top-5 | Best known rank (CTQW) |",
        "|---|---|---|---|---|",
    ]
    for tid, r in per_target.items():
        rec = r["ctqw"]["known_site_recovery"]
        star = " **← tightest P1**" if tid == TIGHTEST_PHASE1_TARGET else ""
        report_lines.append(
            f"| {tid}{star} | {r['phase1_gate']['spearman_rho']:.4f} | "
            f"{r['quantum_vs_classical']['spearman_rho']:.4f} | "
            f"{rec.get('n_known_in_top_k')}/{rec.get('n_known_on_graph')} | "
            f"{rec.get('best_known_rank')} |"
        )
    report_lines.extend(
        [
            "",
            f"Hamiltonian: `{args.hamiltonian}`. Backend: exact `expm(-iHt)` "
            "(simulator; Braket/Classiq packaging is a follow-on).",
            "",
        ]
    )

    write_run_bundle(
        args.out,
        run_id=run_id,
        config={
            **asdict(cfg),
            "hamiltonian": args.hamiltonian,
            "targets": args.targets or list(TARGETS),
        },
        facts=facts,
        meta={
            "task": "phase2_ctqw_coarse",
            "challenge": "cleveland-gqai-2026",
            "notes": (
                "CTQW on Phase 1 coarse graphs; classical CTRW comparator; "
                "myosin Phase 1 ρ=0.823 kept visible as tightest compression margin."
            ),
            "seed": cfg.seed,
        },
        metrics=metrics,
        flags=[f for r in results for f in r["flags"]],
        repo_root=ROOT,
    )
    narrative = args.out / "narrative"
    narrative.mkdir(exist_ok=True)
    (narrative / "report.md").write_text("\n".join(report_lines) + "\n")
    # Drop large arrays from any accidental re-serialization
    print(f"Wrote {args.out}")
    print(f"Reviewer note: {args.out / 'narrative' / 'report.md'}")
    return 0 if gate_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
