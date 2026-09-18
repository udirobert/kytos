"""Kytos k014 — Track 2 trained-model consumption.

Loads `prediction_deltas.npz` produced by `tools/track2/train_conditional_mlp.py`
(on the Nebius box) and feeds the per-context trained deltas into the champion
k011 pipeline as the 'real' tier. Targets the trained model did not cover
(coverage_mask false — e.g. the ~28 unscoped targets without embeddings) fall
through to the k007 neighbor-imputation tier, then the fallback.

The trained deltas are magnitude-calibrated against ground truth during
training, so the default delta-scale is 1.0 (the k011 x1.7 scalar was a blind
amplification of borrowed signatures; keep it available via --delta-scale for
sweeping, but do not assume it applies).

Run (Modal; see tools/modal_k014_trained_model.py):
  python tools/run_k014_trained_model.py \
    --replogle-src /root/replogle/K562_gwps_raw_bulk_01.h5ad \
    --deltas /kytos-vol/k014/prediction_deltas.npz
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import anndata as ad  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import sparse  # noqa: E402

import run_k007_neighbor_prior as k007  # noqa: E402
from kytos.models.layer_a import ContextConditionedTransfer  # noqa: E402
from kytos.models.layer_b import HeterogeneousTransportSampler  # noqa: E402
from run_k005_atlas_prior import CONTEXT_COL, PERT_COL  # noqa: E402
from run_k006_replogle_prior import build_combined_deltas  # noqa: E402

RUN_ID = "k014-track2-mlp"


def load_trained_deltas(
    npz_path: Path,
) -> tuple[dict[str, dict[str, np.ndarray]], list[str], list[str], np.ndarray]:
    """Load prediction_deltas.npz -> per-context {target: delta}, contexts, targets, mask."""
    d = np.load(npz_path, allow_pickle=False)
    contexts = [str(c) for c in d["contexts"].tolist()]
    vcc_targets = [str(t) for t in d["vcc_targets"].tolist()]
    deltas = d["deltas"]  # (C, T, G)
    mask = d["coverage_mask"]  # (C, T)

    per_context: dict[str, dict[str, np.ndarray]] = {}
    for ci, ctx in enumerate(contexts):
        per_context[ctx] = {
            vcc_targets[ti]: deltas[ci, ti] for ti in range(len(vcc_targets)) if mask[ci, ti]
        }
    return per_context, contexts, vcc_targets, mask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument(
        "--atlas-src",
        type=Path,
        default=None,
        help="2025 Atlas validation h5ad (optional; used for neighbor coverage)",
    )
    ap.add_argument(
        "--replogle-src",
        type=Path,
        required=True,
        help="Replogle K562 GWPS bulk h5ad (neighbor-imputation coverage)",
    )
    ap.add_argument(
        "--deltas", type=Path, required=True, help="prediction_deltas.npz from the trained model"
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
    ap.add_argument(
        "--delta-scale",
        type=float,
        default=1.0,
        help="post-training magnitude scale; trained deltas are calibrated, default 1.0",
    )
    ap.add_argument("--library-cap", type=str, default="median")
    ap.add_argument("--neighbor-min-partners", type=int, default=2)
    ap.add_argument("--neighbor-min-score", type=float, default=0.7)
    ap.add_argument("--neighbor-topk", type=int, default=5)
    args = ap.parse_args(argv)

    raw_dir: Path = args.raw_dir
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_order = pd.read_csv(raw_dir / "gene_names.csv", header=None, skiprows=1)[0].tolist()
    all_targets = pd.read_csv(raw_dir / "pert_counts.csv", header=None, skiprows=1)[0].tolist()
    targets = all_targets[: args.max_targets] if args.max_targets else all_targets
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]

    if not args.deltas.exists():
        print(f"missing trained deltas {args.deltas}", file=sys.stderr)
        return 2
    if not args.replogle_src.exists():
        print(f"missing replogle source {args.replogle_src}", file=sys.stderr)
        return 3
    if not args.neighbor_map.exists():
        print(f"missing neighbor map {args.neighbor_map}", file=sys.stderr)
        return 4

    trained_deltas, delta_contexts, delta_targets, coverage_mask = load_trained_deltas(args.deltas)
    coverage_per_ctx = {ctx: len(trained_deltas.get(ctx, {})) for ctx in contexts}
    print(
        f"[trained] contexts {delta_contexts}, targets {len(delta_targets)}, "
        f"coverage {coverage_per_ctx}",
        flush=True,
    )

    # Neighbor-imputation coverage source: combined real priors (K562-based),
    # exactly as the k011 champion — used only for targets the trained model
    # did not cover.
    combined_deltas = build_combined_deltas(args.atlas_src, args.replogle_src, gene_order)
    neighbor_map = json.loads(args.neighbor_map.read_text())
    neighbor_deltas = k007.build_neighbor_deltas(
        neighbor_map,
        combined_deltas,
        gene_order,
        min_partners=args.neighbor_min_partners,
        min_score=args.neighbor_min_score,
        topk=args.neighbor_topk,
    )
    print(f"[neighbor] imputed {len(neighbor_deltas)} targets from combined priors", flush=True)

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
        real = trained_deltas.get(ctx, {})
        # Neighbor tier only for targets the trained model left uncovered.
        ctx_neighbors = {t: d for t, d in neighbor_deltas.items() if t not in real}
        X_pred, obs, used = k007.build_context_predictions(
            ctx,
            ctrl_path,
            targets,
            gene_order,
            args.cells_per_pert,
            rng,
            real,
            ctx_neighbors,
            fallback,
            sampler,
            library_cap=args.library_cap,
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
        "mode": "track2-trained-deltas+neighbor_imputation+heterogeneous_kd",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
        "deltas_src": str(args.deltas),
        "atlas_src": str(args.atlas_src) if args.atlas_src else None,
        "replogle_src": str(args.replogle_src),
        "neighbor_map": str(args.neighbor_map),
        "coverage_per_context": coverage_per_ctx,
        "coverage_mask_shape": list(coverage_mask.shape),
        "dispatch": totals,
        "kd_std": args.kd_std,
        "delta_scale": args.delta_scale,
        "library_cap": args.library_cap,
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
    sys.exit(main())
