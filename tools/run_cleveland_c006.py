#!/usr/bin/env python3
"""c006 — Qiskit CTQW packaging on coarse graphs (+ Braket/Classiq exports).

Verifies HamiltonianGate statevector matches exact eigh metric; writes circuit
packages for challenge hardware. Does not require live Braket credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cleveland.circuit import (  # noqa: E402
    braket_export_payload,
    classiq_export_payload,
    package_graph_ctqw,
)
from cleveland.graph import (  # noqa: E402
    adjacency_matrix,
    build_contact_graph,
    coarse_grain,
)
from cleveland.io import write_run_bundle  # noqa: E402
from cleveland.pdb import coords_matrix, fetch_pdb, load_residue_nodes  # noqa: E402
from cleveland.pipeline import _source_graph_nodes  # noqa: E402
from cleveland.pipeline_phase2 import (  # noqa: E402
    PHASE1_GATE_RECEIPTS,
    TIGHTEST_PHASE1_TARGET,
)
from cleveland.targets import PHASE1_PDB_JOBS, TARGETS, GraphConfig  # noqa: E402
from cleveland.walk.ctqw import graph_hamiltonian  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=ROOT / "data/cleveland/raw")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments/cleveland/c006-circuit-packaging",
    )
    p.add_argument("--walk-time", type=float, default=10.0)
    p.add_argument("--n-times", type=int, default=16)
    p.add_argument("--hamiltonian", default="laplacian")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--targets", nargs="*", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    myo = PHASE1_GATE_RECEIPTS[TIGHTEST_PHASE1_TARGET]
    print(f"c006 circuit packaging — myosin P1 ρ={myo['spearman_rho']:.4f} kept visible")
    for job in PHASE1_PDB_JOBS:
        fetch_pdb(job.pdb_id, args.raw_dir)

    cfg = GraphConfig(seed=args.seed)
    ids = args.targets or list(TARGETS.keys())
    per = {}
    lines = [
        "# c006 — Qiskit CTQW packaging (metric fidelity vs exact eigh)",
        "",
        f"Myosin Phase 1 margin ρ=**{myo['spearman_rho']:.4f}** still surfaced.",
        "",
        "| Target | n_coarse | n_qubits | fidelity vs exact |",
        "|---|---|---|---|",
    ]

    export_dir = args.out / "metrics" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    for tid in ids:
        target = TARGETS[tid]
        nodes = load_residue_nodes(target.apo, args.raw_dir)
        coords = coords_matrix(nodes)
        g = build_contact_graph(nodes, coords, cfg)
        sources, _ = _source_graph_nodes(g, target.active_site_residues)
        if not sources:
            continue
        cg, labels, cg_info = coarse_grain(g, cfg)
        node_to_dense = {n: i for i, n in enumerate(cg_info["node_order"])}
        coarse_sources = sorted(
            {int(labels[node_to_dense[n]]) for n in sources if n in node_to_dense}
        )
        packed = package_graph_ctqw(
            cg,
            coarse_sources,
            args.walk_time,
            hamiltonian=args.hamiltonian,
            n_times=args.n_times,
        )
        pkg = packed["package"]
        star = " **← tightest P1**" if tid == TIGHTEST_PHASE1_TARGET else ""
        print(
            f"  {tid:16s} qubits={pkg['n_qubits']}  "
            f"fid={pkg['fidelity_vs_exact']:.6f}"
            + (" ← myosin" if tid == TIGHTEST_PHASE1_TARGET else "")
        )
        lines.append(
            f"| {tid}{star} | {cg_info['n_coarse']} | {pkg['n_qubits']} | "
            f"{pkg['fidelity_vs_exact']:.6f} |"
        )

        a, _ = adjacency_matrix(cg)
        h = graph_hamiltonian(a, form=args.hamiltonian)
        times = list(np.linspace(0.0, args.walk_time, args.n_times))
        braket = braket_export_payload(h, times)
        classiq = classiq_export_payload(pkg["n_qubits"], args.walk_time)
        (export_dir / f"{tid}_braket.json").write_text(json.dumps(braket) + "\n")
        np.save(export_dir / f"{tid}_H.npy", h)
        (export_dir / f"{tid}_classiq.json").write_text(json.dumps(classiq) + "\n")

        per[tid] = {
            "pdb_id": target.apo.pdb_id,
            "n_full": g.number_of_nodes(),
            "n_coarse": cg_info["n_coarse"],
            "package": pkg,
            "phase1_receipt": PHASE1_GATE_RECEIPTS.get(tid, {}),
            "tightest_phase1_margin": tid == TIGHTEST_PHASE1_TARGET,
            "exports": {
                "braket": str((export_dir / f"{tid}_braket.json").relative_to(args.out)),
                "classiq": str((export_dir / f"{tid}_classiq.json").relative_to(args.out)),
                "H_npy": str((export_dir / f"{tid}_H.npy").relative_to(args.out)),
            },
        }

    run_id = "c006-circuit-packaging"
    facts = {
        "run_id": run_id,
        "challenge": "cleveland-gqai-2026",
        "phase": "2_hardware_packaging",
        "method": "qiskit_hamiltonian_gate_statevector",
        "phase1_compression": {
            "tightest_target": TIGHTEST_PHASE1_TARGET,
            "tightest_spearman_rho": myo["spearman_rho"],
            "receipts": PHASE1_GATE_RECEIPTS,
        },
        "targets": per,
    }
    write_run_bundle(
        args.out,
        run_id=run_id,
        config={
            **asdict(cfg),
            "walk_time": args.walk_time,
            "n_times": args.n_times,
            "hamiltonian": args.hamiltonian,
        },
        facts=facts,
        meta={
            "task": "circuit_packaging",
            "challenge": "cleveland-gqai-2026",
            "notes": "Qiskit packaging fidelity vs eigh; Braket/Classiq exports only.",
            "seed": args.seed,
        },
        metrics={"per_target": {t: p["package"] for t, p in per.items()}},
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
