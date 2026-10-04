"""Generate c008 figures into narrative/figs/ (run from repo root, .venv python)."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

BASE = Path("experiments/cleveland/c008-moth-qpu-tomography")
FIGS = BASE / "narrative" / "figs"
FIGS.mkdir(parents=True, exist_ok=True)

PAULIS = ["XX", "XY", "XZ", "YX", "YY", "YZ", "ZX", "ZY", "ZZ"]
ROLE_COLORS = {
    "source": "#d94f3d",
    "known": "#3d7fd9",
    "sourceknown": "#a03dd9",
    "": "#9aa0a6",
}
EMU_C, QPU_C = "#3d7fd9", "#d94f3d"
TARGETS = [("KRAS G12C", "kras"), ("cardiac myosin", "myosin")]

cores = {t: json.load(open(BASE / f"metrics/graphs/{t}_core.json")) for _, t in TARGETS}
res = {
    t: {
        m: json.load(open(BASE / f"metrics/results/{t}_{m}.json"))["result"]["output"]
        for m in ("emu", "qpu")
    }
    for t in ("kras", "myosin", "ctrl")
}


def corr_norm(out, edge):
    rel = out["tomography"]["relationships"]
    v = rel.get(f"{edge[0]},{edge[1]}") or rel.get(f"{edge[1]},{edge[0]}")
    return np.linalg.norm([v[p] for p in PAULIS]) if v else np.nan


def bloch_r(t, mode):
    b = res[t][mode]["tomography"]["bloch"]
    return [np.linalg.norm([b[str(i)]["X"], b[str(i)]["Y"], b[str(i)]["Z"]]) for i in range(20)]


# fig 1: the two coupling graphs, colored by role
fig, axes = plt.subplots(1, 2, figsize=(11, 5))
for ax, (name, t) in zip(axes, TARGETS):
    core = cores[t]
    G = nx.Graph()
    G.add_nodes_from(range(core["n_nodes"]))
    G.add_edges_from(core["edges"])
    pos = nx.spring_layout(G, seed=4, k=1.6)
    roles = {int(i): d["role"] for i, d in core["node_map"].items()}
    colors = [ROLE_COLORS[roles[n]] for n in G.nodes]
    nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.45, width=1.2)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=colors, node_size=320, edgecolors="#222")
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=7)
    n_e = len(core["edges"])
    ax.set_title(f"{name} — {core['n_nodes']}-qubit allosteric core\n({n_e} edges)", fontsize=11)
    ax.axis("off")
legend_items = [
    ("source (active site)", ROLE_COLORS["source"]),
    ("known site", ROLE_COLORS["known"]),
    ("source + known (both)", ROLE_COLORS["sourceknown"]),
    ("connector", ROLE_COLORS[""]),
]
handles = [
    plt.Line2D([], [], marker="o", ls="", color=color, label=name, markersize=8)
    for name, color in legend_items
]
fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False)
fig.tight_layout(rect=[0, 0.07, 1, 1])
fig.savefig(FIGS / "fig1_coupling_graphs.png", dpi=160)
plt.close(fig)

# fig 2: edge-correlation adjacency heatmaps, emu vs qpu + delta, both targets
fig, axes = plt.subplots(2, 3, figsize=(12, 8))
for row, (name, t) in enumerate(TARGETS):
    core = cores[t]
    n = core["n_nodes"]
    Me = np.zeros((n, n))
    Mq = np.zeros((n, n))
    for a, b in core["edges"]:
        ce = corr_norm(res[t]["emu"], (a, b))
        cq = corr_norm(res[t]["qpu"], (a, b))
        Me[a, b] = Me[b, a] = ce
        Mq[a, b] = Mq[b, a] = cq
    vmax = np.nanmax([Me, Mq])
    dmax = np.nanmax(np.abs(Mq - Me))
    for ax, M, ttl, cmap, vmin, v in [
        (axes[row, 0], Me, "emulator", "viridis", 0, vmax),
        (axes[row, 1], Mq, "ibm_fez (QPU)", "viridis", 0, vmax),
        (axes[row, 2], Mq - Me, "QPU − emu", "RdBu_r", -dmax, dmax),
    ]:
        im = ax.imshow(M, cmap=cmap, vmin=vmin, vmax=v)
        ax.set_title(f"{name} — {ttl}", fontsize=10)
        ax.set_xticks(range(0, n, 5))
        ax.set_yticks(range(0, n, 5))
        fig.colorbar(im, ax=ax, fraction=0.046)
fig.suptitle("two-qubit correlation |vector| per graph edge", fontsize=12)
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(FIGS / "fig2_edge_correlations.png", dpi=160)
plt.close(fig)

# fig 3: per-qubit Bloch |r|, emu vs qpu, both targets
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
for ax, (name, t) in zip(axes, TARGETS):
    x = np.arange(20)
    ax.bar(x - 0.2, bloch_r(t, "emu"), width=0.4, label="emulator", color=EMU_C)
    ax.bar(x + 0.2, bloch_r(t, "qpu"), width=0.4, label="ibm_fez", color=QPU_C)
    ax.axhline(0, color="#888", lw=0.5)
    ax.set_title(f"{name} — single-qubit Bloch |r|", fontsize=10)
    ax.set_xlabel("qubit")
    ax.set_xticks(range(0, 20, 2))
    if ax is axes[0]:
        ax.set_ylabel("|r|")
        ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(FIGS / "fig3_bloch_magnitudes.png", dpi=160)
plt.close(fig)

# fig 4: real-vs-control summary
ctrl_graph = json.load(open(BASE / "metrics/graphs/ctrl_graph.json"))
ctrl_edges = [tuple(e) for e in ctrl_graph["control_edges"]]
edge_sets = {
    "kras": [tuple(e) for e in cores["kras"]["edges"]],
    "myosin": [tuple(e) for e in cores["myosin"]["edges"]],
    "ctrl": ctrl_edges,
}
fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))
labels = ["KRAS", "myosin", "random ctrl"]
emu_c = [np.mean([corr_norm(res[t]["emu"], e) for e in edge_sets[t]]) for t in edge_sets]
qpu_c = [np.mean([corr_norm(res[t]["qpu"], e) for e in edge_sets[t]]) for t in edge_sets]
agree_e = [res[t]["emu"]["edge_agreement_score"] for t in edge_sets]
agree_q = [res[t]["qpu"]["edge_agreement_score"] for t in edge_sets]
x = np.arange(3)
for ax, (ye, yq), ttl, ylab in [
    (axes[0], (emu_c, qpu_c), "edge correlation magnitude", "mean edge |corr|"),
    (axes[1], (agree_e, agree_q), "engine edge-agreement", "edge agreement score"),
]:
    ax.bar(x - 0.2, ye, width=0.4, label="emulator", color=EMU_C)
    ax.bar(x + 0.2, yq, width=0.4, label="ibm_fez", color=QPU_C)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylab)
    ax.set_title(ttl)
axes[0].legend(frameon=False)
fig.tight_layout()
fig.savefig(FIGS / "fig4_real_vs_control.png", dpi=160)
plt.close(fig)

print("figs:", sorted(p.name for p in FIGS.glob("*.png")))
