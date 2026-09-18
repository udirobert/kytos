#!/usr/bin/env python3
"""
Kytos k004 — Kaggle smoke: real control-cell resampling + ContextConditioned Layer A

Ratiocine two-phase smoke for Kaggle free GPU/CPU (13GB RAM CPU, 16GB T4x2).

What it does (fits free tier, ~4-6 min for 20 targets x 3 contexts):
  1. Loads VCC 2026 controls (data/raw/vcc2026 or /kaggle/input/vcc2026-controls)
  2. EDA: per-context basal stats (uses src/kytos/features/basal.py sparse-safe)
  3. Exp A: real control-cell resampling baseline (no model, preserves dispersion)
         — the "next run" from experiments/README.md:25 / docs/architecture.md §4
  4. Exp B: ContextConditionedTransfer + AdditiveTransportSampler (Layer A+B smoke)
  5. Writes cell-eval-ready pred.h5ad (sparse) + meta.json
  6. Proxy metrics (and cell-eval run if --run-ceiling and Atlas available)

Usage locally (8GB Mac — keep --max-targets small):
  python notebooks/kaggle_k004_smoke.py --max-targets 10 --contexts A --out /tmp/k004_test

On Kaggle (after uploading vcc2026-controls dataset):
  python kaggle_k004_smoke.py --max-targets 30 --contexts A,B,C --out /kaggle/working/k004

Memory: never densifies full 360k x 18533 (~26GB). Per-target sampling densifies
400 x 18533 slices (~29MB float32) one at a time.
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

# --- repo import (works both locally and on Kaggle after git clone) ---
REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from kytos.features.basal import extract_basal_context
from kytos.models.layer_a import ContextConditionedTransfer
from kytos.models.layer_b import AdditiveTransportSampler

PERT_COL = "target_gene"
CONTEXT_COL = "context"
CONTROL_LABEL = "non-targeting"


def resolve_raw_dir(cli: Path | None) -> Path:
    if cli and cli.exists():
        return cli
    # Kaggle dataset mount
    for cand in [
        Path("/kaggle/input/vcc2026-controls"),
        Path("/kaggle/input/vcc2026-controls/data/raw/vcc2026"),
        Path("/kaggle/input/kytos-vcc2026-controls"),
    ]:
        if cand.exists() and (cand / "gene_names.csv").exists():
            return cand
        # Kaggle nests under dataset name
        if cand.exists():
            for sub in cand.rglob("gene_names.csv"):
                return sub.parent
    # local
    local = REPO / "data" / "raw" / "vcc2026"
    if local.exists():
        return local
    raise FileNotFoundError("Cannot find vcc2026 raw dir. Pass --raw-dir explicitly.")


def build_pred_for_context(
    context: str,
    control_path: Path,
    targets: list[str],
    gene_order: list[str],
    cells_per_pert: int,
    mode: str,  # "resample" or "layer_a_b"
    seed: int,
) -> tuple[sparse.csr_matrix, pd.DataFrame]:
    """Return (X_pred sparse, obs) for one context."""
    print(f"[{context}] loading {control_path.name} ...", flush=True)
    ctrl = ad.read_h5ad(str(control_path))
    n_genes = len(gene_order)
    assert ctrl.n_vars == n_genes, f"gene mismatch {ctrl.n_vars} vs {n_genes}"

    # Basal context (sparse-safe, no densify) — feeds Layer A
    ctx = extract_basal_context(ctrl.X, gene_order)
    print(
        f"  basal: {ctx.n_cells} cells, mean nnz/cell {ctrl.X.nnz / ctrl.n_obs:.1f}, "
        f"sparsity {1 - ctrl.X.nnz / (ctrl.n_obs * ctrl.n_vars):.3f}",
        flush=True,
    )
    # top-3 genes diagnostic
    top_idx = np.argsort(ctx.mean_expression)[-3:][::-1]
    print(
        f"  top genes: {[(gene_order[i], round(float(ctx.mean_expression[i]), 1)) for i in top_idx]}",
        flush=True,
    )

    rng = np.random.default_rng(seed)
    model = ContextConditionedTransfer() if mode == "layer_a_b" else None
    sampler = AdditiveTransportSampler(noise_scale=0.05) if mode == "layer_a_b" else None

    # For resampling baseline we just sample rows from ctrl.X directly.
    # For layer_a_b we sample then apply delta per target (densify 400 x 18533 slices only).
    blocks: list[sparse.csr_matrix] = []
    obs_rows: list[pd.DataFrame] = []

    # Pre-convert ctrl.X to CSR for fast row slicing; keep sparse
    X_ctrl_csr = ctrl.X.tocsr() if not sparse.isspmatrix_csr(ctrl.X) else ctrl.X

    for tgt in targets:
        if mode == "resample":
            idx = rng.choice(ctx.n_cells, size=cells_per_pert, replace=True)
            X_block = X_ctrl_csr[idx]  # sparse slice, preserves real dispersion
        else:
            # Layer A delta conditioned on basal rank
            assert model is not None and sampler is not None
            delta = model.predict_delta(tgt, ctx)  # (G,)
            # sample basal rows, densify slice, perturb, re-sparsify
            idx = rng.choice(ctx.n_cells, size=cells_per_pert, replace=True)
            basal_slice = np.asarray(X_ctrl_csr[idx].todense(), dtype=np.float32)
            # sampler expects dense; it clips to >=0
            perturbed = sampler.sample_cells(
                basal_slice,
                delta.astype(np.float32),
                n_samples=cells_per_pert,
                seed=int(rng.integers(0, 1_000_000)),
            )
            # keep sparse for output (sparsity ~0.3-0.5 after perturbation)
            X_block = sparse.csr_matrix(perturbed)

        blocks.append(X_block)
        obs_rows.append(
            pd.DataFrame(
                {PERT_COL: [tgt] * cells_per_pert, CONTEXT_COL: [context] * cells_per_pert}
            )
        )

    X_pred = sparse.vstack(blocks, format="csr")
    obs = pd.concat(obs_rows, ignore_index=True)
    print(
        f"  -> {mode}: {X_pred.shape[0]} cells x {X_pred.shape[1]} genes, nnz {X_pred.nnz:,} ({X_pred.nnz / (X_pred.shape[0] * X_pred.shape[1]):.3%} dense)",
        flush=True,
    )
    return X_pred, obs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("experiments/k004-kaggle-smoke"))
    ap.add_argument("--contexts", default="A,B,C", help="comma-separated: A,B,C")
    ap.add_argument(
        "--max-targets",
        type=int,
        default=20,
        help="subset of 300 targets (Kaggle free: 20-30 fits 13GB)",
    )
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--mode", choices=["resample", "layer_a_b", "both"], default="both")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--run-cell-eval",
        action="store_true",
        help="if set, try cell-eval run against controls (needs real ground truth; skips on Kaggle)",
    )
    args = ap.parse_args(argv)

    raw_dir = resolve_raw_dir(args.raw_dir)
    print(f"raw_dir: {raw_dir}")
    gene_order = pd.read_csv(raw_dir / "gene_names.csv", header=None, skiprows=1)[0].tolist()
    all_targets = pd.read_csv(raw_dir / "pert_counts.csv", header=None, skiprows=1)[0].tolist()
    targets = all_targets[: args.max_targets] if args.max_targets else all_targets
    print(f"genes: {len(gene_order)}, targets: {len(targets)} / {len(all_targets)}")

    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    modes = ["resample", "layer_a_b"] if args.mode == "both" else [args.mode]

    for mode in modes:
        t0 = time.time()
        blocks: list[sparse.csr_matrix] = []
        obss: list[pd.DataFrame] = []
        for ctx in contexts:
            ctrl_path = raw_dir / f"context_{ctx}.h5ad"
            if not ctrl_path.exists():
                # try nested
                candidates = list(raw_dir.rglob(f"context_{ctx}.h5ad"))
                if candidates:
                    ctrl_path = candidates[0]
                else:
                    print(f"missing {ctrl_path}", file=sys.stderr)
                    return 2
            Xb, obs = build_pred_for_context(
                ctx, ctrl_path, targets, gene_order, args.cells_per_pert, mode, seed=args.seed
            )
            blocks.append(Xb)
            obss.append(obs)

        X_all = sparse.vstack(blocks, format="csr")
        obs_all = pd.concat(obss, ignore_index=True)
        var = pd.DataFrame(index=pd.Index(gene_order, name="gene_name"))
        adata_pred = ad.AnnData(X=X_all, obs=obs_all, var=var)
        adata_pred.obs[PERT_COL] = adata_pred.obs[PERT_COL].astype("category")
        adata_pred.obs[CONTEXT_COL] = adata_pred.obs[CONTEXT_COL].astype("category")

        out_h5ad = out_dir / f"pred_{mode}.h5ad"
        print(
            f"[{mode}] writing {out_h5ad} ({X_all.shape[0]} x {X_all.shape[1]}, {X_all.nnz / 1e6:.1f}M nnz, ~{X_all.data.nbytes / 1e6:.0f} MB data) ...",
            flush=True,
        )
        adata_pred.write_h5ad(str(out_h5ad), compression="gzip")
        print(f"[{mode}] wrote in {time.time() - t0:.1f}s")

        # lightweight proxy metrics (no ground truth needed): compare pred pseudobulk vs control mean
        # For real cell-eval, user would run against withheld ground truth on Kaggle if available.
        # Here we show that layer_a_b actually shifts target genes vs resample baseline.
        # Compute mean shift for first target as sanity check
        first_tgt = targets[0]
        mask = adata_pred.obs[PERT_COL] == first_tgt
        X_first = adata_pred[mask].X
        if sparse.issparse(X_first):
            mean_first = np.asarray(X_first.mean(axis=0)).ravel()
        else:
            mean_first = X_first.mean(axis=0)
        if first_tgt in gene_order:
            gidx = gene_order.index(first_tgt)
            # control mean for reference (reload first context)
            ctrl0 = ad.read_h5ad(str(raw_dir / f"context_{contexts[0]}.h5ad"))
            ctrl_mean = np.asarray(ctrl0.X.mean(axis=0)).ravel()[gidx]
            print(
                f"  sanity {first_tgt}: ctrl mean {ctrl_mean:.2f} -> pred mean {mean_first[gidx]:.2f} (delta {mean_first[gidx] - ctrl_mean:.2f})",
                flush=True,
            )

        meta = {
            "run_id": f"k004-kaggle-smoke-{mode}",
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "mode": mode,
            "raw_dir": str(raw_dir),
            "contexts": contexts,
            "n_targets": len(targets),
            "cells_per_pert": args.cells_per_pert,
            "total_cells": int(X_all.shape[0]),
            "n_genes": int(X_all.shape[1]),
            "seed": args.seed,
            "note": "Kaggle free-tier smoke: resample baseline vs ContextConditionedTransfer+AdditiveTransport. See notebooks/kaggle_k004_smoke.py",
        }
        (out_dir / f"meta_{mode}.json").write_text(json.dumps(meta, indent=2))
        print(f"[{mode}] meta -> {out_dir / f'meta_{mode}.json'}")

    print(f"\nDone. Outputs in {out_dir}")
    print("Kaggle: upload pred_*.h5ad as submission or run `vcc prep --dry-run` to validate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
