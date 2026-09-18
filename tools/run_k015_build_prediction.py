"""Kytos k015 — apply learned low-rank context transfer to build panel predictions.

Takes the lowrank_models.npz produced by run_k015_essential_transfer.py and
applies the best low-rank linear transfer map to the K562 GWPS deltas for
each panel target, per context. Then builds the prediction h5ad using the
champion pipeline (heterogeneous KD sampling, delta_scale, library_cap).

Context mapping (from k012 lineage score):
  A -> Jurkat transfer map
  B -> RPE1 transfer map
  C -> HepG2 transfer map (hESC proxy; Atlas pairs too few for stable fit)

Usage:
  python tools/run_k015_build_prediction.py \
    --raw-dir data/raw/vcc2026 \
    --replogle-src /root/replogle/K562_gwps_raw_bulk_01.h5ad \
    --lowrank-models experiments/k015-essential-transfer/lowrank_models.npz \
    --neighbor-map experiments/k007-neighbor-prior-validation/neighbor_map.json \
    --out-dir experiments/k015-essential-transfer \
    --delta-scale 1.7 --kd-std 2.0
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import numpy as np  # noqa: E402
import run_k007_neighbor_prior as k007  # noqa: E402
from kytos.models.layer_b import HeterogeneousTransportSampler  # noqa: E402

RUN_ID = "k015-essential-transfer"

# Context -> low-rank model prefix in the npz
CTX_MODEL_PREFIX = {
    "A": "k562_to_jurkat",
    "B": "k562_to_rpe1",
    "C": "k562_to_hepg2",
}


def apply_lowrank_transfer(
    delta: np.ndarray,
    basis_s: np.ndarray,
    W: np.ndarray,
    basis_d: np.ndarray,
) -> np.ndarray:
    """Apply low-rank linear transfer: y = (x @ Vs^T) @ W @ Vd (uncentered fit)."""
    return ((delta.astype(np.float32) @ basis_s.T) @ W) @ basis_d


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument("--replogle-src", type=Path, required=True)
    ap.add_argument(
        "--lowrank-models",
        type=Path,
        required=True,
        help="lowrank_models.npz from run_k015_essential_transfer.py",
    )
    ap.add_argument(
        "--neighbor-map",
        type=Path,
        default=REPO / "experiments" / "k007-neighbor-prior-validation" / "neighbor_map.json",
    )
    ap.add_argument("--out-dir", type=Path, default=REPO / "experiments" / RUN_ID)
    ap.add_argument("--contexts", default="A,B,C")
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-targets", type=int, default=0)
    ap.add_argument("--knockdown-efficiency", type=float, default=2.5)
    ap.add_argument("--attenuation-factor", type=float, default=0.5)
    ap.add_argument("--noise-scale", type=float, default=0.05)
    ap.add_argument("--kd-std", type=float, default=2.0)
    ap.add_argument("--delta-scale", type=float, default=1.7)
    ap.add_argument("--neighbor-min-partners", type=int, default=2)
    ap.add_argument("--neighbor-min-score", type=float, default=0.7)
    ap.add_argument("--neighbor-topk", type=int, default=5)
    args = ap.parse_args(argv)

    import json
    import time

    import anndata as ad
    import pandas as pd
    from scipy import sparse

    from kytos.models.layer_a import ContextConditionedTransfer
    from run_k005_atlas_prior import CONTEXT_COL, PERT_COL
    from run_k006_replogle_prior import build_combined_deltas

    raw_dir: Path = args.raw_dir
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_order = pd.read_csv(raw_dir / "gene_names.csv", header=None, skiprows=1)[0].tolist()
    all_targets = pd.read_csv(raw_dir / "pert_counts.csv", header=None, skiprows=1)[0].tolist()
    targets = all_targets[: args.max_targets] if args.max_targets else all_targets
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]

    if not args.replogle_src.exists():
        print(f"missing replogle source {args.replogle_src}", file=sys.stderr)
        return 2
    if not args.lowrank_models.exists():
        print(f"missing low-rank models {args.lowrank_models}", file=sys.stderr)
        return 3
    if not args.neighbor_map.exists():
        print(f"missing neighbor map {args.neighbor_map}", file=sys.stderr)
        return 4

    # Load low-rank transfer models
    lr_models = np.load(args.lowrank_models, allow_pickle=False)
    available_models = [k for k in lr_models.keys() if k.endswith("_rank")]
    print(f"[models] loaded low-rank params: {available_models}", flush=True)

    # Build base deltas from K562 GWPS (the primary source for panel targets)
    real_deltas = build_combined_deltas(None, args.replogle_src, gene_order)
    neighbor_map = json.loads(args.neighbor_map.read_text())
    neighbor_deltas = k007.build_neighbor_deltas(
        neighbor_map,
        real_deltas,
        gene_order,
        min_partners=args.neighbor_min_partners,
        min_score=args.neighbor_min_score,
        topk=args.neighbor_topk,
    )
    neighbor_targets = sorted(t for t in neighbor_deltas if t not in real_deltas)
    print(
        f"[neighbor] imputed {len(neighbor_deltas)} targets; "
        f"{len(neighbor_targets)} are otherwise uncovered",
        flush=True,
    )

    # Apply low-rank transfer per context
    ctx_real_deltas = {}
    ctx_neighbor_deltas = {}
    for ctx in contexts:
        prefix = CTX_MODEL_PREFIX.get(ctx)
        model_available = prefix and f"{prefix}_W" in lr_models

        if model_available:
            basis_s = lr_models[f"{prefix}_basis_s"]
            basis_d = lr_models[f"{prefix}_basis_d"]
            W = lr_models[f"{prefix}_W"]
            rank = int(lr_models[f"{prefix}_rank"])
            print(
                f"[{ctx}] applying low-rank transfer (rank={rank}, prefix={prefix})",
                flush=True,
            )
            ctx_real_deltas[ctx] = {
                t: apply_lowrank_transfer(d, basis_s, W, basis_d) for t, d in real_deltas.items()
            }
            ctx_neighbor_deltas[ctx] = {
                t: apply_lowrank_transfer(d, basis_s, W, basis_d)
                for t, d in neighbor_deltas.items()
            }
        else:
            print(
                f"[{ctx}] no low-rank model for prefix '{prefix}', using raw deltas",
                flush=True,
            )
            ctx_real_deltas[ctx] = real_deltas
            ctx_neighbor_deltas[ctx] = neighbor_deltas

    rng = np.random.default_rng(args.seed)
    fallback = ContextConditionedTransfer(
        knockdown_efficiency=args.knockdown_efficiency,
        attenuation_factor=args.attenuation_factor,
    )
    sampler = HeterogeneousTransportSampler(noise_scale=args.noise_scale, kd_std=args.kd_std)

    t0 = time.time()
    ctx_blocks: list[sparse.csr_matrix] = []
    ctx_obs: list[pd.DataFrame] = []
    totals = {"real": 0, "neighbor": 0, "fallback": 0}
    for ctx in contexts:
        ctrl_path = raw_dir / f"context_{ctx}.h5ad"
        if not ctrl_path.exists():
            print(f"missing {ctrl_path}", file=sys.stderr)
            return 5
        X_pred, obs, used = k007.build_context_predictions(
            ctx,
            ctrl_path,
            targets,
            gene_order,
            args.cells_per_pert,
            rng,
            ctx_real_deltas[ctx],
            ctx_neighbor_deltas[ctx],
            fallback,
            sampler,
            library_cap="median",
            delta_scale=args.delta_scale,
        )
        ctx_blocks.append(X_pred)
        ctx_obs.append(obs)
        for k, v in used.items():
            totals[k] += v
    print(f"[dispatch] totals over {len(contexts)} contexts: {totals}", flush=True)

    X = sparse.vstack(ctx_blocks, format="csr")
    obs = pd.concat(ctx_obs, ignore_index=True)
    var = pd.DataFrame(index=pd.Index(gene_order, name="gene_name"))
    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.obs[PERT_COL] = adata.obs[PERT_COL].astype("category")
    adata.obs[CONTEXT_COL] = adata.obs[CONTEXT_COL].astype("category")

    pred_path = out_dir / "prediction.h5ad"
    print(
        f"[write] {pred_path} ({adata.shape[0]} x {adata.shape[1]}, "
        f"{adata.X.nnz / 1e6:.1f}M nnz) ...",
        flush=True,
    )
    adata.write_h5ad(str(pred_path), compression="gzip")

    meta = {
        "run_id": RUN_ID,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "essential_lowrank_transfer+neighbor_imputation+heterogeneous_kd+delta_scale",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
        "replogle_src": str(args.replogle_src),
        "lowrank_models": str(args.lowrank_models),
        "neighbor_map": str(args.neighbor_map),
        "neighbor_gate": {
            "min_partners": args.neighbor_min_partners,
            "min_score": args.neighbor_min_score,
            "topk": args.neighbor_topk,
        },
        "sampler": {
            "type": "heterogeneous",
            "noise_scale": args.noise_scale,
            "kd_std": args.kd_std,
        },
        "delta_scale": args.delta_scale,
        "library_cap": "median",
        "dispatch": totals,
        "imputed_targets": neighbor_targets,
        "knockdown_efficiency": args.knockdown_efficiency,
        "attenuation_factor": args.attenuation_factor,
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
