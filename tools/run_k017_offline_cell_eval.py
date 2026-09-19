"""Kytos k017 — offline cell-eval validation harness on the 2025 H1 validation set.

Builds COUNT-LEVEL predictions for the held-out 2025 H1 validation targets and
scores them with cell-eval against the real validation h5ad. No submission is
produced; this is the gate before any leaderboard upload.

Pipeline per candidate:
  1. Source deltas: Replogle K562 (paired_transfer_train.npz) mapped to the
     validation gene order.
  2. Optional transfer: rank-64 low-rank map trained on 136 H1-2025 training
     pairs (h1_train_deltas.npz x delta_matrix_src.npz), plus self-gene reset
     to the training self-effect median.
  3. delta_scale multiplier (champion axis from k011).
  4. Count generation via the dual-moment generator
     (kytos.models.dual_moment.build_prediction_dual_moment), templated on
     sampled real control cells.
  5. cell-eval MetricsEvaluator (real DE computed once and reused).

Candidate names (registry):
  identity_ds{1p0,1p3,1p7,2p0}
  h1lr64_ds{1p0,1p3,1p7,2p0}_selfTrain        (non-self scaled, self = train median)
  h1lr64_ds{1p0,1p3,1p7,2p0}_selfTrainScaled  (self = train median x scale)

Run (inside the Modal container; see tools/modal_k017_offline_cell_eval.py):
  python tools/run_k017_offline_cell_eval.py \
    --val-h5ad /root/atlas/adata_Validation.h5ad \
    --paired-npz /root/paired/paired_transfer_train.npz \
    --h1-npz /root/h1train/h1_train_deltas.npz \
    --src-matrix /root/paired/delta_matrix_src.npz \
    --outdir /root/kytos/experiments/k017-offline-cell-eval \
    --candidates identity_ds1p7,h1lr64_ds1p7_selfTrain,h1lr64_ds2p0_selfTrainScaled
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
SCALES = {"1p0": 1.0, "1p3": 1.3, "1p7": 1.7, "2p0": 2.0}


def parse_candidate(name: str) -> dict:
    """Parse a registry candidate name into its config."""
    spec: dict = {"name": name, "amplitude": 1.0, "bulk_amplitude": 1.0}
    base = name
    for suffix in ("_ampdef",):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            spec["amplitude"] = 0.6
            spec["bulk_amplitude"] = 0.3
    parts = base.split("_")
    if parts[0] == "identity":
        spec["transfer"] = "identity"
        spec["delta_scale"] = SCALES[parts[1][2:]]
        spec["self_mode"] = "none"
    elif parts[0] == "h1lr64":
        spec["transfer"] = "lowrank"
        spec["rank"] = 64
        spec["delta_scale"] = SCALES[parts[1][2:]]
        spec["self_mode"] = parts[2]  # selfTrain | selfTrainScaled
    else:
        raise ValueError(f"unknown candidate family: {name}")
    return spec


def map_vectors(mat: np.ndarray, src_genes: list[str], dst_genes: list[str]) -> np.ndarray:
    """Map columns of mat from src gene order to dst gene order (zeros for missing)."""
    src_idx = {g: i for i, g in enumerate(src_genes)}
    cols = np.array([src_idx.get(g, -1) for g in dst_genes], dtype=np.int64)
    valid = cols >= 0
    out = np.zeros((mat.shape[0], len(dst_genes)), dtype=np.float32)
    out[:, valid] = mat[:, cols[valid]]
    return out


def map_vector(vec: np.ndarray, src_genes: list[str], dst_index: dict[str, int]) -> np.ndarray:
    out = np.zeros(len(dst_index), dtype=np.float32)
    for g, v in zip(src_genes, vec):
        j = dst_index.get(g)
        if j is not None:
            out[j] = v
    return out


def fit_lowrank(X_train: np.ndarray, Y_train: np.ndarray, rank: int):
    """Uncentered rank-r transfer: project through top SVD bases of both sides."""
    rank = min(rank, max(1, X_train.shape[0] - 1))
    _, _, vt_x = np.linalg.svd(X_train.astype(np.float64), full_matrices=False)
    _, _, vt_y = np.linalg.svd(Y_train.astype(np.float64), full_matrices=False)
    bx = vt_x[:rank].astype(np.float32)
    by = vt_y[:rank].astype(np.float32)
    xp = X_train @ bx.T
    yp = Y_train @ by.T
    lam = max(1.0, 0.1 * float(np.trace(xp.T @ xp)) / max(rank, 1))
    w = np.linalg.solve(xp.T @ xp + lam * np.eye(rank, dtype=np.float32), xp.T @ yp)

    def transform(x: np.ndarray) -> np.ndarray:
        return ((x.astype(np.float32) @ bx.T) @ w) @ by

    return transform


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--val-h5ad", type=Path, required=True)
    ap.add_argument("--paired-npz", type=Path, required=True)
    ap.add_argument("--h1-npz", type=Path, required=True)
    ap.add_argument("--src-matrix", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument(
        "--candidates",
        default="identity_ds1p7,h1lr64_ds1p7_selfTrain,h1lr64_ds2p0_selfTrainScaled",
    )
    ap.add_argument("--cells-per-target", type=int, default=400)
    ap.add_argument("--control-cells", type=int, default=4000)
    ap.add_argument("--max-targets", type=int, default=0, help="0 = all paired targets")
    ap.add_argument("--profile", default="minimal", choices=["full", "minimal", "vcc", "pds"])
    ap.add_argument("--num-threads", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pool-k", type=int, default=4)
    ap.add_argument("--keep-pred", action="store_true", help="keep prediction h5ads")
    ap.add_argument("--ceiling", action="store_true", help="also compute the real-data ceiling")
    args = ap.parse_args(argv)

    t0 = time.time()
    args.outdir.mkdir(parents=True, exist_ok=True)
    candidates = [parse_candidate(c.strip()) for c in args.candidates.split(",") if c.strip()]

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

    # ---- Source deltas (Replogle K562) for the paired targets ----------
    paired = np.load(str(args.paired_npz), allow_pickle=True)
    paired_genes = [str(g) for g in paired["genes"]]
    paired_targets = [str(t).strip().upper() for t in paired["paired_targets"]]
    src_by_target: dict[str, np.ndarray] = {}
    for t, row in zip(paired_targets, paired["delta_k562"].astype(np.float32)):
        src_by_target[t] = map_vector(row, paired_genes, gene_index)
    print(f"[paired] {len(src_by_target)} K562 source deltas mapped", flush=True)

    # Evaluation target set: real targets that have a source delta.
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

    # ---- H1 low-rank transfer trained on the 2025 H1 training set ------
    h1 = np.load(str(args.h1_npz), allow_pickle=True)
    src = np.load(str(args.src_matrix), allow_pickle=True)
    h1_genes = [str(g) for g in h1["genes"]]
    h1_targets = [str(t).strip().upper() for t in h1["targets"]]
    src_targets = [str(t).strip().upper() for t in src["targets"]]
    src_target_idx = {t: i for i, t in enumerate(src_targets)}

    train_pairs = [(i, src_target_idx[t]) for i, t in enumerate(h1_targets) if t in src_target_idx]
    print(f"[train] {len(train_pairs)} H1 train pairs with source deltas", flush=True)
    X_train = map_vectors(
        np.stack([src["deltas"][si] for _, si in train_pairs]).astype(np.float32),
        paired_genes,
        gene_order,
    )
    Y_train = map_vectors(
        np.stack([h1["deltas"][hi] for hi, _ in train_pairs]).astype(np.float32),
        h1_genes,
        gene_order,
    )
    self_vals = []
    train_target_names = [h1_targets[hi] for hi, _ in train_pairs]
    for row, tgt in enumerate(train_target_names):
        j = gene_index.get(tgt)
        if j is not None:
            self_vals.append(float(Y_train[row, j]))
    self_median = float(np.median(self_vals)) if self_vals else -1.5
    print(f"[train] self-effect median (train only): {self_median:.3f}", flush=True)

    transform = fit_lowrank(X_train, Y_train, rank=64)

    # ---- Control cells for count generation ----------------------------
    ctrl_pos = np.flatnonzero(labels == CONTROL_LABEL)
    rng = np.random.default_rng(args.seed)
    n_ctrl_use = min(args.control_cells, len(ctrl_pos))
    ctrl_choice = rng.choice(ctrl_pos, size=n_ctrl_use, replace=False)
    control_adata = real[ctrl_choice].copy()
    lib = np.asarray(control_adata.X.sum(axis=1)).ravel()
    control_adata = control_adata[lib > 0].copy()
    print(f"[control] using {control_adata.shape[0]} control cells as template", flush=True)

    # ---- Real DE (computed once, reused across candidates) -------------
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

    # ---- Generate + evaluate each candidate ----------------------------
    from cell_eval import MetricsEvaluator

    summary: dict = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_eval_targets": len(eval_targets),
        "dropped_targets": dropped,
        "cells_per_target": args.cells_per_target,
        "control_cells": int(control_adata.shape[0]),
        "self_median_train": self_median,
        "profile": args.profile,
        "candidates": {},
    }

    for cand in candidates:
        name = cand["name"]
        scale = cand["delta_scale"]
        print(f"\n=== candidate {name} ===", flush=True)
        t_c = time.time()

        deltas: dict[str, np.ndarray] = {}
        for tgt in eval_targets:
            key = tgt.strip().upper()
            base = src_by_target[key]
            if cand["transfer"] == "identity":
                d = base * scale
            else:
                d = transform(base.reshape(1, -1))[0] * scale
                j = gene_index.get(key)
                if j is not None and cand["self_mode"] != "none":
                    self_val = self_median
                    if cand["self_mode"] == "selfTrainScaled":
                        self_val = self_median * scale
                    d[j] = self_val
            deltas[tgt] = d.astype(np.float32)

        X_pred = build_prediction_dual_moment(
            control_adata,
            deltas,
            eval_targets,
            gene_order,
            cells_per_target=args.cells_per_target,
            amplitude=cand["amplitude"],
            bulk_amplitude=cand["bulk_amplitude"],
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

        def _finite(v):
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        summary["candidates"][name] = {
            "agg": {k: _finite(v) for k, v in agg_dict.items()},
            "gen_plus_eval_s": round(time.time() - t_c, 1),
            "eval_s": round(time.time() - t_e, 1),
            "config": cand,
        }
        print(f"[eval] {name}: {json.dumps(summary['candidates'][name]['agg'])}", flush=True)

    if args.ceiling:
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
            ceil = pd.read_csv(ceil_path)
            summary["ceiling"] = dict(zip(ceil["metric"], ceil["ceiling"]))

    summary["elapsed_s"] = round(time.time() - t0, 1)
    out = args.outdir / "summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\n[done] wrote {out}; total {summary['elapsed_s']}s", flush=True)
    print(json.dumps({c: v["agg"] for c, v in summary["candidates"].items()}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
