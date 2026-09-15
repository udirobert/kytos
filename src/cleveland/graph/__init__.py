"""Elastic-network contact graphs and spectral coarse-graining."""

from __future__ import annotations

import numpy as np
import networkx as nx
from sklearn.cluster import SpectralClustering

from cleveland.pdb import ResidueNode
from cleveland.targets import GraphConfig


def pairwise_distances(coords: np.ndarray) -> np.ndarray:
    """Euclidean pairwise distances (Å)."""
    diff = coords[:, None, :] - coords[None, :, :]
    return np.sqrt(np.sum(diff * diff, axis=-1))


def edge_weight(dist: float, cfg: GraphConfig) -> float:
    if dist <= 0:
        return 0.0
    if cfg.weight == "gaussian":
        return float(np.exp(-((dist / cfg.gaussian_sigma) ** 2)))
    # inverse-distance (default ENM-style)
    return float(1.0 / dist)


def build_contact_graph(
    nodes: list[ResidueNode],
    coords: np.ndarray,
    cfg: GraphConfig,
) -> nx.Graph:
    """Undirected weighted contact graph within cutoff."""
    n = len(nodes)
    dists = pairwise_distances(coords)
    g = nx.Graph()
    for i, node in enumerate(nodes):
        g.add_node(
            i,
            resseq=node.resseq,
            resname=node.resname,
            chain=node.chain,
        )
    cutoff = cfg.cutoff_angstrom
    for i in range(n):
        for j in range(i + 1, n):
            d = float(dists[i, j])
            if d <= cutoff:
                w = edge_weight(d, cfg)
                if w > 0:
                    g.add_edge(i, j, weight=w, distance=d)
    if g.number_of_edges() == 0:
        raise ValueError("contact graph has no edges — raise cutoff or check domain mask")
    # Keep largest connected component for walk stability.
    if not nx.is_connected(g):
        largest = max(nx.connected_components(g), key=len)
        g = g.subgraph(largest).copy()
    return g


def adjacency_matrix(g: nx.Graph) -> tuple[np.ndarray, list[int]]:
    """Dense weighted adjacency for nodes in sorted order."""
    nodes = sorted(g.nodes())
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    a = np.zeros((n, n), dtype=np.float64)
    for u, v, data in g.edges(data=True):
        i, j = idx[u], idx[v]
        w = float(data.get("weight", 1.0))
        a[i, j] = w
        a[j, i] = w
    return a, nodes


def choose_n_clusters(n_nodes: int, cfg: GraphConfig) -> int:
    """Target 32–64 supernodes (~5–6 qubit budget later).

    Prefer ~n/6 so mid-size kinase domains retain ranking fidelity under
    spectral coarse-graining; clip into [n_clusters_min, n_clusters_max].
    """
    if n_nodes <= cfg.n_clusters_min:
        return max(2, n_nodes // 2)
    guess = int(round(n_nodes / 6))
    return int(np.clip(guess, cfg.n_clusters_min, cfg.n_clusters_max))


def coarse_grain(
    g: nx.Graph,
    cfg: GraphConfig,
) -> tuple[nx.Graph, np.ndarray, dict]:
    """Spectral clustering → supernode graph with aggregated edge weights.

    Returns (coarse_graph, labels_by_dense_index, info).
    labels align with sorted(g.nodes()) order used by adjacency_matrix.
    """
    a, node_order = adjacency_matrix(g)
    n = a.shape[0]
    k = choose_n_clusters(n, cfg)
    # Normalized Laplacian affinity = adjacency (sklearn spectral clustering).
    clustering = SpectralClustering(
        n_clusters=k,
        affinity="precomputed",
        assign_labels="kmeans",
        random_state=cfg.seed,
    )
    labels = clustering.fit_predict(a)

    # Build coarse adjacency: sum of inter-cluster edge weights.
    coarse_a = np.zeros((k, k), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            w = a[i, j]
            if w <= 0:
                continue
            li, lj = int(labels[i]), int(labels[j])
            if li == lj:
                continue
            coarse_a[li, lj] += w
            coarse_a[lj, li] += w

    cg = nx.Graph()
    for c in range(k):
        members = [node_order[i] for i in range(n) if int(labels[i]) == c]
        cg.add_node(c, members=members, size=len(members))
    for i in range(k):
        for j in range(i + 1, k):
            w = coarse_a[i, j]
            if w > 0:
                cg.add_edge(i, j, weight=float(w))

    info = {
        "n_full": n,
        "n_coarse": k,
        "n_clusters": k,
        "node_order": node_order,
    }
    return cg, labels, info
