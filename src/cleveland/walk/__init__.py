"""Classical continuous-time random walk on a weighted contact graph."""

from __future__ import annotations

import numpy as np
import networkx as nx
from scipy.linalg import expm

from cleveland.graph import adjacency_matrix


def random_walk_generator(a: np.ndarray) -> np.ndarray:
    """Infinitesimal generator Q for continuous-time random walk.

    Q = D^{-1} A - I  (rows sum to 0), with absorbing-safe degree handling.
    """
    n = a.shape[0]
    deg = a.sum(axis=1)
    q = np.zeros_like(a)
    for i in range(n):
        if deg[i] <= 0:
            continue
        q[i, :] = a[i, :] / deg[i]
        q[i, i] -= 1.0
    return q


def time_averaged_occupation(
    q: np.ndarray,
    source_dense_idx: list[int],
    t_max: float,
    *,
    n_times: int = 64,
) -> np.ndarray:
    """Time-averaged probability mass from a uniform source mixture.

    score_j = (1/T) ∫_0^T p_j(t) dt approximated by trapezoidal samples of
    p(t) = p0 @ expm(t Q).
    """
    n = q.shape[0]
    p0 = np.zeros(n, dtype=np.float64)
    for i in source_dense_idx:
        if 0 <= i < n:
            p0[i] += 1.0
    if p0.sum() <= 0:
        raise ValueError("no valid source indices on this graph component")
    p0 /= p0.sum()

    times = np.linspace(0.0, t_max, n_times)
    acc = np.zeros(n, dtype=np.float64)
    for t in times:
        p_t = p0 @ expm(t * q)
        acc += np.maximum(p_t, 0.0)
    acc /= n_times
    return acc


def ctrw_scores(
    g: nx.Graph,
    source_graph_nodes: list[int],
    t_max: float,
) -> tuple[np.ndarray, list[int], dict]:
    """Return (scores_aligned_to_node_order, node_order, meta)."""
    a, node_order = adjacency_matrix(g)
    idx_map = {n: i for i, n in enumerate(node_order)}
    source_dense = [idx_map[n] for n in source_graph_nodes if n in idx_map]
    if not source_dense:
        raise ValueError("active-site residues not present in graph component")
    q = random_walk_generator(a)
    scores = time_averaged_occupation(q, source_dense, t_max)
    meta = {
        "n_nodes": len(node_order),
        "n_sources": len(source_dense),
        "t_max": t_max,
    }
    return scores, node_order, meta


def project_coarse_scores_to_residues(
    coarse_scores: np.ndarray,
    labels: np.ndarray,
) -> np.ndarray:
    """Map each coarse supernode score onto its member residues."""
    return np.asarray([coarse_scores[int(c)] for c in labels], dtype=np.float64)
