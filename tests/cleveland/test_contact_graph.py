"""Unit tests for Cleveland Phase 1 classical pipeline (no network)."""

from __future__ import annotations

import numpy as np
import networkx as nx
import pytest

from cleveland.eval import rank_descending, spearman_gate
from cleveland.graph import build_contact_graph, choose_n_clusters, coarse_grain
from cleveland.pdb import ResidueNode
from cleveland.targets import GraphConfig
from cleveland.walk import ctrw_scores, random_walk_generator, time_averaged_occupation


def _chain_nodes(n: int = 40, spacing: float = 3.8) -> list[ResidueNode]:
    nodes = []
    for i in range(n):
        nodes.append(
            ResidueNode(
                chain="A",
                resseq=i + 1,
                resname="ALA",
                coord=np.array([i * spacing, 0.0, 0.0], dtype=np.float64),
                index=i,
            )
        )
    return nodes


def test_contact_graph_chain():
    nodes = _chain_nodes(30)
    coords = np.stack([n.coord for n in nodes])
    cfg = GraphConfig(cutoff_angstrom=8.0, weight="inverse")
    g = build_contact_graph(nodes, coords, cfg)
    assert g.number_of_nodes() == 30
    assert g.number_of_edges() >= 29
    assert nx.is_connected(g)


def test_ctrw_mass_conserved_approximately():
    a = np.array(
        [
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
        ]
    )
    q = random_walk_generator(a)
    assert np.allclose(q.sum(axis=1), 0.0, atol=1e-10)
    scores = time_averaged_occupation(q, [0], t_max=5.0, n_times=32)
    assert scores.shape == (3,)
    assert scores[0] >= scores[2]  # closer to source on average early


def test_spearman_gate_identical_passes():
    s = np.array([0.5, 0.4, 0.1, 0.05, 0.01])
    gate = spearman_gate(s, s.copy(), threshold=0.8)
    assert gate["pass"] is True
    assert gate["spearman_rho"] == pytest.approx(1.0)


def test_spearman_gate_anti_correlated_fails():
    s = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
    gate = spearman_gate(s, -s, threshold=0.8)
    assert gate["pass"] is False


def test_coarse_grain_reduces_nodes():
    nodes = _chain_nodes(80)
    coords = np.stack([n.coord for n in nodes])
    cfg = GraphConfig(cutoff_angstrom=9.0, n_clusters_min=32, n_clusters_max=64, seed=0)
    g = build_contact_graph(nodes, coords, cfg)
    cg, labels, info = coarse_grain(g, cfg)
    assert info["n_coarse"] == choose_n_clusters(info["n_full"], cfg)
    assert cg.number_of_nodes() == info["n_coarse"]
    assert labels.shape == (info["n_full"],)


def test_ctrw_on_graph_smoke():
    nodes = _chain_nodes(25)
    coords = np.stack([n.coord for n in nodes])
    cfg = GraphConfig(cutoff_angstrom=8.0)
    g = build_contact_graph(nodes, coords, cfg)
    scores, order, meta = ctrw_scores(g, [0], t_max=3.0)
    assert len(scores) == len(order) == meta["n_nodes"]
    assert scores[order.index(0)] == pytest.approx(scores.max())


def test_rank_descending():
    ranks = rank_descending(np.array([0.1, 0.9, 0.5]))
    assert ranks[1] == 1  # highest score
    assert ranks[0] == 3
