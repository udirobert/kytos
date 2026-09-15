"""Phase 2b — full-graph vs coarse CTQW compression audit.

Answers the reviewer question raised by cardiac myosin's tight Phase 1 margin
(ρ=0.823): does coarse-graining destroy CTQW known-site recovery?
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cleveland.eval import known_site_recovery, spearman_gate, top_k_resseqs
from cleveland.graph import build_contact_graph, coarse_grain
from cleveland.pdb import coords_matrix, load_residue_nodes
from cleveland.pipeline import _source_graph_nodes
from cleveland.pipeline_phase2 import PHASE1_GATE_RECEIPTS, TIGHTEST_PHASE1_TARGET
from cleveland.targets import DEFAULT_GRAPH, TARGETS, BenchmarkTarget, GraphConfig
from cleveland.walk import project_coarse_scores_to_residues
from cleveland.walk.ctqw import ctqw_scores


def run_compression_audit(
    target: BenchmarkTarget,
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    hamiltonian: str = "laplacian",
    n_times: int = 48,
) -> dict[str, Any]:
    structure = target.apo
    nodes = load_residue_nodes(structure, raw_dir, atom_mode=cfg.atom_mode)
    coords = coords_matrix(nodes)
    g = build_contact_graph(nodes, coords, cfg)
    sources, n_found = _source_graph_nodes(g, target.active_site_residues)
    if not sources:
        raise ValueError(f"{target.target_id}: no active-site sources on graph")

    # Full-resolution CTQW
    scores_full, _, order_full, meta_full = ctqw_scores(
        g, sources, cfg.walk_time, hamiltonian=hamiltonian, n_times=n_times
    )

    # Coarse CTQW → project to residues
    cg, labels, cg_info = coarse_grain(g, cfg)
    node_to_dense = {n: i for i, n in enumerate(cg_info["node_order"])}
    coarse_sources = sorted({int(labels[node_to_dense[n]]) for n in sources if n in node_to_dense})
    scores_c, _, order_c, meta_c = ctqw_scores(
        cg, coarse_sources, cfg.walk_time, hamiltonian=hamiltonian, n_times=n_times
    )
    by_label = np.zeros(cg_info["n_coarse"], dtype=np.float64)
    for i, lab in enumerate(order_c):
        by_label[int(lab)] = scores_c[i]
    scores_proj = project_coarse_scores_to_residues(by_label, labels)

    rank_corr = spearman_gate(scores_full, scores_proj, threshold=0.8)
    rec_full = known_site_recovery(scores_full, order_full, g, target.known_allosteric_residues)
    rec_coarse = known_site_recovery(scores_proj, order_full, g, target.known_allosteric_residues)
    exclude = set(target.active_site_residues)
    hits_full = top_k_resseqs(scores_full, order_full, g, k=5, exclude=exclude)
    hits_coarse = top_k_resseqs(scores_proj, order_full, g, k=5, exclude=exclude)

    receipt = PHASE1_GATE_RECEIPTS.get(target.target_id, {})
    tightest = target.target_id == TIGHTEST_PHASE1_TARGET

    # Compression verdict for known-site signal
    full_best = rec_full.get("best_known_rank")
    coarse_best = rec_coarse.get("best_known_rank")
    if full_best is None or coarse_best is None:
        compression_verdict = "no_known_labels"
    elif coarse_best <= full_best * 1.25 + 5:
        compression_verdict = "compression_preserves_known_signal"
    elif full_best < coarse_best:
        compression_verdict = "compression_degrades_known_signal"
    else:
        compression_verdict = "coarse_better_or_noise"

    return {
        "target_id": target.target_id,
        "name": target.name,
        "pdb_id": structure.pdb_id,
        "n_full": g.number_of_nodes(),
        "n_coarse": cg_info["n_coarse"],
        "n_sources_found": n_found,
        "phase1_receipt": receipt,
        "tightest_phase1_margin": tightest,
        "ctqw_full_vs_coarse_spearman": rank_corr,
        "recovery_full": rec_full,
        "recovery_coarse": rec_coarse,
        "hit_list_full_top5": hits_full,
        "hit_list_coarse_top5": hits_coarse,
        "compression_verdict": compression_verdict,
        "meta_full": meta_full,
        "meta_coarse": meta_c,
        "known_allosteric_label": target.known_allosteric_label,
    }


def run_all_compression_audits(
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    target_ids: list[str] | None = None,
    hamiltonian: str = "laplacian",
    n_times: int = 48,
) -> list[dict[str, Any]]:
    ids = target_ids or list(TARGETS.keys())
    return [
        run_compression_audit(
            TARGETS[tid],
            raw_dir=raw_dir,
            cfg=cfg,
            hamiltonian=hamiltonian,
            n_times=n_times,
        )
        for tid in ids
    ]
