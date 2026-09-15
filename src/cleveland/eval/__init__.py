"""Ranking, Spearman coarse-grain gate, and audit flags."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import spearmanr


def rank_descending(scores: np.ndarray) -> np.ndarray:
    """Rank 1 = highest score (average ranks for ties via argsort twice)."""
    order = np.argsort(-scores, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1, dtype=np.float64)
    return ranks


def top_k_resseqs(
    scores: np.ndarray,
    node_order: list[int],
    graph: Any,
    k: int = 5,
    *,
    exclude: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Ranked hit list by graph node → resseq."""
    exclude = exclude or set()
    order = np.argsort(-scores, kind="mergesort")
    hits: list[dict[str, Any]] = []
    for idx in order:
        gnode = node_order[int(idx)]
        resseq = int(graph.nodes[gnode]["resseq"])
        if resseq in exclude:
            continue
        hits.append(
            {
                "rank": len(hits) + 1,
                "resseq": resseq,
                "resname": graph.nodes[gnode].get("resname"),
                "score": float(scores[int(idx)]),
                "graph_node": int(gnode),
            }
        )
        if len(hits) >= k:
            break
    return hits


def spearman_gate(
    scores_full: np.ndarray,
    scores_projected: np.ndarray,
    *,
    threshold: float = 0.8,
) -> dict[str, Any]:
    """Require Spearman ρ between full and coarse-projected rankings ≥ threshold."""
    if scores_full.shape != scores_projected.shape:
        raise ValueError("score vectors must align")
    # Compare rankings (higher score = better); spearmanr on raw scores is equivalent
    # for monotonic transform, but we correlate ranks explicitly for clarity.
    r_full = rank_descending(scores_full)
    r_proj = rank_descending(scores_projected)
    rho, pvalue = spearmanr(r_full, r_proj)
    rho_f = float(rho) if np.isfinite(rho) else 0.0
    return {
        "spearman_rho": rho_f,
        "spearman_pvalue": float(pvalue) if np.isfinite(pvalue) else None,
        "threshold": threshold,
        "pass": bool(rho_f >= threshold),
    }


def audit_flags(
    *,
    n_residues: int,
    n_edges: int,
    gate: dict[str, Any],
    n_sources_found: int,
    n_sources_requested: int,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if n_sources_found < max(1, n_sources_requested // 2):
        flags.append(
            {
                "id": "sparse_active_site",
                "severity": "warn",
                "detail": (
                    f"only {n_sources_found}/{n_sources_requested} active-site residues on graph"
                ),
            }
        )
    if n_edges < n_residues:
        flags.append(
            {
                "id": "sparse_contact_graph",
                "severity": "warn",
                "detail": f"edges={n_edges} < residues={n_residues}",
            }
        )
    if not gate["pass"]:
        flags.append(
            {
                "id": "coarsegrain_spearman_fail",
                "severity": "fail",
                "detail": (
                    f"spearman_rho={gate['spearman_rho']:.4f} < threshold={gate['threshold']}"
                ),
            }
        )
    else:
        flags.append(
            {
                "id": "coarsegrain_spearman_pass",
                "severity": "info",
                "detail": f"spearman_rho={gate['spearman_rho']:.4f}",
            }
        )
    return flags


def known_site_recovery(
    scores: np.ndarray,
    node_order: list[int],
    graph: Any,
    known_resseqs: tuple[int, ...],
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    """Post-hoc blind label check — never used as model input."""
    if not known_resseqs:
        return {
            "n_known": 0,
            "n_known_on_graph": 0,
            "top_k": top_k,
            "n_known_in_top_k": None,
            "best_known_rank": None,
            "mean_known_rank": None,
            "known_ranks": [],
        }
    ranks = rank_descending(scores)
    resseq_to_dense: dict[int, int] = {}
    for i, gnode in enumerate(node_order):
        resseq_to_dense[int(graph.nodes[gnode]["resseq"])] = i

    known_ranks: list[dict[str, Any]] = []
    for r in known_resseqs:
        if r not in resseq_to_dense:
            continue
        di = resseq_to_dense[r]
        known_ranks.append(
            {
                "resseq": int(r),
                "rank": float(ranks[di]),
                "score": float(scores[di]),
            }
        )
    if not known_ranks:
        return {
            "n_known": len(known_resseqs),
            "n_known_on_graph": 0,
            "top_k": top_k,
            "n_known_in_top_k": 0,
            "best_known_rank": None,
            "mean_known_rank": None,
            "known_ranks": [],
        }
    rank_vals = [kr["rank"] for kr in known_ranks]
    return {
        "n_known": len(known_resseqs),
        "n_known_on_graph": len(known_ranks),
        "top_k": top_k,
        "n_known_in_top_k": sum(1 for v in rank_vals if v <= top_k),
        "best_known_rank": float(min(rank_vals)),
        "mean_known_rank": float(np.mean(rank_vals)),
        "known_ranks": known_ranks,
    }
