"""Extract a <=20-node functional core from a target's coarse contact graph.

Selection: active-site + known-allosteric-site supernodes, greedily extended
by strongest-coupled neighbors until the engine's 20-qubit cap is reached.

Run from repo root with .venv-cleveland:
    python reproduce/subgraph.py <target> <out.json>
e.g. python reproduce/subgraph.py kras_g12c metrics/graphs/kras_core.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from cleveland.graph import build_contact_graph, coarse_grain
from cleveland.pdb import coords_matrix, load_residue_nodes
from cleveland.targets import DEFAULT_GRAPH, TARGETS

MAX_NODES = 20


def main() -> None:
    target = sys.argv[1]
    out_path = sys.argv[2]
    raw = Path("data/cleveland/raw")
    t = TARGETS[target]

    nodes = load_residue_nodes(t.apo, raw, atom_mode=DEFAULT_GRAPH.atom_mode)
    coords = coords_matrix(nodes)
    g = build_contact_graph(nodes, coords, DEFAULT_GRAPH)
    cg, labels, info = coarse_grain(g, DEFAULT_GRAPH)
    order = info["node_order"]

    res2sn = {}
    for i, node_id in enumerate(order):
        data = g.nodes[node_id]
        res2sn[(data.get("chain"), data.get("resseq"))] = int(labels[i])

    def sns_for(resseqs: set[int]) -> set[int]:
        return {sn for (_, r), sn in res2sn.items() if r in resseqs}

    src_sns = sns_for(set(t.active_site_residues))
    known_sns = sns_for(set(t.known_allosteric_residues))
    print(f"coarse: {cg.number_of_nodes()} supernodes, {cg.number_of_edges()} edges")
    print(f"source supernodes: {sorted(src_sns)}")
    print(f"known-site supernodes: {sorted(known_sns)}")

    core = set(src_sns) | set(known_sns)
    while len(core) < MAX_NODES:
        best, bestw = None, 0
        for u in core:
            for v, d in cg[u].items():
                if v not in core and d.get("weight", 0) > bestw:
                    best, bestw = v, d["weight"]
        if best is None:
            break
        core.add(best)

    sub = cg.subgraph(sorted(core)).copy()
    reindex = {old: i for i, old in enumerate(sorted(core))}
    edges = [[reindex[u], reindex[v]] for u, v in sub.edges()]
    print(f"subgraph: {sub.number_of_nodes()} nodes, {sub.number_of_edges()} edges")

    node_map = {}
    for s in core:
        role = ("source" if s in src_sns else "") + ("known" if s in known_sns else "")
        node_map[reindex[s]] = {
            "supernode": s,
            "role": role,
            "residues": [g.nodes[n]["resseq"] for n in cg.nodes[s]["members"]],
        }

    json.dump(
        {"target": target, "n_nodes": sub.number_of_nodes(), "node_map": node_map, "edges": edges},
        open(out_path, "w"),
        indent=1,
    )
    print("roles:", {i: node_map[i]["role"] for i in sorted(node_map)})


if __name__ == "__main__":
    main()
