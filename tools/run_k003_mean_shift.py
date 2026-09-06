"""Kytos k003 — sparse mean-shift baseline for the 2026 validation set.

For each unseen context (A, B, C) and each official perturbation target, the
model predicts that the post-perturbation cells look like a fixed, sparse slice
of the control (non-targeting) basal state.  It is the honest "no shift"
baseline that the architecture doc calls the Phase-0 floor:

genes per cell:    top-k by control mean (default 300)
cells per target:  same as official panel (default 400)
perturbation col:  target_gene
context col:       context
control label:     non-targeting

This is intentionally tiny and laptop-safe: ~1.5 GB in memory, ~400–800 MB
on disk, so it can be prepped by `vcc prep` on a machine with 16 GB.  On an
8 GB Mac it may still swap; use `--contexts A` for a dry-run first.
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
DEFAULT_RAW = REPO / "data" / "raw" / "vcc2026"
DEFAULT_RUN = REPO / "experiments" / "k003-mean-shift-validation"

PERT_COL = "target_gene"
CONTEXT_COL = "context"
CONTROL_LABEL = "non-targeting"


def topk_control_counts(adata: ad.AnnData, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Return the top-k genes by control mean and their rounded counts."""
    mean = np.asarray(adata.X.mean(axis=0)).ravel()
    top_idx = np.argsort(mean)[-k:][::-1]
    top_counts = np.rint(np.maximum(mean[top_idx], 0.0)).astype(np.float32)
    top_counts = np.maximum(top_counts, 1.0)  # never zero; counts preserve log
    return top_idx.astype(np.int32), top_counts


def build_context_block(
    context: str,
    control_path: Path,
    targets: list[str],
    gene_order: list[str],
    cells_per_pert: int,
    genes_per_cell: int,
    include_controls: bool,
) -> tuple[sparse.csr_matrix, pd.DataFrame]:
    """One context matrix (targets + optional NTC cells) + obs."""
    print(f"[{context}] loading control h5ad …", flush=True)
    ctrl = ad.read_h5ad(str(control_path))
    n_genes = len(gene_order)

    top_idx, top_counts = topk_control_counts(ctrl, genes_per_cell)

    # target cells: each target gets `cells_per_pert` identical sparse rows
    n_target_cells = len(targets) * cells_per_pert
    row = np.repeat(np.arange(n_target_cells, dtype=np.int32), genes_per_cell)
    col = np.tile(top_idx, n_target_cells)
    data = np.tile(top_counts, n_target_cells)
    X_targets = sparse.coo_matrix((data, (row, col)), shape=(n_target_cells, n_genes)).tocsr()
    target_obs = pd.DataFrame(
        {
            PERT_COL: np.repeat(np.asarray(targets, dtype=object), cells_per_pert),
            CONTEXT_COL: np.repeat(context, n_target_cells),
        }
    )

    if not include_controls:
        return X_targets, target_obs

    # NTC cells: same pattern; vcc prep rejects them server-side anyway
    n_ctrl_cells = cells_per_pert
    row_c = np.repeat(np.arange(n_ctrl_cells, dtype=np.int32), genes_per_cell)
    col_c = np.tile(top_idx, n_ctrl_cells)
    data_c = np.tile(top_counts, n_ctrl_cells)
    X_ctrl = sparse.coo_matrix((data_c, (row_c, col_c)), shape=(n_ctrl_cells, n_genes)).tocsr()
    ctrl_obs = pd.DataFrame(
        {
            PERT_COL: np.repeat(CONTROL_LABEL, n_ctrl_cells),
            CONTEXT_COL: np.repeat(context, n_ctrl_cells),
        }
    )

    X = sparse.vstack([X_targets, X_ctrl], format="csr")
    obs = pd.concat([target_obs, ctrl_obs], ignore_index=True)
    return X, obs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--contexts", default="A,B,C", help="contexts to include")
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--genes-per-cell", type=int, default=300)
    ap.add_argument(
        "--include-controls",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "include a non-targeting control block per context "
            "(default: no; vcc rejects submitted controls)"
        ),
    )
    ap.add_argument("--max-targets", type=int, default=None)
    args = ap.parse_args(argv)

    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]
    raw_dir: Path = args.raw_dir
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_path = raw_dir / "gene_names.csv"
    perts_path = raw_dir / "pert_counts.csv"
    if not gene_path.is_file() or not perts_path.is_file():
        print(
            f"missing {gene_path} or {perts_path}; run `vcc datasets download controls`",
            file=sys.stderr,
        )
        return 1

    gene_order = pd.read_csv(gene_path, header=None, skiprows=1)[0].tolist()
    perts = pd.read_csv(perts_path, header=None, skiprows=1)[0].tolist()
    if args.max_targets is not None:
        perts = perts[: args.max_targets]

    blocks: list[sparse.csr_matrix] = []
    obs_parts: list[pd.DataFrame] = []

    t0 = time.time()
    for ctx in contexts:
        control_path = raw_dir / f"context_{ctx}.h5ad"
        if not control_path.is_file():
            print(f"missing {control_path}", file=sys.stderr)
            return 2
        X, obs = build_context_block(
            ctx,
            control_path,
            perts,
            gene_order,
            args.cells_per_pert,
            args.genes_per_cell,
            args.include_controls,
        )
        blocks.append(X)
        obs_parts.append(obs)
        print(f"[{ctx}] built {X.shape[0]} cells × {X.shape[1]} genes", flush=True)

    X = sparse.vstack(blocks, format="csr")
    obs = pd.concat(obs_parts, ignore_index=True)
    var = pd.DataFrame(index=gene_order)
    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.var.index = gene_order

    pred_path = out_dir / "prediction.h5ad"
    print(f"[write] {pred_path} ({adata.shape[0]} × {adata.shape[1]}) …", flush=True)
    adata.write_h5ad(str(pred_path), compression="gzip")

    meta = {
        "run_id": "k003-mean-shift-validation",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_contexts": len(contexts),
        "n_targets": len(perts),
        "cells_per_pert": args.cells_per_pert,
        "genes_per_cell": args.genes_per_cell,
        "prediction_sha256": "",
        "cells": int(adata.shape[0]),
        "genes": int(adata.shape[1]),
    }
    meta_path = out_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    elapsed = time.time() - t0
    print(f"[done] wrote {pred_path} in {elapsed:.1f}s", flush=True)
    print(f"[note] next: vcc prep --dry-run -g {gene_path} --perts {perts_path} {pred_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
