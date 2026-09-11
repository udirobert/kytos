"""Kytos k005 — 2025 Atlas perturbation prior + log1p transport.

Uses the VCC 2025 validation set (public Arc bucket) to learn per-target
perturbation signatures, then transfers them onto the 2026 control cells.

For each 2026 target:
  1. If the target was perturbed in the 2025 validation, use its real
     log1p mean-shift delta (target_perturbed_mean - control_mean).
  2. Otherwise, fall back to ContextConditionedTransfer (target knockdown).
  3. Sample real control cells and apply the delta in log1p space.

This is the first data-driven Layer A model for Kytos.
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

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from kytos.features.basal import extract_basal_context  # noqa: E402
from kytos.models.layer_a import ContextConditionedTransfer  # noqa: E402
from kytos.models.layer_b import AdditiveTransportSampler  # noqa: E402

PERT_COL = "target_gene"
CONTEXT_COL = "context"
CONTROL_LABEL = "non-targeting"


def log1p_sparse(X: sparse.spmatrix | np.ndarray) -> sparse.spmatrix | np.ndarray:
    if sparse.issparse(X):
        X_log = X.copy()
        X_log.data = np.log1p(X_log.data)
        return X_log
    return np.log1p(np.asarray(X))


def build_atlas_deltas(
    atlas_path: Path,
    context_genes: list[str],
) -> dict[str, np.ndarray]:
    """Compute per-target log1p mean-shift deltas from the 2025 validation set."""
    print(f"[atlas] loading {atlas_path} ...", flush=True)
    atlas = ad.read_h5ad(str(atlas_path))
    print(
        f"[atlas] loaded {atlas.shape[0]} cells x {atlas.shape[1]} genes; "
        f"obs cols: {list(atlas.obs.columns)}",
        flush=True,
    )
    if PERT_COL not in atlas.obs.columns:
        raise ValueError(f"{PERT_COL} not found in atlas.obs")

    X_log = log1p_sparse(atlas.X)
    atlas_genes = list(atlas.var.index)
    gene_index = {g: i for i, g in enumerate(atlas_genes)}

    obs = atlas.obs
    control_mask = obs[PERT_COL] == CONTROL_LABEL
    control_mean = np.asarray(X_log[control_mask].mean(axis=0)).ravel()

    targets = sorted({str(t) for t in obs.loc[~control_mask, PERT_COL].unique()})
    deltas: dict[str, np.ndarray] = {}
    for tgt in targets:
        tgt_mask = obs[PERT_COL] == tgt
        tgt_mean = np.asarray(X_log[tgt_mask].mean(axis=0)).ravel()
        delta = tgt_mean - control_mean

        # Map atlas delta onto the 2026 gene order.
        mapped = np.zeros(len(context_genes), dtype=np.float32)
        for i, g in enumerate(context_genes):
            idx = gene_index.get(g)
            if idx is not None:
                mapped[i] = delta[idx]
        deltas[tgt] = mapped

    print(f"[atlas] built deltas for {len(deltas)} targets", flush=True)
    return deltas


def build_context_predictions(
    context: str,
    control_path: Path,
    targets: list[str],
    gene_order: list[str],
    cells_per_pert: int,
    rng: np.random.Generator,
    atlas_deltas: dict[str, np.ndarray],
    fallback: ContextConditionedTransfer,
    sampler: AdditiveTransportSampler,
) -> tuple[sparse.csr_matrix, pd.DataFrame]:
    """Return a sparse prediction for one context using Atlas priors."""
    print(f"[{context}] loading {control_path.name} ...", flush=True)
    ctrl = ad.read_h5ad(str(control_path))
    X_ctrl = ctrl.X.tocsr() if not sparse.isspmatrix_csr(ctrl.X) else ctrl.X
    n_cells, n_genes = X_ctrl.shape
    assert n_genes == len(gene_order)

    basal = extract_basal_context(X_ctrl, gene_order)
    print(
        f"  basal: {n_cells} cells, mean nnz/cell {ctrl.X.nnz / ctrl.n_obs:.1f}",
        flush=True,
    )

    blocks: list[sparse.csr_matrix] = []
    obs_parts: list[pd.DataFrame] = []
    n_targets = len(targets)
    used_atlas = 0
    used_fallback = 0
    for i, tgt in enumerate(targets):
        if i % 50 == 0:
            print(f"  [{context}] {i}/{n_targets} {tgt}", flush=True)

        if tgt in atlas_deltas:
            delta = atlas_deltas[tgt]
            used_atlas += 1
        else:
            delta = fallback.predict_delta(tgt, basal)
            used_fallback += 1

        idx = rng.choice(n_cells, size=cells_per_pert, replace=True)
        basal_slice = X_ctrl[idx].todense().astype(np.float32)

        log_basal = np.log1p(basal_slice, out=np.empty_like(basal_slice))
        seed = int(rng.integers(0, 1_000_000))
        perturbed = sampler.sample_cells(
            log_basal, delta.astype(np.float32), n_samples=cells_per_pert, seed=seed
        )
        perturbed = np.expm1(perturbed)
        np.clip(perturbed, a_min=0.0, a_max=None, out=perturbed)
        perturbed = np.rint(perturbed).astype(np.float32)

        blocks.append(sparse.csr_matrix(perturbed))
        obs_parts.append(
            pd.DataFrame(
                {
                    PERT_COL: [tgt] * cells_per_pert,
                    CONTEXT_COL: [context] * cells_per_pert,
                }
            )
        )

    X_pred = sparse.vstack(blocks, format="csr")
    obs = pd.concat(obs_parts, ignore_index=True)
    print(
        f"  [{context}] built {X_pred.shape[0]} cells x {X_pred.shape[1]} genes, "
        f"nnz {X_pred.nnz:,} ({X_pred.nnz / (X_pred.shape[0] * X_pred.shape[1]):.3%} dense), "
        f"atlas={used_atlas} fallback={used_fallback}",
        flush=True,
    )
    return X_pred, obs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument(
        "--atlas-src",
        type=Path,
        default=REPO / "data" / "raw" / "vcc2025" / "adata_Validation.h5ad",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=REPO / "experiments" / "k005-atlas-prior-validation",
    )
    ap.add_argument("--contexts", default="A,B,C", help="comma-separated contexts")
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-targets", type=int, default=0, help="0 = all targets")
    ap.add_argument("--knockdown-efficiency", type=float, default=2.5)
    ap.add_argument("--attenuation-factor", type=float, default=0.5)
    ap.add_argument("--noise-scale", type=float, default=0.05)
    args = ap.parse_args(argv)

    raw_dir: Path = args.raw_dir
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_path = raw_dir / "gene_names.csv"
    if not gene_path.exists():
        print(f"missing {gene_path}; run `vcc datasets download controls`", file=sys.stderr)
        return 1

    gene_order = pd.read_csv(gene_path, header=None, skiprows=1)[0].tolist()
    all_targets = pd.read_csv(raw_dir / "pert_counts.csv", header=None, skiprows=1)[0].tolist()
    targets = all_targets[: args.max_targets] if args.max_targets else all_targets
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]

    if not args.atlas_src.exists():
        print(f"missing atlas source {args.atlas_src}", file=sys.stderr)
        return 2

    atlas_deltas = build_atlas_deltas(args.atlas_src, gene_order)

    rng = np.random.default_rng(args.seed)
    fallback = ContextConditionedTransfer(
        knockdown_efficiency=args.knockdown_efficiency,
        attenuation_factor=args.attenuation_factor,
    )
    sampler = AdditiveTransportSampler(noise_scale=args.noise_scale)

    t0 = time.time()
    ctx_blocks: list[sparse.csr_matrix] = []
    ctx_obs: list[pd.DataFrame] = []
    for ctx in contexts:
        ctrl_path = raw_dir / f"context_{ctx}.h5ad"
        if not ctrl_path.exists():
            print(f"missing {ctrl_path}", file=sys.stderr)
            return 3
        X_pred, obs = build_context_predictions(
            ctx,
            ctrl_path,
            targets,
            gene_order,
            args.cells_per_pert,
            rng,
            atlas_deltas,
            fallback,
            sampler,
        )
        ctx_blocks.append(X_pred)
        ctx_obs.append(obs)

    X = sparse.vstack(ctx_blocks, format="csr")
    obs = pd.concat(ctx_obs, ignore_index=True)
    var = pd.DataFrame(index=pd.Index(gene_order, name="gene_name"))
    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.obs[PERT_COL] = adata.obs[PERT_COL].astype("category")
    adata.obs[CONTEXT_COL] = adata.obs[CONTEXT_COL].astype("category")

    pred_path = out_dir / "prediction.h5ad"
    data_gb = adata.X.data.nbytes / 1e9
    print(
        f"[write] {pred_path} ({adata.shape[0]} x {adata.shape[1]}, "
        f"{adata.X.nnz / 1e6:.1f}M nnz, ~{data_gb:.2f} GB data) ...",
        flush=True,
    )
    adata.write_h5ad(str(pred_path), compression="gzip")

    meta = {
        "run_id": "k005-atlas-prior-validation",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "atlas_prior",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
        "atlas_targets": len(atlas_deltas),
        "atlas_src": str(args.atlas_src),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    elapsed = time.time() - t0
    print(f"[done] wrote {pred_path} in {elapsed:.1f}s", flush=True)
    print(
        "[note] next: vcc prep -g "
        f"{raw_dir / 'gene_names.csv'} --perts {raw_dir / 'pert_counts.csv'} {pred_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
