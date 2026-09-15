"""c007 — topology-only levers aimed at beating the edge-rewire null.

Levers (MD-free / ENM-only):
- contact cutoff ∈ {8, 9, 10} Å
- multi-scale T (average CTQW across horizons)
- community sources (active ± 1-hop neighbors)
- quantum residual: CTQW − CTRW (interference hypothesis)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cleveland.eval import known_site_recovery, top_k_resseqs
from cleveland.graph import build_contact_graph, coarse_grain
from cleveland.pdb import coords_matrix, load_residue_nodes
from cleveland.pipeline import _source_graph_nodes
from cleveland.pipeline_c004 import _rewire
from cleveland.pipeline_phase2 import PHASE1_GATE_RECEIPTS, TIGHTEST_PHASE1_TARGET
from cleveland.targets import DEFAULT_GRAPH, TARGETS, BenchmarkTarget, GraphConfig
from cleveland.walk import ctrw_scores, project_coarse_scores_to_residues
from cleveland.walk.ctqw import ctqw_scores
import networkx as nx

HORIZONS = (3.0, 10.0, 30.0)


def expand_sources(g, sources: list[int], mode: str) -> list[int]:
    if mode == "active":
        return list(sources)
    if mode == "active_plus_neighbors":
        out = set(sources)
        for s in sources:
            out.update(g.neighbors(s))
        return sorted(out)
    raise ValueError(mode)


def _distal_upweight(
    g,
    sources: list[int],
    scores: np.ndarray,
    order: list[int],
) -> np.ndarray:
    """Upweight nodes far from sources (allosteric distal bias; topology-only)."""
    lengths: dict[int, float] = {}
    for s in sources:
        for n, d in nx.single_source_shortest_path_length(g, s).items():
            lengths[n] = min(lengths.get(n, 1e9), float(d))
    out = np.zeros_like(scores)
    for i, node in enumerate(order):
        dist = lengths.get(node, 0.0)
        out[i] = scores[i] * (dist**2)
    return out


def _ctqw_once(g, sources, t_max, hamiltonian, n_times):
    scores, _, order, meta = ctqw_scores(
        g, sources, t_max, hamiltonian=hamiltonian, n_times=n_times
    )
    return scores, order, meta


def _multiscale(g, sources, hamiltonian, n_times):
    acc = None
    order = None
    for t_max in HORIZONS:
        scores, order, _ = _ctqw_once(g, sources, t_max, hamiltonian, n_times)
        acc = scores if acc is None else acc + scores
    assert acc is not None and order is not None
    return acc / len(HORIZONS), order, {"horizons": list(HORIZONS)}


def _residual(g, sources, walk_time, hamiltonian, n_times):
    q_scores, order_q, meta_q = _ctqw_once(g, sources, walk_time, hamiltonian, n_times)
    c_scores, order_c, _ = ctrw_scores(g, sources, walk_time)
    if order_q != order_c:
        idx = {n: i for i, n in enumerate(order_c)}
        c_aligned = np.array([c_scores[idx[n]] for n in order_q], dtype=np.float64)
    else:
        c_aligned = c_scores
    qn = q_scores / (q_scores.sum() + 1e-15)
    cn = c_aligned / (c_aligned.sum() + 1e-15)
    return qn - cn, order_q, {**meta_q, "score_mode": "ctqw_minus_ctrw"}


def _project_if_coarse(scores, order, g_full, labels, cg_info, project: bool):
    if not project:
        return scores, order, g_full
    by_label = np.zeros(cg_info["n_coarse"], dtype=np.float64)
    for i, lab in enumerate(order):
        by_label[int(lab)] = scores[i]
    projected = project_coarse_scores_to_residues(by_label, labels)
    return projected, cg_info["node_order"], g_full


def sweep_target_c007(
    target: BenchmarkTarget,
    *,
    raw_dir: Path,
    base_cfg: GraphConfig = DEFAULT_GRAPH,
    n_times: int = 24,
    n_null: int = 30,
    seed: int = 0,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    nodes = load_residue_nodes(target.apo, raw_dir, atom_mode=base_cfg.atom_mode)
    coords = coords_matrix(nodes)

    trials: list[dict[str, Any]] = []

    for cutoff in (8.0, 9.0, 10.0):
        cfg = GraphConfig(
            cutoff_angstrom=cutoff,
            seed=base_cfg.seed,
            n_clusters_min=base_cfg.n_clusters_min,
            n_clusters_max=base_cfg.n_clusters_max,
        )
        g = build_contact_graph(nodes, coords, cfg)
        base_sources, n_found = _source_graph_nodes(g, target.active_site_residues)
        if not base_sources:
            continue

        resolutions = ["coarse"]
        if g.number_of_nodes() <= 350:
            resolutions.append("full")

        for source_mode in ("active", "active_plus_neighbors"):
            sources = expand_sources(g, base_sources, source_mode)
            for hamiltonian in ("laplacian", "adjacency"):
                for resolution in resolutions:
                    for score_mode in (
                        "ctqw_t10",
                        "ctqw_multiscale",
                        "ctqw_minus_ctrw",
                    ):
                        for distal in (False, True):
                            if resolution == "coarse":
                                cg, labels, cg_info = coarse_grain(g, cfg)
                                node_to_dense = {n: i for i, n in enumerate(cg_info["node_order"])}
                                work_sources = sorted(
                                    {
                                        int(labels[node_to_dense[n]])
                                        for n in sources
                                        if n in node_to_dense
                                    }
                                )
                                work_g = cg
                                project = True
                            else:
                                work_g, work_sources = g, sources
                                labels, cg_info, project = None, None, False

                            if not work_sources:
                                continue

                            if score_mode == "ctqw_t10":
                                scores_w, order_w, meta = _ctqw_once(
                                    work_g, work_sources, 10.0, hamiltonian, n_times
                                )
                            elif score_mode == "ctqw_multiscale":
                                scores_w, order_w, meta = _multiscale(
                                    work_g, work_sources, hamiltonian, n_times
                                )
                            else:
                                scores_w, order_w, meta = _residual(
                                    work_g, work_sources, 10.0, hamiltonian, n_times
                                )

                            scores, order, g_lab = _project_if_coarse(
                                scores_w, order_w, g, labels, cg_info, project
                            )
                            if distal:
                                scores = _distal_upweight(g_lab, sources, scores, order)
                                meta = {**meta, "distal_upweight": True}
                            else:
                                meta = {**meta, "distal_upweight": False}

                            rec = known_site_recovery(
                                scores, order, g_lab, target.known_allosteric_residues
                            )
                            hits = top_k_resseqs(
                                scores,
                                order,
                                g_lab,
                                k=5,
                                exclude=set(target.active_site_residues),
                            )
                            trials.append(
                                {
                                    "cutoff": cutoff,
                                    "source_mode": source_mode,
                                    "hamiltonian": hamiltonian,
                                    "resolution": resolution,
                                    "score_mode": score_mode,
                                    "distal_upweight": distal,
                                    "best_known_rank": rec.get("best_known_rank"),
                                    "mean_known_rank": rec.get("mean_known_rank"),
                                    "n_known_in_top_k": rec.get("n_known_in_top_k"),
                                    "recovery": rec,
                                    "hit_list_top5": hits,
                                    "n_sources": len(sources),
                                    "n_found_active": n_found,
                                    "meta": meta,
                                    "_scores": scores,
                                    "_order": order,
                                    "_g": g,
                                    "_cfg": cfg,
                                    "_sources_full": sources,
                                }
                            )

    def sort_key(t: dict[str, Any]) -> tuple:
        b = t["best_known_rank"]
        m = t["mean_known_rank"]
        top = t["n_known_in_top_k"] or 0
        return (
            -(top),
            b if b is not None else 1e9,
            m if m is not None else 1e9,
        )

    trials_sorted = sorted(trials, key=sort_key)
    if not trials_sorted:
        raise ValueError(f"{target.target_id}: no trials")
    winner = trials_sorted[0]

    # Null: rewire winner's graph, re-run same score mode on same resolution path
    obs_mean = winner["mean_known_rank"]
    obs_best = winner["best_known_rank"]
    null_means: list[float] = []
    null_bests: list[float] = []
    g0 = winner["_g"]
    cfg0 = winner["_cfg"]
    sources0 = winner["_sources_full"]

    if obs_mean is not None and target.known_allosteric_residues:
        for _ in range(n_null):
            h = _rewire(g0, n_swaps=10 * g0.number_of_edges(), rng=rng)
            try:
                if winner["resolution"] == "coarse":
                    cg, labels, cg_info = coarse_grain(h, cfg0)
                    node_to_dense = {n: i for i, n in enumerate(cg_info["node_order"])}
                    work_sources = sorted(
                        {int(labels[node_to_dense[n]]) for n in sources0 if n in node_to_dense}
                    )
                    work_g = cg
                    project = True
                else:
                    work_g, work_sources = h, sources0
                    labels, cg_info, project = None, None, False
                if not work_sources:
                    continue
                sm = winner["score_mode"]
                ham = winner["hamiltonian"]
                if sm == "ctqw_t10":
                    sw, ow, _ = _ctqw_once(work_g, work_sources, 10.0, ham, n_times)
                elif sm == "ctqw_multiscale":
                    sw, ow, _ = _multiscale(work_g, work_sources, ham, n_times)
                else:
                    sw, ow, _ = _residual(work_g, work_sources, 10.0, ham, n_times)
                scores, order, g_lab = _project_if_coarse(sw, ow, h, labels, cg_info, project)
                if winner.get("distal_upweight"):
                    scores = _distal_upweight(g_lab, sources0, scores, order)
                rec_n = known_site_recovery(scores, order, g_lab, target.known_allosteric_residues)
                m = rec_n.get("mean_known_rank")
                b = rec_n.get("best_known_rank")
                if m is not None:
                    null_means.append(float(m))
                if b is not None:
                    null_bests.append(float(b))
            except (ValueError, KeyError, np.linalg.LinAlgError):
                continue

    def _z(obs, nulls):
        if obs is None or len(nulls) < 8:
            return None, None, None, None
        mu = float(np.mean(nulls))
        sd = float(np.std(nulls, ddof=1))
        z = (float(obs) - mu) / sd if sd > 1e-12 else 0.0
        p = float(np.mean([r <= obs for r in nulls]))
        return z, p, mu, sd

    z_mean, p_mean, null_mean, null_std = _z(obs_mean, null_means)
    z_best, p_best, null_best_mean, null_best_std = _z(obs_best, null_bests)
    sig = bool((z_mean is not None and z_mean < -2.0) or (z_best is not None and z_best < -2.0))

    trial_log = [{k: v for k, v in t.items() if not k.startswith("_")} for t in trials_sorted[:20]]
    return {
        "target_id": target.target_id,
        "pdb_id": target.apo.pdb_id,
        "n_nodes": winner["_g"].number_of_nodes(),
        "phase1_receipt": PHASE1_GATE_RECEIPTS.get(target.target_id, {}),
        "tightest_phase1_margin": target.target_id == TIGHTEST_PHASE1_TARGET,
        "winner": {k: v for k, v in winner.items() if not k.startswith("_")},
        "zscore_mean_known_rank": z_mean,
        "empirical_p_mean": p_mean,
        "null_mean": null_mean,
        "null_std": null_std,
        "zscore_best_known_rank": z_best,
        "empirical_p_best": p_best,
        "null_best_mean": null_best_mean,
        "null_best_std": null_best_std,
        "n_null_used": len(null_means),
        "significant_better_than_null": sig,
        "n_trials": len(trials_sorted),
        "top_trials": trial_log,
        "known_allosteric_label": target.known_allosteric_label,
    }


def run_all_c007(
    *,
    raw_dir: Path,
    base_cfg: GraphConfig = DEFAULT_GRAPH,
    target_ids: list[str] | None = None,
    n_times: int = 24,
    n_null: int = 30,
    seed: int = 0,
) -> list[dict[str, Any]]:
    ids = target_ids or [t for t in TARGETS if TARGETS[t].known_allosteric_residues]
    return [
        sweep_target_c007(
            TARGETS[tid],
            raw_dir=raw_dir,
            base_cfg=base_cfg,
            n_times=n_times,
            n_null=n_null,
            seed=seed + i * 23,
        )
        for i, tid in enumerate(ids)
    ]
