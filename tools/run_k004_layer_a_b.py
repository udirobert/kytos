"""Kytos k004 Layer A/B — context-conditioned gene transfer + single-cell transport.

For each target and context:
  1. Compute a gene-wise delta from ContextConditionedTransfer (Layer A).
  2. Sample real control cells.
  3. Apply the delta in log1p(counts) space and transform back to counts
     (preserves biological interpretation of the log2FC knockdown).
  4. Re-sparsify and write the prediction.

This is the first target-specific Kytos model: the target gene gets a real
CRISPRi knockdown and secondary effects are modulated by basal expression.
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


def build_context_predictions(
    context: str,
    control_path: Path,
    targets: list[str],
    gene_order: list[str],
    cells_per_pert: int,
    rng: np.random.Generator,
    knockdown_efficiency: float,
    attenuation_factor: float,
    noise_scale: float,
) -> tuple[sparse.csr_matrix, pd.DataFrame]:
    """Return a sparse prediction for one context using Layer A/B."""
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

    layer_a = ContextConditionedTransfer(
        knockdown_efficiency=knockdown_efficiency,
        attenuation_factor=attenuation_factor,
    )
    layer_b = AdditiveTransportSampler(noise_scale=noise_scale)

    # Work in log1p(counts) space; delta from Layer A is a log2FC-style shift.
    # Convert basal counts to log1p once, but per target we sample a slice.
    blocks: list[sparse.csr_matrix] = []
    obs_parts: list[pd.DataFrame] = []
    n_targets = len(targets)
    for i, tgt in enumerate(targets):
        if i % 50 == 0:
            print(f"  [{context}] {i}/{n_targets} {tgt}", flush=True)

        delta = layer_a.predict_delta(tgt, basal)

        idx = rng.choice(n_cells, size=cells_per_pert, replace=True)
        basal_slice = X_ctrl[idx].todense().astype(np.float32)

        # log1p-transform counts, apply additive delta + noise, expm1 back.
        log_basal = np.log1p(basal_slice, out=np.empty_like(basal_slice))
        seed = int(rng.integers(0, 1_000_000))
        perturbed = layer_b.sample_cells(
            log_basal, delta.astype(np.float32), n_samples=cells_per_pert, seed=seed
        )
        perturbed = np.expm1(perturbed)
        np.clip(perturbed, a_min=0.0, a_max=None, out=perturbed)
        # Round to nearest count so vcc prep require-counts is happy.
        perturbed = np.rint(perturbed).astype(np.float32)

        X_block = sparse.csr_matrix(perturbed)
        blocks.append(X_block)
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
        default=REPO / "experiments" / "k004-layer-a-b-validation",
    )
    ap.add_argument("--contexts", default="A,B,C", help="comma-separated contexts")
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
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
        X_pred, obs = build_context_predictions(
            ctx,
            ctrl_path,
            targets,
            gene_order,
            args.cells_per_pert,
            rng,
            args.knockdown_efficiency,
            args.attenuation_factor,
            args.noise_scale,
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
        "run_id": "k004-layer-a-b-validation",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "layer_a_b",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
        "knockdown_efficiency": args.knockdown_efficiency,
        "attenuation_factor": args.attenuation_factor,
        "noise_scale": args.noise_scale,
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
