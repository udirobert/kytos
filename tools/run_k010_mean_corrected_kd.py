"""Kytos k010 — k007 priors + mean-corrected heterogeneous knockdown sampling.

Same prior stack and sampler family as k008 (eta ~ N(1, kd_std) truncated at
0), but each draw is divided by E[N(1, kd_std) | eta>0] so the applied delta
stays mean-1. The k009 gamma runs showed removing the mean inflation recovers
nmae (best-ever +0.022) but the skewed gamma shape costs pds/fid; this variant
keeps the symmetric shape the leaderboard rewards while removing the bias.

Note: dividing by the clipped mean shrinks the applied spread too, so
kd_std=2.0 yields eta (mean 1.0, std ~1.06) and kd_std=4.0 yields
(mean 1.0, std ~1.24) — both tighter than the k008 s2.0 champion's
effective (mean ~1.40, std ~1.48). If they underperform, the applied
mean inflation itself was load-bearing.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import run_k007_neighbor_prior as k007  # noqa: E402
from kytos.models.layer_b import HeterogeneousTransportSampler  # noqa: E402

RUN_ID = "k010-mean-corrected-kd-validation"


def main(argv: list[str] | None = None) -> int:
    # reuse the k007 CLI and pipeline; swap RUN_ID-scoped defaults and sampler
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument("--atlas-src", type=Path, default=None)
    ap.add_argument("--replogle-src", type=Path, required=True)
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
    if not args.neighbor_map.exists():
        print(f"missing neighbor map {args.neighbor_map}", file=sys.stderr)
        return 4

    real_deltas = build_combined_deltas(args.atlas_src, args.replogle_src, gene_order)
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

    rng = np.random.default_rng(args.seed)
    fallback = ContextConditionedTransfer(
        knockdown_efficiency=args.knockdown_efficiency,
        attenuation_factor=args.attenuation_factor,
    )
    sampler = HeterogeneousTransportSampler(
        noise_scale=args.noise_scale, kd_std=args.kd_std, mean_correct=True
    )

    t0 = time.time()
    ctx_blocks: list[sparse.csr_matrix] = []
    ctx_obs: list[pd.DataFrame] = []
    totals = {"real": 0, "neighbor": 0, "fallback": 0}
    for ctx in contexts:
        ctrl_path = raw_dir / f"context_{ctx}.h5ad"
        if not ctrl_path.exists():
            print(f"missing {ctrl_path}", file=sys.stderr)
            return 3
        X_pred, obs, used = k007.build_context_predictions(
            ctx,
            ctrl_path,
            targets,
            gene_order,
            args.cells_per_pert,
            rng,
            real_deltas,
            neighbor_deltas,
            fallback,
            sampler,
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
        "mode": "replogle_prior+neighbor_imputation+mean_corrected_kd",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
        "atlas_src": str(args.atlas_src) if args.atlas_src else None,
        "replogle_src": str(args.replogle_src),
        "neighbor_map": str(args.neighbor_map),
        "neighbor_gate": {
            "min_partners": args.neighbor_min_partners,
            "min_score": args.neighbor_min_score,
            "topk": args.neighbor_topk,
        },
        "sampler": {
            "type": "heterogeneous_mean_corrected",
            "noise_scale": args.noise_scale,
            "kd_std": args.kd_std,
            "mean_correct": True,
        },
        "kd_spread_evidence": "/kytos-vol/k008-kd-spread-v2.json "
        "(Atlas eta measurement w/ basal-noise decomposition)",
        "dispatch": totals,
        "imputed_targets": neighbor_targets,
        "knockdown_efficiency": args.knockdown_efficiency,
        "attenuation_factor": args.attenuation_factor,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    print(f"[done] wrote {pred_path} in {time.time() - t0:.1f}s", flush=True)
    print(
        "[note] next: vcc prep -g "
        f"{raw_dir / 'gene_names.csv'} --perts {raw_dir / 'pert_counts.csv'} {pred_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
