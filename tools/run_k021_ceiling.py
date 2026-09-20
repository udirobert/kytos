"""Kytos k021 — ceiling / attribution analysis on the 2025 Atlas validation set.

Locates the bottleneck that keeps us off the 2026 top-100: is the remaining
score gap *signature*-limited (we can't recover the true per-target delta from
any public corpus) or *modeling*-limited (even a perfect delta loses score in
our mean-only count generator, so the win is in per-cell covariance / Layer B)?

Three arms, all scored on the SAME eval targets (real validation targets that
also have a K562 GWPS source delta) and the SAME control templates:

  identity_ds1p7  -- champion-proxy signature: borrowed K562 delta x 1.7,
                     dual-moment count generator. What we ship today, offline.
  true_ds1p0      -- PERFECT signature: the true per-target log1p mean-shift
                     measured from the held-out validation cells themselves,
                     pushed through the SAME generator at scale 1.0.
  ceiling         -- real-vs-real cell-eval ceiling: the real perturbed cells
                     themselves (full covariance, perfect everything).

Attribution:
  identity -> true   = headroom recoverable by a better SIGNATURE at fixed pipeline
  true     -> ceiling = headroom recoverable by better COUNT MODELING at fixed delta

If (true -> ceiling) >> (identity -> true), the gap is modeling/Layer-B and a
per-cell generative model is where the top-100 points live. Otherwise we are
corpus-limited and polish-only (accept the champion near its ceiling).

No submission is produced.

Run (inside the Modal container; see tools/modal_k021_ceiling.py):
  python tools/run_k021_ceiling.py \
    --val-h5ad /root/atlas/adata_Validation.h5ad \
    --paired-npz /root/paired/paired_transfer_train.npz \
    --outdir /root/kytos/experiments/k021-ceiling
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from kytos.models.dual_moment import build_prediction_dual_moment  # noqa: E402

PERT_COL = "target_gene"
CONTROL_LABEL = "non-targeting"
IDENTITY_SCALE = 1.7


def map_vector(vec: np.ndarray, src_genes: list[str], dst_index: dict[str, int]) -> np.ndarray:
    out = np.zeros(len(dst_index), dtype=np.float32)
    for g, v in zip(src_genes, vec):
        j = dst_index.get(g)
        if j is not None:
            out[j] = v
    return out


def _row_mean(x, mask: np.ndarray) -> np.ndarray:
    """Mean of the rows selected by boolean mask, dense 1-D (sparse-safe)."""
    sub = x[mask]
    return np.asarray(sub.mean(axis=0)).ravel()


def _finite(v):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--val-h5ad", type=Path, required=True)
    ap.add_argument("--paired-npz", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--cells-per-target", type=int, default=400)
    ap.add_argument("--control-cells", type=int, default=4000)
    ap.add_argument("--max-targets", type=int, default=0, help="0 = all paired targets")
    ap.add_argument("--profile", default="minimal", choices=["full", "minimal", "vcc", "pds"])
    ap.add_argument("--num-threads", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pool-k", type=int, default=4)
    ap.add_argument("--keep-pred", action="store_true", help="keep prediction h5ads")
    args = ap.parse_args(argv)

    t0 = time.time()
    args.outdir.mkdir(parents=True, exist_ok=True)

    # ---- Load real validation data -------------------------------------
    print(f"[real] loading {args.val_h5ad} ...", flush=True)
    real = ad.read_h5ad(str(args.val_h5ad))
    if not sparse.isspmatrix_csr(real.X):
        real.X = real.X.tocsr()
    gene_order = [str(g) for g in real.var_names]
    gene_index = {g: i for i, g in enumerate(gene_order)}
    labels = real.obs[PERT_COL].astype(str).to_numpy()
    real_targets = sorted({t for t in labels if t != CONTROL_LABEL})
    n_ctrl = int((labels == CONTROL_LABEL).sum())
    print(f"[real] {real.shape}, {len(real_targets)} targets, {n_ctrl} controls", flush=True)

    # ---- Source deltas (Replogle K562) -> define the eval target set ----
    paired = np.load(str(args.paired_npz), allow_pickle=True)
    paired_genes = [str(g) for g in paired["genes"]]
    paired_targets = [str(t).strip().upper() for t in paired["paired_targets"]]
    src_by_target: dict[str, np.ndarray] = {}
    for t, row in zip(paired_targets, paired["delta_k562"].astype(np.float32)):
        src_by_target[t] = map_vector(row, paired_genes, gene_index)
    print(f"[paired] {len(src_by_target)} K562 source deltas mapped", flush=True)

    eval_targets = [t for t in real_targets if t.strip().upper() in src_by_target]
    if args.max_targets:
        eval_targets = eval_targets[: args.max_targets]
    dropped = sorted(set(real_targets) - set(eval_targets))
    print(
        f"[targets] evaluating {len(eval_targets)}; dropped {len(dropped)}: {dropped}", flush=True
    )
    if not eval_targets:
        print("no evaluable targets", file=sys.stderr)
        return 2

    keep = np.isin(labels, eval_targets) | (labels == CONTROL_LABEL)
    real_sub = real[keep].copy()
    print(f"[real] subset to {real_sub.shape}", flush=True)

    # ---- Control cells for count generation ----------------------------
    ctrl_pos = np.flatnonzero(labels == CONTROL_LABEL)
    rng = np.random.default_rng(args.seed)
    n_ctrl_use = min(args.control_cells, len(ctrl_pos))
    ctrl_choice = rng.choice(ctrl_pos, size=n_ctrl_use, replace=False)
    control_adata = real[ctrl_choice].copy()
    lib = np.asarray(control_adata.X.sum(axis=1)).ravel()
    control_adata = control_adata[lib > 0].copy()
    print(f"[control] using {control_adata.shape[0]} control cells as template", flush=True)

    # ---- Real DE (computed once, reused across arms) --------------------
    import scanpy as sc
    from pdex import pdex

    print("[de] norm-log converting real subset ...", flush=True)
    real_eval = real_sub.copy()
    sc.pp.normalize_total(real_eval, inplace=True)
    sc.pp.log1p(real_eval)
    real_de_path = args.outdir / "real_de.csv"
    print(
        f"[de] running pdex on real ({real_eval.shape}, {args.num_threads} threads) ...", flush=True
    )
    t_de = time.time()
    real_de = pdex(
        adata=real_eval,
        mode="ref",
        reference=CONTROL_LABEL,
        groupby=PERT_COL,
        threads=args.num_threads,
        is_log1p=True,
        epsilon=0.0,
        cpm_filter=None,
    )
    real_de.write_csv(str(real_de_path))
    print(f"[de] real DE done in {time.time() - t_de:.1f}s ({len(real_de)} rows)", flush=True)

    # ---- Build the two signature arms ----------------------------------
    # true per-target delta = mean log1p(pert) - mean log1p(ctrl), in gene order.
    ev_labels = real_eval.obs[PERT_COL].astype(str).to_numpy()
    ctrl_mean = _row_mean(real_eval.X, ev_labels == CONTROL_LABEL)
    true_deltas: dict[str, np.ndarray] = {}
    for tgt in eval_targets:
        pm = _row_mean(real_eval.X, ev_labels == tgt)
        true_deltas[tgt] = (pm - ctrl_mean).astype(np.float32)

    identity_deltas: dict[str, np.ndarray] = {}
    for tgt in eval_targets:
        identity_deltas[tgt] = (src_by_target[tgt.strip().upper()] * IDENTITY_SCALE).astype(
            np.float32
        )

    # How well does the borrowed signature match the true one? (delta-level, cheap sanity)
    def _cos(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        return float(a @ b / (na * nb)) if na > 0 and nb > 0 else 0.0

    id_true_cos = float(np.mean([_cos(identity_deltas[t], true_deltas[t]) for t in eval_targets]))
    print(f"[sanity] mean cos(identity_ds1p7, true) = {id_true_cos:.3f}", flush=True)

    # ---- Generate + evaluate each arm ----------------------------------
    from cell_eval import MetricsEvaluator

    summary: dict = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_eval_targets": len(eval_targets),
        "dropped_targets": dropped,
        "cells_per_target": args.cells_per_target,
        "control_cells": int(control_adata.shape[0]),
        "identity_scale": IDENTITY_SCALE,
        "mean_cos_identity_vs_true": round(id_true_cos, 4),
        "profile": args.profile,
        "arms": {},
    }

    arms = {
        "identity_ds1p7": identity_deltas,
        "true_ds1p0": true_deltas,
    }
    for name, deltas in arms.items():
        print(f"\n=== arm {name} ===", flush=True)
        t_c = time.time()
        X_pred = build_prediction_dual_moment(
            control_adata,
            deltas,
            eval_targets,
            gene_order,
            cells_per_target=args.cells_per_target,
            amplitude=1.0,
            bulk_amplitude=1.0,
            pool_k=args.pool_k,
            seed=args.seed,
        )
        print(
            f"[gen] {X_pred.shape} pert cells in {time.time() - t_c:.1f}s "
            f"(nnz {X_pred.nnz / 1e6:.1f}M)",
            flush=True,
        )

        obs_rows = [CONTROL_LABEL] * control_adata.shape[0]
        for tgt in eval_targets:
            obs_rows.extend([tgt] * args.cells_per_target)
        X_full = sparse.vstack([sparse.csr_matrix(control_adata.X), X_pred], format="csr")
        obs_index = [f"pred_{i}" for i in range(len(obs_rows))]
        pred = ad.AnnData(
            X=X_full,
            obs=pd.DataFrame({PERT_COL: obs_rows}, index=obs_index),
            var=real_sub.var.copy(),
        )
        pred.obs[PERT_COL] = pred.obs[PERT_COL].astype("category")

        cand_dir = args.outdir / name
        cand_dir.mkdir(parents=True, exist_ok=True)
        if args.keep_pred:
            pred.write_h5ad(str(cand_dir / "prediction.h5ad"), compression="gzip")

        t_e = time.time()
        evaluator = MetricsEvaluator(
            adata_pred=pred,
            adata_real=real_eval,
            de_real=str(real_de_path),
            control_pert=CONTROL_LABEL,
            pert_col=PERT_COL,
            num_threads=args.num_threads,
            outdir=str(cand_dir),
        )
        results, agg = evaluator.compute(profile=args.profile, basename="results.csv")
        agg_pd = agg.to_pandas().set_index("statistic")
        agg_dict = agg_pd.loc["mean"].to_dict() if "mean" in agg_pd.index else {}

        summary["arms"][name] = {
            "agg": {k: _finite(v) for k, v in agg_dict.items()},
            "gen_plus_eval_s": round(time.time() - t_c, 1),
            "eval_s": round(time.time() - t_e, 1),
        }
        print(f"[eval] {name}: {json.dumps(summary['arms'][name]['agg'])}", flush=True)

    # ---- Real-vs-real ceiling ------------------------------------------
    print("\n=== real-data ceiling ===", flush=True)
    ceiling_dir = args.outdir / "ceiling"
    ceiling_dir.mkdir(parents=True, exist_ok=True)
    evaluator = MetricsEvaluator(
        adata_pred=None,
        adata_real=real_eval,
        control_pert=CONTROL_LABEL,
        pert_col=PERT_COL,
        num_threads=args.num_threads,
        outdir=str(ceiling_dir),
    )
    evaluator.compute_ceiling(profile=args.profile, basename="ceiling_results.csv")
    ceil_path = ceiling_dir / "agg_ceiling_results.csv"
    if ceil_path.exists():
        # agg_ceiling_results.csv is a single WIDE row: one column per metric.
        # Non-reliability metrics (mae/mse/counts/clustering_agreement/...) carry
        # no defensible ceiling and are emitted as NaN -> drop them.
        ceil = pd.read_csv(ceil_path)
        summary["ceiling"] = {}
        if len(ceil):
            row = ceil.iloc[0].to_dict()
            for m, v in row.items():
                fv = _finite(v)
                if fv is not None:
                    summary["ceiling"][str(m)] = fv

    # ---- Attribution table ---------------------------------------------
    # Direction-robust: for each metric normalise by the full identity->ceiling
    # span. sig_frac = how much of that span the true signature closes; mod_frac
    # = the residual (true->ceiling) = count-modeling loss. Both live in ~[0,1]
    # regardless of whether the metric is higher- or lower-is-better, so they can
    # be averaged across metrics without the sign mixing raw diffs would cause.
    metric_keys = sorted(
        set(summary["arms"]["identity_ds1p7"]["agg"])
        & set(summary["arms"]["true_ds1p0"]["agg"])
        & set(summary.get("ceiling", {}))
    )
    EPS = 1e-9
    attribution: dict = {}
    sig_fracs: list[float] = []
    mod_fracs: list[float] = []
    for k in metric_keys:
        ident = summary["arms"]["identity_ds1p7"]["agg"][k]
        truev = summary["arms"]["true_ds1p0"]["agg"][k]
        ceil = summary["ceiling"][k]
        if None in (ident, truev, ceil):
            continue
        span = ceil - ident
        entry = {
            "identity": round(ident, 4),
            "true": round(truev, 4),
            "ceiling": round(ceil, 4),
            "signature_headroom": round(truev - ident, 4),
            "modeling_headroom": round(ceil - truev, 4),
        }
        if abs(span) < EPS:
            entry["sig_frac"] = None  # no gap between identity and ceiling
            entry["mod_frac"] = None
        else:
            sig_frac = (truev - ident) / span
            entry["sig_frac"] = round(sig_frac, 4)
            entry["mod_frac"] = round(1.0 - sig_frac, 4)
            sig_fracs.append(sig_frac)
            mod_fracs.append(1.0 - sig_frac)
        attribution[k] = entry
    summary["attribution"] = attribution

    mean_sig = float(np.mean(sig_fracs)) if sig_fracs else float("nan")
    mean_mod = float(np.mean(mod_fracs)) if mod_fracs else float("nan")
    summary["headroom_totals"] = {
        "n_metrics": len(sig_fracs),
        "mean_signature_frac": round(mean_sig, 4) if sig_fracs else None,
        "mean_modeling_frac": round(mean_mod, 4) if mod_fracs else None,
        "verdict": (
            "modeling-limited: even a perfect delta stays far below the ceiling "
            "-> per-cell covariance / Layer B is the top-100 lever"
            if mean_mod > mean_sig
            else "signature-limited: a perfect delta nearly reaches the ceiling "
            "-> our count pipeline is faithful; corpus coverage caps us (polish-only)"
        ),
    }

    summary["elapsed_s"] = round(time.time() - t0, 1)
    out = args.outdir / "summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\n[done] wrote {out}; total {summary['elapsed_s']}s", flush=True)
    print(json.dumps(summary["attribution"], indent=2), flush=True)
    print(json.dumps(summary["headroom_totals"], indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
