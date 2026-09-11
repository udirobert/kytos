"""Kytos k006 — Replogle K562 GWPS + optional 2025 Atlas prior + log1p transport.

Uses public perturbation datasets to cover as many 2026 targets as possible:

  1. VCC 2025 validation (optional, H1 hESC) — in-distribution prior.
  2. Replogle K562 genome-wide Perturb-seq bulk — broad coverage (~272/300
     2026 targets).
  3. ContextConditionedTransfer fallback for any remaining targets.

For each target, the preferred delta is Atlas > Replogle > fallback.
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
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

from kytos.models.layer_a import ContextConditionedTransfer  # noqa: E402
from kytos.models.layer_b import AdditiveTransportSampler  # noqa: E402
from perturbation_priors import (  # noqa: E402
    build_atlas_deltas,
    build_replogle_deltas,
)
from run_k005_atlas_prior import (  # noqa: E402
    CONTEXT_COL,
    PERT_COL,
    build_context_predictions,
)


def build_combined_deltas(
    atlas_path: Path | None,
    replogle_path: Path | None,
    context_genes: list[str],
    prefer_atlas: bool = True,
) -> dict[str, np.ndarray]:
    """Return a target→delta dict merging Atlas and Replogle priors."""
    atlas_deltas: dict[str, np.ndarray] = {}
    if atlas_path is not None and atlas_path.exists():
        atlas_deltas = build_atlas_deltas(atlas_path, context_genes)

    replogle_deltas: dict[str, np.ndarray] = {}
    if replogle_path is not None and replogle_path.exists():
        replogle_deltas = build_replogle_deltas(replogle_path, context_genes)

    combined: dict[str, np.ndarray] = {}
    for tgt, delta in replogle_deltas.items():
        combined[tgt] = delta
    for tgt, delta in atlas_deltas.items():
        if prefer_atlas or tgt not in combined:
            combined[tgt] = delta

    print(
        f"[prior] combined deltas: atlas={len(atlas_deltas)} "
        f"replogle={len(replogle_deltas)} combined={len(combined)}",
        flush=True,
    )
    return combined


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument(
        "--atlas-src",
        type=Path,
        default=None,
        help="optional VCC 2025 validation h5ad",
    )
    ap.add_argument(
        "--replogle-src",
        type=Path,
        required=True,
        help="Replogle K562 GWPS raw bulk h5ad",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=REPO / "experiments" / "k006-replogle-prior-validation",
    )
    ap.add_argument("--contexts", default="A,B,C", help="comma-separated contexts")
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-targets", type=int, default=0, help="0 = all targets")
    ap.add_argument("--knockdown-efficiency", type=float, default=2.5)
    ap.add_argument("--attenuation-factor", type=float, default=0.5)
    ap.add_argument("--noise-scale", type=float, default=0.05)
    ap.add_argument(
        "--prefer-atlas",
        action="store_true",
        default=True,
        help="prefer 2025 Atlas deltas over Replogle when both exist",
    )
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

    if not args.replogle_src.exists():
        print(f"missing replogle source {args.replogle_src}", file=sys.stderr)
        return 2

    deltas = build_combined_deltas(
        args.atlas_src,
        args.replogle_src,
        gene_order,
        prefer_atlas=args.prefer_atlas,
    )

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
            deltas,
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
        "run_id": "k006-replogle-prior-validation",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "replogle_prior",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
        "atlas_src": str(args.atlas_src) if args.atlas_src else None,
        "replogle_src": str(args.replogle_src),
        "prefer_atlas": args.prefer_atlas,
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
