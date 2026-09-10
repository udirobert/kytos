"""Kytos k004 — real per-target control-cell resampling baseline.

For each target and context, sample real control (non-targeting) cells with
replacement.  This preserves the natural single-cell dispersion of the basal
state and gives every target a plausible post-perturbation distribution, but
it does not yet apply a target-specific perturbation signature (that is the
Layer A/B extension).

Memory strategy:
- Controls are kept sparse (CSR).
- Predictions are built context-by-context and vstacked, never densified.
- The full output is 360k x 18,533 and remains sparse.
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

PERT_COL = "target_gene"
CONTEXT_COL = "context"


def build_context_predictions(
    context: str,
    control_path: Path,
    targets: list[str],
    cells_per_pert: int,
    rng: np.random.Generator,
) -> tuple[sparse.csr_matrix, pd.DataFrame]:
    """Return a sparse prediction for one context."""
    print(f"[{context}] loading {control_path.name} ...", flush=True)
    ctrl = ad.read_h5ad(str(control_path))
    X_ctrl = ctrl.X.tocsr() if not sparse.isspmatrix_csr(ctrl.X) else ctrl.X
    n_cells = X_ctrl.shape[0]
    n_genes = X_ctrl.shape[1]

    print(
        f"  basal: {n_cells} cells, {n_genes} genes, mean nnz/cell {ctrl.X.nnz / ctrl.n_obs:.1f}",
        flush=True,
    )

    blocks: list[sparse.csr_matrix] = []
    obs_parts: list[pd.DataFrame] = []
    n_targets = len(targets)
    for i, tgt in enumerate(targets):
        if i % 50 == 0:
            print(f"  [{context}] {i}/{n_targets} {tgt}", flush=True)
        idx = rng.choice(n_cells, size=cells_per_pert, replace=True)
        blocks.append(X_ctrl[idx])
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
        f"nnz {X_pred.nnz:,} ({X_pred.nnz / (X_pred.shape[0] * X_pred.shape[1]):.3%} dense)",
        flush=True,
    )
    return X_pred, obs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=REPO / "experiments" / "k004-real-resampling-validation",
    )
    ap.add_argument("--contexts", default="A,B,C", help="comma-separated contexts")
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    raw_dir: Path = args.raw_dir
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_path = raw_dir / "gene_names.csv"
    if not gene_path.exists():
        print(f"missing {gene_path}; run `vcc datasets download controls`", file=sys.stderr)
        return 1

    gene_order = pd.read_csv(gene_path, header=None, skiprows=1)[0].tolist()
    targets = pd.read_csv(raw_dir / "pert_counts.csv", header=None, skiprows=1)[0].tolist()
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]

    rng = np.random.default_rng(args.seed)

    t0 = time.time()
    ctx_blocks: list[sparse.csr_matrix] = []
    ctx_obs: list[pd.DataFrame] = []
    for ctx in contexts:
        ctrl_path = raw_dir / f"context_{ctx}.h5ad"
        if not ctrl_path.exists():
            print(f"missing {ctrl_path}", file=sys.stderr)
            return 2
        X_pred, obs = build_context_predictions(ctx, ctrl_path, targets, args.cells_per_pert, rng)
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
        "run_id": "k004-real-resampling-validation",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "resample",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
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
