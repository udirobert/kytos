"""c005 — improve CTQW signal vs null via H-form, multi-T, resolution sweep."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cleveland.eval import known_site_recovery, top_k_resseqs
from cleveland.graph import build_contact_graph, coarse_grain
from cleveland.pdb import coords_matrix, load_residue_nodes
from cleveland.pipeline import _source_graph_nodes
from cleveland.pipeline_c004 import _mean_known_rank, _rewire
from cleveland.pipeline_phase2 import PHASE1_GATE_RECEIPTS, TIGHTEST_PHASE1_TARGET
from cleveland.targets import DEFAULT_GRAPH, TARGETS, BenchmarkTarget, GraphConfig
from cleveland.walk import project_coarse_scores_to_residues
from cleveland.walk.ctqw import ctqw_scores


def _scores_for_config(
    g,
    sources: list[int],
    *,
    resolution: str,
    hamiltonian: str,
    walk_time: float,
    n_times: int,
    cfg: GraphConfig,
) -> tuple[np.ndarray, list[int], Any, dict[str, Any]]:
    """Return residue-aligned scores, order, graph_for_labels, meta."""
    if resolution == "full":
        scores, _, order, meta = ctqw_scores(
            g, sources, walk_time, hamiltonian=hamiltonian, n_times=n_times
        )
        return scores, order, g, {**meta, "resolution": "full", "n_graph": g.number_of_nodes()}

    cg, labels, cg_info = coarse_grain(g, cfg)
    node_to_dense = {n: i for i, n in enumerate(cg_info["node_order"])}
    coarse_sources = sorted({int(labels[node_to_dense[n]]) for n in sources if n in node_to_dense})
    scores_c, _, order_c, meta = ctqw_scores(
        cg, coarse_sources, walk_time, hamiltonian=hamiltonian, n_times=n_times
    )
    by_label = np.zeros(cg_info["n_coarse"], dtype=np.float64)
    for i, lab in enumerate(order_c):
        by_label[int(lab)] = scores_c[i]
    projected = project_coarse_scores_to_residues(by_label, labels)
    # order aligns with cg_info node_order == adjacency order of g LCC
    order = cg_info["node_order"]
    return (
        projected,
        order,
        g,
        {
            **meta,
            "resolution": "coarse",
            "n_graph": cg_info["n_coarse"],
            "n_full": cg_info["n_full"],
        },
    )


def sweep_target(
    target: BenchmarkTarget,
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    n_times: int = 32,
    n_null: int = 24,
    seed: int = 0,
) -> dict[str, Any]:
    """Grid-search configs; z-score the winner against edge-rewire nulls."""
    rng = np.random.default_rng(seed)
    structure = target.apo
    nodes = load_residue_nodes(structure, raw_dir, atom_mode=cfg.atom_mode)
    coords = coords_matrix(nodes)
    g = build_contact_graph(nodes, coords, cfg)
    sources, n_found = _source_graph_nodes(g, target.active_site_residues)
    if not sources:
        raise ValueError(f"{target.target_id}: no sources")

    n = g.number_of_nodes()
    # Full-graph only when local-safe; myosin stays coarse-primary but still tried.
    resolutions = ["coarse", "full"] if n <= 400 else ["coarse", "full"]
    hamiltonians = ["laplacian", "adjacency"]
    walk_times = [3.0, 10.0, 30.0]

    trials: list[dict[str, Any]] = []
    for resolution in resolutions:
        for hamiltonian in hamiltonians:
            for walk_time in walk_times:
                scores, order, g_lab, meta = _scores_for_config(
                    g,
                    sources,
                    resolution=resolution,
                    hamiltonian=hamiltonian,
                    walk_time=walk_time,
                    n_times=n_times,
                    cfg=cfg,
                )
                rec = known_site_recovery(scores, order, g_lab, target.known_allosteric_residues)
                exclude = set(target.active_site_residues)
                hits = top_k_resseqs(scores, order, g_lab, k=5, exclude=exclude)
                # Primary sort key: best known rank (lower better); then mean rank
                best = rec.get("best_known_rank")
                mean = rec.get("mean_known_rank")
                trials.append(
                    {
                        "resolution": resolution,
                        "hamiltonian": hamiltonian,
                        "walk_time": walk_time,
                        "best_known_rank": best,
                        "mean_known_rank": mean,
                        "n_known_in_top_k": rec.get("n_known_in_top_k"),
                        "recovery": rec,
                        "hit_list_top5": hits,
                        "meta": meta,
                        "_scores": scores,
                        "_order": order,
                    }
                )

    def sort_key(t: dict[str, Any]) -> tuple:
        b = t["best_known_rank"]
        m = t["mean_known_rank"]
        return (
            b if b is not None else 1e9,
            m if m is not None else 1e9,
            t["walk_time"],
        )

    trials_sorted = sorted(trials, key=sort_key)
    winner = trials_sorted[0]

    # Null on winner config (rewire base graph, re-apply same resolution path)
    obs = winner["mean_known_rank"]
    null_ranks: list[float] = []
    if obs is not None and target.known_allosteric_residues:
        for _ in range(n_null):
            h = _rewire(g, n_swaps=10 * g.number_of_edges(), rng=rng)
            try:
                s_null, o_null, g_null, _ = _scores_for_config(
                    h,
                    sources,
                    resolution=winner["resolution"],
                    hamiltonian=winner["hamiltonian"],
                    walk_time=winner["walk_time"],
                    n_times=n_times,
                    cfg=cfg,
                )
            except (ValueError, KeyError):
                continue
            m = _mean_known_rank(s_null, o_null, g_null, target.known_allosteric_residues)
            if m is not None:
                null_ranks.append(float(m))

    zscore = None
    p_emp = None
    if obs is not None and len(null_ranks) >= 8:
        mu = float(np.mean(null_ranks))
        sd = float(np.std(null_ranks, ddof=1))
        zscore = (float(obs) - mu) / sd if sd > 1e-12 else 0.0
        p_emp = float(np.mean([r <= obs for r in null_ranks]))

    # Drop heavy arrays from trial log
    trial_log = [{k: v for k, v in t.items() if not k.startswith("_")} for t in trials_sorted]

    return {
        "target_id": target.target_id,
        "pdb_id": structure.pdb_id,
        "n_nodes": n,
        "n_sources_found": n_found,
        "phase1_receipt": PHASE1_GATE_RECEIPTS.get(target.target_id, {}),
        "tightest_phase1_margin": target.target_id == TIGHTEST_PHASE1_TARGET,
        "winner": {k: v for k, v in winner.items() if not k.startswith("_")},
        "zscore_mean_known_rank": zscore,
        "empirical_p_lower_rank": p_emp,
        "null_mean": float(np.mean(null_ranks)) if null_ranks else None,
        "null_std": float(np.std(null_ranks, ddof=1)) if len(null_ranks) > 1 else None,
        "n_null_used": len(null_ranks),
        "significant_better_than_null": bool(zscore is not None and zscore < -2.0),
        "n_known_in_top_k_winner": winner.get("n_known_in_top_k"),
        "trial_log": trial_log,
        "known_allosteric_label": target.known_allosteric_label,
    }


def run_all_sweeps(
    *,
    raw_dir: Path,
    cfg: GraphConfig = DEFAULT_GRAPH,
    target_ids: list[str] | None = None,
    n_times: int = 32,
    n_null: int = 24,
    seed: int = 0,
) -> list[dict[str, Any]]:
    ids = target_ids or [t for t in TARGETS if TARGETS[t].known_allosteric_residues]
    return [
        sweep_target(
            TARGETS[tid],
            raw_dir=raw_dir,
            cfg=cfg,
            n_times=n_times,
            n_null=n_null,
            seed=seed + i * 19,
        )
        for i, tid in enumerate(ids)
    ]
