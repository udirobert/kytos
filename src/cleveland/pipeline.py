"""Phase 1 pipeline: PDB → contact graph → CTRW → coarse-grain → Spearman gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cleveland.eval import audit_flags, spearman_gate, top_k_resseqs
from cleveland.graph import build_contact_graph, coarse_grain
from cleveland.pdb import coords_matrix, load_residue_nodes
from cleveland.targets import (
    DEFAULT_GRAPH,
    TARGETS,
    BenchmarkTarget,
    GraphConfig,
)
from cleveland.walk import ctrw_scores, project_coarse_scores_to_residues


def _source_graph_nodes(g, active_resseqs: tuple[int, ...]) -> tuple[list[int], int]:
    wanted = set(active_resseqs)
    nodes = [n for n, d in g.nodes(data=True) if d["resseq"] in wanted]
    return nodes, len(nodes)


def run_structure(
    target: BenchmarkTarget,
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    use_apo: bool = True,
) -> dict[str, Any]:
    """Run classical CTRW + coarse-grain gate on apo (or exploratory) structure."""
    structure = target.apo if use_apo else target.holo
    if structure is None:
        raise ValueError(f"{target.target_id}: no structure for use_apo={use_apo}")

    nodes = load_residue_nodes(structure, raw_dir, atom_mode=cfg.atom_mode)
    coords = coords_matrix(nodes)
    g = build_contact_graph(nodes, coords, cfg)

    sources, n_found = _source_graph_nodes(g, target.active_site_residues)
    if not sources:
        # Fallback: use geometric center residue as source so the gate still runs;
        # flag via n_found == 0.
        center = coords.mean(axis=0)
        # Map original node indices — graph may be LCC subgraph.
        # Pick graph node closest to centroid among remaining nodes.
        best = None
        best_d = float("inf")
        for n, data in g.nodes(data=True):
            # find residue coord by resseq
            for node in nodes:
                if node.resseq == data["resseq"] and node.chain == data["chain"]:
                    dist = float(np.linalg.norm(node.coord - center))
                    if dist < best_d:
                        best_d = dist
                        best = n
                    break
        sources = [best] if best is not None else [next(iter(g.nodes()))]

    scores_full, order_full, walk_meta = ctrw_scores(g, sources, cfg.walk_time)

    cg, labels, cg_info = coarse_grain(g, cfg)
    # Map active-site graph nodes → coarse labels via dense index.
    node_to_dense = {n: i for i, n in enumerate(cg_info["node_order"])}
    coarse_sources = sorted({int(labels[node_to_dense[n]]) for n in sources if n in node_to_dense})
    scores_coarse, order_coarse, _ = ctrw_scores(cg, coarse_sources, cfg.walk_time)
    # Align coarse scores to label ids 0..k-1 (order_coarse should be 0..k-1).
    coarse_by_label = np.zeros(cg_info["n_coarse"], dtype=np.float64)
    for i, lab in enumerate(order_coarse):
        coarse_by_label[int(lab)] = scores_coarse[i]
    projected = project_coarse_scores_to_residues(coarse_by_label, labels)

    # Align projected to order_full (both use cg_info node_order == order from full adj).
    # scores_full and projected share the same dense order as adjacency of g.
    gate = spearman_gate(scores_full, projected, threshold=cfg.spearman_threshold)

    exclude_sources = set(target.active_site_residues)
    hits = top_k_resseqs(scores_full, order_full, g, k=5, exclude=exclude_sources)

    flags = audit_flags(
        n_residues=g.number_of_nodes(),
        n_edges=g.number_of_edges(),
        gate=gate,
        n_sources_found=n_found,
        n_sources_requested=len(target.active_site_residues),
    )

    return {
        "target_id": target.target_id,
        "name": target.name,
        "pdb_id": structure.pdb_id,
        "role": structure.role,
        "n_residues_parsed": len(nodes),
        "n_graph_nodes": g.number_of_nodes(),
        "n_graph_edges": g.number_of_edges(),
        "n_coarse": cg_info["n_coarse"],
        "n_sources_found": n_found,
        "n_sources_used": len(sources),
        "walk": walk_meta,
        "gate": gate,
        "hit_list_top5": hits,
        "flags": flags,
        "known_allosteric_label": target.known_allosteric_label,
    }


def run_all_apo(
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    target_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    ids = target_ids or list(TARGETS.keys())
    results = []
    for tid in ids:
        results.append(run_structure(TARGETS[tid], raw_dir=raw_dir, cfg=cfg, use_apo=True))
    return results
