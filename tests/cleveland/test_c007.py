"""Tests for c007 topology helpers."""

from __future__ import annotations

import networkx as nx

from cleveland.pipeline_c007 import _residual, expand_sources


def test_expand_sources_neighbors():
    g = nx.path_graph(5)
    assert expand_sources(g, [2], "active") == [2]
    assert expand_sources(g, [2], "active_plus_neighbors") == [1, 2, 3]


def test_residual_sums_near_zero():
    g = nx.path_graph(8)
    for u, v in g.edges():
        g.edges[u, v]["weight"] = 1.0
    scores, order, meta = _residual(g, [0], walk_time=5.0, hamiltonian="laplacian", n_times=16)
    assert meta["score_mode"] == "ctqw_minus_ctrw"
    assert len(scores) == len(order) == 8
    assert abs(float(scores.sum())) < 1e-10
