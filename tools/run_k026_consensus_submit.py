"""Kytos k026 — consensus_w_ctr submission build (Gate B winner).

Identical generation path to champion k011 (build_context_predictions +
HeterogeneousTransportSampler kd_std=2.0, library_cap="median",
400 cells/pert, delta_scale=1.7) but the "real" delta tier is the
multi-lineage weighted consensus (K562 2 : HCT116 1 : HEK293T 1 : CD4 1,
common-response centered) instead of the Replogle-K562 source. The NPZ
is on the panel axis in gene_names.csv order (verified); all 300 panel
targets are covered, so dispatch is expected to be all 'real'.

Evidence: Gate B gate-20260921-01 -- consensus_w_ctr avg_score 0.1417 vs
champion-equivalent k562_ds1p7 0.1085 (+0.033) through pinned cell-eval2
0.16.0. Declared trade: pds_cosine/lfc_nmae improve, direction fidelity
and sig-jaccard regress. See experiments/k025-eval2-gate/.
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

RUN_ID = "k026-consensus-w-ctr"


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument("--deltas-npz", type=Path, required=True)
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
    args = ap.parse_args(argv)

    import hashlib
    import json
    import time

    import anndata as ad
    import numpy as np
    import pandas as pd
    from scipy import sparse

    from kytos.models.layer_a import ContextConditionedTransfer
    from run_k005_atlas_prior import CONTEXT_COL, PERT_COL

    raw_dir: Path = args.raw_dir
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_order = pd.read_csv(raw_dir / "gene_names.csv", header=None, skiprows=1)[0].tolist()
    all_targets = pd.read_csv(raw_dir / "pert_counts.csv", header=None, skiprows=1)[0].tolist()
    targets = all_targets[: args.max_targets] if args.max_targets else all_targets
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]

    if not args.deltas_npz.exists():
        print(f"missing deltas npz {args.deltas_npz}", file=sys.stderr)
        return 2

    npz_bytes = args.deltas_npz.read_bytes()
    npz_sha = hashlib.sha256(npz_bytes).hexdigest()
    with np.load(args.deltas_npz, allow_pickle=False) as data:
        src_genes = [str(g) for g in data["genes"]]
        src_targets = [str(t) for t in data["targets"]]
        mat = data["deltas"].astype(np.float32)
    if src_genes != [str(g) for g in gene_order]:
        print("npz gene axis does not match gene_names.csv order", file=sys.stderr)
        return 5
    real_deltas = {t: mat[i] for i, t in enumerate(src_targets)}
    uncovered = [t for t in targets if t not in real_deltas]
    print(
        f"[deltas] {args.deltas_npz.name}: {len(real_deltas)} targets x "
        f"{mat.shape[1]} genes, sha256 {npz_sha[:12]}; "
        f"panel uncovered: {len(uncovered)} {uncovered[:10]}",
        flush=True,
    )

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
            return 3
        X_pred, obs, used = k007.build_context_predictions(
            ctx,
            ctrl_path,
            targets,
            gene_order,
            args.cells_per_pert,
            rng,
            real_deltas,
            {},
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
        "mode": "consensus_w_ctr deltas + heterogeneous_kd + delta_scale",
        "evidence": "Gate B gate-20260921-01: avg_score 0.1417 vs k562_ds1p7 "
        "0.1085 (experiments/k025-eval2-gate/)",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
        "deltas_npz": str(args.deltas_npz),
        "deltas_npz_sha256": npz_sha,
        "sampler": {
            "type": "heterogeneous",
            "noise_scale": args.noise_scale,
            "kd_std": args.kd_std,
        },
        "delta_scale": args.delta_scale,
        "library_cap": "median",
        "dispatch": totals,
        "uncovered_targets": uncovered,
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
