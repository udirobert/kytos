"""Extract the paired-transfer training set for the learned Layer A (k012).

Produces paired_transfer_train.npz: the ~50 targets screened in BOTH the
Replogle K562 GWPS bulk and the 2025 Atlas (H1 hESC) validation, with
per-context basal features for the 2026 control contexts. This is the
training/eval set for the transfer classes in
docs/k012-layer-a-pipeline.md, shared by Track 1 (Modal LOO harness) and
Track 2 (Nebius trained-model input).

NPZ contract (all dense float32 unless noted):
  genes            [G]        str   — 2026 context gene order (18,533)
  contexts         [C]        str   — e.g. ["A","B","C"]
  vcc_targets      [T]        str   — the 300-target panel (pert_counts.csv)
  paired_targets   [P]        str   — targets in BOTH atlas and replogle
  delta_k562       [P,G]      float32 — Replogle deltas, context gene order
  delta_hesc       [P,G]      float32 — Atlas deltas, same order
  basal_k562_log1p [G]        float32 — K562 control mean (log1p space)
  basal_hesc_log1p [G]        float32 — Atlas control mean (log1p space)
  basal_ctx_log1p  [C,G]      float32 — 2026 control means (log1p space)
  basal_ctx_raw    [C,G]      float32 — raw-count mean (as Layer A sees it)
  basal_ctx_rank   [C,G]      float32 — percentile rank 0..1
  basal_ctx_sparsity [C,G]    float32 — fraction non-zero cells

Optional --emit-src-matrix also writes delta_matrix_src.npz with every
combined real prior (replogle ∪ atlas, atlas preferred) for Track-2
full-panel training.

Run (Modal; see tools/modal_extract_paired_transfer.py):
  python tools/extract_paired_transfer.py \
    --raw-dir data/raw/vcc2026 \
    --atlas-src /root/atlas/adata_Validation.h5ad \
    --replogle-src /root/replogle/K562_gwps_raw_bulk_01.h5ad \
    --out experiments/k012-paired-transfer/paired_transfer_train.npz \
    --emit-src-matrix
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
sys.path.insert(0, str(REPO / "tools"))

from kytos.features.basal import extract_basal_context  # noqa: E402
from perturbation_priors import (  # noqa: E402
    build_atlas_deltas_with_control,
    build_replogle_deltas_with_control,
    log1p_sparse,
)


def context_basal(control_path: Path, gene_order: list[str]) -> dict[str, np.ndarray]:
    """Per-context basal features: log1p mean + raw stats over control cells."""
    ctrl = ad.read_h5ad(str(control_path))
    X = ctrl.X.tocsr() if not sparse.isspmatrix_csr(ctrl.X) else ctrl.X
    bc = extract_basal_context(X, gene_order)
    X_log = log1p_sparse(X)
    log1p_mean = np.asarray(X_log.mean(axis=0)).ravel().astype(np.float32)
    return {
        "log1p_mean": log1p_mean,
        "raw_mean": bc.mean_expression.astype(np.float32),
        "rank": bc.expression_rank.astype(np.float32),
        "sparsity": bc.sparsity.astype(np.float32),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument("--atlas-src", type=Path, required=True)
    ap.add_argument("--replogle-src", type=Path, required=True)
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO / "experiments" / "k012-paired-transfer" / "paired_transfer_train.npz",
    )
    ap.add_argument("--contexts", type=str, default="A,B,C")
    ap.add_argument(
        "--emit-src-matrix",
        action="store_true",
        help="also write delta_matrix_src.npz (all combined real priors, for Track-2 training)",
    )
    args = ap.parse_args(argv)

    t0 = time.time()
    raw_dir: Path = args.raw_dir
    args.out.parent.mkdir(parents=True, exist_ok=True)

    gene_order = pd.read_csv(raw_dir / "gene_names.csv", header=None, skiprows=1)[0].tolist()
    vcc_targets = pd.read_csv(raw_dir / "pert_counts.csv", header=None, skiprows=1)[0].tolist()
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]

    atlas_deltas, atlas_ctrl = build_atlas_deltas_with_control(str(args.atlas_src), gene_order)
    replogle_deltas, replogle_ctrl = build_replogle_deltas_with_control(
        str(args.replogle_src), gene_order
    )

    paired = sorted(set(atlas_deltas) & set(replogle_deltas))
    print(f"[paired] {len(paired)} targets in both atlas and replogle", flush=True)
    paired_in_panel = [t for t in paired if t in set(vcc_targets)]
    print(
        f"[paired] {len(paired_in_panel)} of them are on the 2026 panel",
        flush=True,
    )
    if not paired:
        print("no paired targets — check source overlap", file=sys.stderr)
        return 2

    delta_k562 = np.stack([replogle_deltas[t] for t in paired]).astype(np.float32)
    delta_hesc = np.stack([atlas_deltas[t] for t in paired]).astype(np.float32)

    ctx_feats = []
    for ctx in contexts:
        path = raw_dir / f"context_{ctx}.h5ad"
        print(f"[ctx {ctx}] loading {path.name} ...", flush=True)
        ctx_feats.append(context_basal(path, gene_order))
        print(f"[ctx {ctx}] done", flush=True)

    np.savez_compressed(
        args.out,
        genes=np.asarray(gene_order),
        contexts=np.asarray(contexts),
        vcc_targets=np.asarray(vcc_targets),
        paired_targets=np.asarray(paired),
        delta_k562=delta_k562,
        delta_hesc=delta_hesc,
        basal_k562_log1p=replogle_ctrl.astype(np.float32),
        basal_hesc_log1p=atlas_ctrl.astype(np.float32),
        basal_ctx_log1p=np.stack([f["log1p_mean"] for f in ctx_feats]),
        basal_ctx_raw=np.stack([f["raw_mean"] for f in ctx_feats]),
        basal_ctx_rank=np.stack([f["rank"] for f in ctx_feats]),
        basal_ctx_sparsity=np.stack([f["sparsity"] for f in ctx_feats]),
    )
    print(f"[out] wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)", flush=True)

    if args.emit_src_matrix:
        src_targets = sorted(set(replogle_deltas) | set(atlas_deltas))
        src_matrix = np.stack(
            [atlas_deltas[t] if t in atlas_deltas else replogle_deltas[t] for t in src_targets]
        ).astype(np.float32)
        src_out = args.out.parent / "delta_matrix_src.npz"
        np.savez(src_out, targets=np.asarray(src_targets), deltas=src_matrix)
        print(
            f"[out] wrote {src_out} ({src_out.stat().st_size / 1e6:.1f} MB, "
            f"{len(src_targets)} targets)",
            flush=True,
        )

    report = {
        "created": time.strftime("%Y-%m-%d"),
        "n_genes": len(gene_order),
        "n_vcc_targets": len(vcc_targets),
        "n_atlas_targets": len(atlas_deltas),
        "n_replogle_targets": len(replogle_deltas),
        "n_paired": len(paired),
        "n_paired_on_panel": len(paired_in_panel),
        "paired_targets": paired,
        "contexts": contexts,
        "elapsed_s": round(time.time() - t0, 1),
    }
    report_path = args.out.parent / "extract_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"[out] wrote {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
