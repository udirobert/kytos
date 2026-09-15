"""Phase 2 pipeline: CTQW on coarse graph + classical comparison.

Recomputes the Phase 1 coarse-grain Spearman gate and **surfaces it in every
result**, with cardiac myosin called out as the tightest margin (ρ≈0.823).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cleveland.eval import (
    audit_flags,
    known_site_recovery,
    spearman_gate,
    top_k_resseqs,
)
from cleveland.graph import build_contact_graph, coarse_grain
from cleveland.pdb import coords_matrix, load_residue_nodes
from cleveland.pipeline import _source_graph_nodes
from cleveland.targets import (
    DEFAULT_GRAPH,
    TARGETS,
    BenchmarkTarget,
    GraphConfig,
)
from cleveland.walk import ctrw_scores, project_coarse_scores_to_residues
from cleveland.walk.ctqw import ctqw_scores


# Phase 1 receipts (c001) — keep myosin margin visible for Phase 2 review.
PHASE1_GATE_RECEIPTS: dict[str, dict[str, Any]] = {
    "kras_g12c": {"spearman_rho": 0.8573, "n_full": 169, "n_coarse": 32, "pass": True},
    "bcr_abl1": {"spearman_rho": 0.8544, "n_full": 287, "n_coarse": 48, "pass": True},
    "cardiac_myosin": {
        "spearman_rho": 0.8230,
        "n_full": 795,
        "n_coarse": 56,
        "pass": True,
        "margin_to_threshold": 0.0230,
        "note": (
            "Tightest Phase 1 compression margin (threshold 0.8). "
            "If Phase 2 connectivity looks weaker here, ask whether "
            "coarse-graining held up — receipts are this ρ and n_full→n_coarse."
        ),
    },
    "cmyc_max": {"spearman_rho": 0.9425, "n_full": 88, "n_coarse": 32, "pass": True},
}

TIGHTEST_PHASE1_TARGET = "cardiac_myosin"


def run_structure_phase2(
    target: BenchmarkTarget,
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    hamiltonian: str = "laplacian",
) -> dict[str, Any]:
    """CTQW + CTRW on the same coarse graph; Phase 1 gate recomputed and logged."""
    structure = target.apo
    nodes = load_residue_nodes(structure, raw_dir, atom_mode=cfg.atom_mode)
    coords = coords_matrix(nodes)
    g = build_contact_graph(nodes, coords, cfg)

    sources, n_found = _source_graph_nodes(g, target.active_site_residues)
    if not sources:
        center = coords.mean(axis=0)
        best = None
        best_d = float("inf")
        for n, data in g.nodes(data=True):
            for node in nodes:
                if node.resseq == data["resseq"] and node.chain == data["chain"]:
                    dist = float(np.linalg.norm(node.coord - center))
                    if dist < best_d:
                        best_d = dist
                        best = n
                    break
        sources = [best] if best is not None else [next(iter(g.nodes()))]

    # Phase 1 gate (recompute — must still pass before trusting CTQW on coarse).
    scores_full, order_full, _ = ctrw_scores(g, sources, cfg.walk_time)
    cg, labels, cg_info = coarse_grain(g, cfg)
    node_to_dense = {n: i for i, n in enumerate(cg_info["node_order"])}
    coarse_sources = sorted({int(labels[node_to_dense[n]]) for n in sources if n in node_to_dense})

    scores_ctrw_coarse, order_coarse, _ = ctrw_scores(cg, coarse_sources, cfg.walk_time)
    ctrw_by_label = np.zeros(cg_info["n_coarse"], dtype=np.float64)
    for i, lab in enumerate(order_coarse):
        ctrw_by_label[int(lab)] = scores_ctrw_coarse[i]
    projected = project_coarse_scores_to_residues(ctrw_by_label, labels)
    gate = spearman_gate(scores_full, projected, threshold=cfg.spearman_threshold)

    # CTQW on coarse graph
    scores_ctqw, connectivity, order_q, q_meta = ctqw_scores(
        cg,
        coarse_sources,
        cfg.walk_time,
        hamiltonian=hamiltonian,
    )
    # Align CTQW scores to label ids
    ctqw_by_label = np.zeros(cg_info["n_coarse"], dtype=np.float64)
    for i, lab in enumerate(order_q):
        ctqw_by_label[int(lab)] = scores_ctqw[i]
    # Reorder connectivity to label-major axes 0..k-1
    k = cg_info["n_coarse"]
    conn_by_label = np.zeros((k, k), dtype=np.float64)
    for i, li in enumerate(order_q):
        for j, lj in enumerate(order_q):
            conn_by_label[int(li), int(lj)] = connectivity[i, j]

    # Project CTQW coarse scores onto residue graph for hit list + blind check
    ctqw_projected = project_coarse_scores_to_residues(ctqw_by_label, labels)
    # order_full aligns with labels / scores_full dense order
    exclude_sources = set(target.active_site_residues)
    hits_ctqw = top_k_resseqs(ctqw_projected, order_full, g, k=5, exclude=exclude_sources)
    hits_ctrw = top_k_resseqs(projected, order_full, g, k=5, exclude=exclude_sources)

    vs_classical = spearman_gate(ctqw_projected, projected, threshold=0.0)
    recovery_ctqw = known_site_recovery(
        ctqw_projected, order_full, g, target.known_allosteric_residues
    )
    recovery_ctrw = known_site_recovery(projected, order_full, g, target.known_allosteric_residues)

    receipt = PHASE1_GATE_RECEIPTS.get(target.target_id, {})
    tightest = target.target_id == TIGHTEST_PHASE1_TARGET

    flags = audit_flags(
        n_residues=g.number_of_nodes(),
        n_edges=g.number_of_edges(),
        gate=gate,
        n_sources_found=n_found,
        n_sources_requested=len(target.active_site_residues),
    )
    if tightest:
        flags.append(
            {
                "id": "phase1_tightest_compression_margin",
                "severity": "info",
                "detail": (
                    f"cardiac_myosin Phase 1 Spearman ρ="
                    f"{receipt.get('spearman_rho', gate['spearman_rho']):.4f} "
                    f"(margin {receipt.get('margin_to_threshold', gate['spearman_rho'] - 0.8):.4f} "
                    f"above 0.8); watch Phase 2 weakness here for compression risk"
                ),
            }
        )

    return {
        "target_id": target.target_id,
        "name": target.name,
        "pdb_id": structure.pdb_id,
        "role": structure.role,
        "n_graph_nodes": g.number_of_nodes(),
        "n_graph_edges": g.number_of_edges(),
        "n_coarse": cg_info["n_coarse"],
        "n_sources_found": n_found,
        "phase1_gate": {
            **gate,
            "c001_receipt": receipt,
            "tightest_phase1_margin": tightest,
        },
        "ctqw": {
            **q_meta,
            "hit_list_top5": hits_ctqw,
            "known_site_recovery": recovery_ctqw,
        },
        "ctrw_coarse": {
            "hit_list_top5": hits_ctrw,
            "known_site_recovery": recovery_ctrw,
        },
        "quantum_vs_classical": {
            "spearman_rho": vs_classical["spearman_rho"],
            "note": "Spearman between CTQW and CTRW residue rankings on same coarse graph",
        },
        "connectivity_matrix": conn_by_label,
        "known_allosteric_label": target.known_allosteric_label,
        "flags": flags,
    }


def run_all_phase2(
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    target_ids: list[str] | None = None,
    hamiltonian: str = "laplacian",
) -> list[dict[str, Any]]:
    ids = target_ids or list(TARGETS.keys())
    return [
        run_structure_phase2(TARGETS[tid], raw_dir=raw_dir, cfg=cfg, hamiltonian=hamiltonian)
        for tid in ids
    ]
