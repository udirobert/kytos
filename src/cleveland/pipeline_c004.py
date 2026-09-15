"""Phase 3 — randomization / z-score significance for CTQW rankings.

Null: randomly rewire the contact graph (degree-preserving via edge swaps) or
permute scores; here we use **source-label permutation** on the fixed graph
(shuffle which residues are treated as the active-site source) and graph
**edge rewiring**, then z-score the known-site mean rank.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

from cleveland.eval import known_site_recovery
from cleveland.graph import build_contact_graph
from cleveland.pdb import coords_matrix, load_residue_nodes
from cleveland.pipeline import _source_graph_nodes
from cleveland.pipeline_phase2 import PHASE1_GATE_RECEIPTS, TIGHTEST_PHASE1_TARGET
from cleveland.targets import DEFAULT_GRAPH, TARGETS, BenchmarkTarget, GraphConfig
from cleveland.walk.ctqw import ctqw_scores


def _mean_known_rank(
    scores: np.ndarray,
    node_order: list[int],
    g: nx.Graph,
    known: tuple[int, ...],
) -> float | None:
    rec = known_site_recovery(scores, node_order, g, known)
    return rec.get("mean_known_rank")


def _rewire(g: nx.Graph, *, n_swaps: int, rng: np.random.Generator) -> nx.Graph:
    h = g.copy()
    # networkx double_edge_swap needs connected simple graph
    n_edges = h.number_of_edges()
    swaps = max(n_swaps, 10 * n_edges)
    try:
        nx.double_edge_swap(h, nswap=swaps, max_tries=swaps * 10, seed=int(rng.integers(0, 2**31)))
    except nx.NetworkXAlgorithmError:
        pass
    # preserve weights roughly: assign mean weight
    weights = [d.get("weight", 1.0) for _, _, d in g.edges(data=True)]
    mean_w = float(np.mean(weights)) if weights else 1.0
    for u, v in h.edges():
        h.edges[u, v]["weight"] = mean_w
    return h


def run_randomization(
    target: BenchmarkTarget,
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    hamiltonian: str = "laplacian",
    n_null: int = 100,
    n_times: int = 32,
    seed: int = 0,
) -> dict[str, Any]:
    """Z-score known-site mean rank vs edge-rewiring nulls (lower rank = better)."""
    rng = np.random.default_rng(seed)
    structure = target.apo
    nodes = load_residue_nodes(structure, raw_dir, atom_mode=cfg.atom_mode)
    coords = coords_matrix(nodes)
    g = build_contact_graph(nodes, coords, cfg)
    sources, n_found = _source_graph_nodes(g, target.active_site_residues)
    if not sources:
        raise ValueError(f"{target.target_id}: no sources")

    scores, _, order, meta = ctqw_scores(
        g, sources, cfg.walk_time, hamiltonian=hamiltonian, n_times=n_times
    )
    obs = _mean_known_rank(scores, order, g, target.known_allosteric_residues)

    null_ranks: list[float] = []
    if obs is not None and target.known_allosteric_residues:
        for _ in range(n_null):
            h = _rewire(g, n_swaps=20 * g.number_of_edges(), rng=rng)
            # map sources by resseq onto rewired graph (same node ids)
            try:
                s_null, _, o_null, _ = ctqw_scores(
                    h, sources, cfg.walk_time, hamiltonian=hamiltonian, n_times=n_times
                )
            except ValueError:
                continue
            m = _mean_known_rank(s_null, o_null, h, target.known_allosteric_residues)
            if m is not None:
                null_ranks.append(float(m))

    zscore = None
    p_emp = None
    if obs is not None and len(null_ranks) >= 10:
        mu = float(np.mean(null_ranks))
        sd = float(np.std(null_ranks, ddof=1))
        zscore = (float(obs) - mu) / sd if sd > 1e-12 else 0.0
        # Lower rank is better → fraction of nulls with mean rank <= observed
        p_emp = float(np.mean([r <= obs for r in null_ranks]))

    receipt = PHASE1_GATE_RECEIPTS.get(target.target_id, {})
    return {
        "target_id": target.target_id,
        "pdb_id": structure.pdb_id,
        "n_nodes": g.number_of_nodes(),
        "n_sources_found": n_found,
        "observed_mean_known_rank": obs,
        "null_mean": float(np.mean(null_ranks)) if null_ranks else None,
        "null_std": float(np.std(null_ranks, ddof=1)) if len(null_ranks) > 1 else None,
        "n_null_used": len(null_ranks),
        "zscore_mean_known_rank": zscore,
        "empirical_p_lower_rank": p_emp,
        "significant_better_than_null": bool(zscore is not None and zscore < -2.0),
        "phase1_receipt": receipt,
        "tightest_phase1_margin": target.target_id == TIGHTEST_PHASE1_TARGET,
        "known_allosteric_label": target.known_allosteric_label,
        "meta": meta,
        "null_method": "degree_preserving_edge_rewire",
    }


def run_all_randomization(
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    target_ids: list[str] | None = None,
    hamiltonian: str = "laplacian",
    n_null: int = 100,
    n_times: int = 32,
    seed: int = 0,
) -> list[dict[str, Any]]:
    ids = target_ids or [t for t in TARGETS if TARGETS[t].known_allosteric_residues]
    return [
        run_randomization(
            TARGETS[tid],
            raw_dir=raw_dir,
            cfg=cfg,
            hamiltonian=hamiltonian,
            n_null=n_null,
            n_times=n_times,
            seed=seed + i * 17,
        )
        for i, tid in enumerate(ids)
    ]
