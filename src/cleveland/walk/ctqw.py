"""Continuous-time quantum walk (exact unitary) on a weighted contact graph.

Phase 2 uses scipy ``expm(-i H t)`` on the coarse graph — the quantum dynamics
the challenge asks for. Qiskit/Braket circuit depth comes later as hardware
packaging; the metric is identical.
"""

from __future__ import annotations

import numpy as np
import networkx as nx

from cleveland.graph import adjacency_matrix


def graph_hamiltonian(a: np.ndarray, *, form: str = "laplacian") -> np.ndarray:
    """Hermitian Hamiltonian for CTQW.

    - ``laplacian``: H = D - A (combinatorial Laplacian)
    - ``adjacency``: H = A
    """
    a = np.asarray(a, dtype=np.float64)
    if form == "adjacency":
        return a.copy()
    deg = np.diag(a.sum(axis=1))
    return deg - a


def time_averaged_transition_probs(
    h: np.ndarray,
    source_dense_idx: list[int],
    t_max: float,
    *,
    n_times: int = 64,
) -> tuple[np.ndarray, np.ndarray]:
    """Time-averaged |⟨j|U(t)|s⟩|² from a uniform source mixture.

    Uses a single Hermitian eigendecomposition of H so large graphs
    (e.g. myosin ~800 nodes) stay local-safe: O(n³) once, then O(n² n_t).

    Returns
    -------
    scores : (n,) occupation from sources
    connectivity : (n, n) time-averaged |U_ij|² (full matrix)
    """
    n = h.shape[0]
    # H = V diag(w) V^T  (real symmetric)
    w, v = np.linalg.eigh(h)
    times = np.linspace(0.0, t_max, n_times)
    conn = np.zeros((n, n), dtype=np.float64)
    for t in times:
        # U = V diag(e^{-i w t}) V^T
        phase = np.exp(-1j * w * t)
        u = (v * phase) @ v.T
        conn += (np.abs(u) ** 2).real
    conn /= n_times

    source_state = np.zeros(n, dtype=np.float64)
    for i in source_dense_idx:
        if 0 <= i < n:
            source_state[i] += 1.0
    if source_state.sum() <= 0:
        raise ValueError("no valid source indices for CTQW")
    source_state /= source_state.sum()
    scores = conn @ source_state
    return scores, conn


def ctqw_scores(
    g: nx.Graph,
    source_graph_nodes: list[int],
    t_max: float,
    *,
    hamiltonian: str = "laplacian",
    n_times: int = 64,
) -> tuple[np.ndarray, np.ndarray, list[int], dict]:
    """Return (scores, connectivity_matrix, node_order, meta)."""
    a, node_order = adjacency_matrix(g)
    idx_map = {n: i for i, n in enumerate(node_order)}
    source_dense = [idx_map[n] for n in source_graph_nodes if n in idx_map]
    if not source_dense:
        raise ValueError("active-site residues not present in graph component")
    h = graph_hamiltonian(a, form=hamiltonian)
    # Symmetry check (numerical)
    if not np.allclose(h, h.T):
        raise ValueError("Hamiltonian is not symmetric")
    scores, conn = time_averaged_transition_probs(h, source_dense, t_max, n_times=n_times)
    meta = {
        "n_nodes": len(node_order),
        "n_sources": len(source_dense),
        "t_max": t_max,
        "hamiltonian": hamiltonian,
        "n_times": n_times,
        "backend": "exact_unitary_eigh",
    }
    return scores, conn, node_order, meta
