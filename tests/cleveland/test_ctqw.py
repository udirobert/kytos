"""CTQW unit tests (exact unitary; no quantum SDK)."""

from __future__ import annotations

import numpy as np
import networkx as nx
import pytest

from cleveland.walk.ctqw import ctqw_scores, graph_hamiltonian, time_averaged_transition_probs


def test_hamiltonian_laplacian_symmetric():
    a = np.array([[0.0, 1.0, 0.5], [1.0, 0.0, 1.0], [0.5, 1.0, 0.0]])
    h = graph_hamiltonian(a, form="laplacian")
    assert np.allclose(h, h.T)
    assert np.allclose(np.diag(h), a.sum(axis=1))


def test_ctqw_probs_normalized():
    a = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
    h = graph_hamiltonian(a, form="laplacian")
    scores, conn = time_averaged_transition_probs(h, [0], t_max=5.0, n_times=32)
    assert scores.shape == (3,)
    assert np.allclose(conn.sum(axis=0), 1.0, atol=1e-5)  # columns ≈ stochastic
    assert scores.sum() == pytest.approx(1.0, abs=1e-5)


def test_ctqw_on_path_graph():
    g = nx.path_graph(10)
    for u, v in g.edges():
        g.edges[u, v]["weight"] = 1.0
    scores, conn, order, meta = ctqw_scores(g, [0], t_max=3.0)
    assert len(scores) == 10
    assert conn.shape == (10, 10)
    assert meta["backend"] == "exact_unitary_expm"
    # Source end should retain relatively high occupation early
    assert scores[order.index(0)] >= scores[order.index(9)]
