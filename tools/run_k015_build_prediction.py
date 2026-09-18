"""Kytos k015 — apply learned per-gene context transfer to build panel predictions.

Takes the transfer_params.json produced by run_k015_essential_transfer.py and
applies per-gene scaling factors to the K562 GWPS deltas for each panel target,
per context. Then builds the prediction h5ad using the champion pipeline.

Context mapping (from k012 lineage score):
  A -> Jurkat transfer weights
  B -> RPE1 transfer weights
  C -> hESC transfer weights (from Atlas 47 pairs, or HepG2 proxy)

Usage:
  python tools/run_k015_build_prediction.py \
    --raw-dir data/raw/vcc2026 \
    --replogle-src /root/replogle/K562_gwps_raw_bulk_01.h5ad \
    --transfer-params experiments/k015-essential-transfer/transfer_params.json \
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

import run_k007_neighbor_prior as k007  # noqa: E402
from kytos.models.layer_b import HeterogeneousTransportSampler  # noqa: E402

RUN_ID = "k015-essential-transfer"


def apply_transfer_weights(delta, s_gene, min_weight=0.0):
    """Apply per-gene transfer weights to a delta vector.

    s_gene[g] is the learned scaling factor for gene g.
    Genes with weight below min_weight are zeroed (noise suppression).
    """
    import numpy as np

    weights = np.asarray(s_gene, dtype=np.float32)
    mask = np.abs(weights) >= min_weight
    return (delta * weights * mask).astype(np.float32)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument("--replogle-src", type=Path, required=True)
    ap.add_argument(
        "--transfer-params",
        type=Path,
        required=True,
        help="transfer_params.json from run_k015_essential_transfer.py",
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
    ap.add_argument(
        "--min-transfer-weight",
        type=float,
        default=0.0,
        help="Zero out per-gene weights below this (noise suppression)",
    )
    ap.add_argument("--neighbor-min-partners", type=int, default=2)
    ap.add_argument("--neighbor-min-score", type=float, default=0.7)
    ap.add_argument("--neighbor-topk", type=int, default=5)
    args = ap.parse_args(argv)

    import json
    import time

    import anndata as ad
    import numpy as np
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
    if not args.transfer_params.exists():
        print(f"missing transfer params {args.transfer_params}", file=sys.stderr)
        return 3
    if not args.neighbor_map.exists():
        print(f"missing neighbor map {args.neighbor_map}", file=sys.stderr)
        return 4

    # Load transfer parameters
    transfer_params = json.loads(args.transfer_params.read_text())
    print(f"[transfer] loaded params for contexts: {list(transfer_params.keys())}", flush=True)

    # Context -> transfer key mapping
    ctx_transfer_key = {
        "A": "K562_to_Jurkat",
        "B": "K562_to_RPE1",
        "C": "K562_to_HepG2",  # fallback; hESC if available
    }

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

    # Apply transfer weights per context
    # We build context-specific delta dicts by scaling the base K562 deltas
    ctx_real_deltas = {}
    ctx_neighbor_deltas = {}
    for ctx in contexts:
        key = ctx_transfer_key.get(ctx)
        if key and key in transfer_params:
            s_gene = transfer_params[key].get("s_gene", [])
            if len(s_gene) == len(gene_order):
                print(f"[{ctx}] applying {key} transfer weights ({len(s_gene)} genes)", flush=True)
                ctx_real_deltas[ctx] = {
                    t: apply_transfer_weights(d, s_gene, args.min_transfer_weight)
                    for t, d in real_deltas.items()
                }
                ctx_neighbor_deltas[ctx] = {
                    t: apply_transfer_weights(d, s_gene, args.min_transfer_weight)
                    for t, d in neighbor_deltas.items()
                }
            else:
                print(
                    f"[{ctx}] WARNING: s_gene length {len(s_gene)} != {len(gene_order)}, "
                    "skipping transfer",
                    flush=True,
                )
                ctx_real_deltas[ctx] = real_deltas
                ctx_neighbor_deltas[ctx] = neighbor_deltas
        else:
            print(f"[{ctx}] no transfer params for key '{key}', using raw deltas", flush=True)
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
        "mode": "essential_transfer+neighbor_imputation+heterogeneous_kd+delta_scale",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
        "replogle_src": str(args.replogle_src),
        "transfer_params": str(args.transfer_params),
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
        "min_transfer_weight": args.min_transfer_weight,
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
