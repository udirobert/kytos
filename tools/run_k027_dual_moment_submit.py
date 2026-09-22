"""Kytos k027 — consensus_w_ctr deltas + dual-moment count generation.

Same delta source as k026 (variant_consensus_w_ctr.npz — weighted
K562 2 : HCT116 1 : HEK293T 1 : CD4 1, common-response centered; NPZ is on
the panel axis in gene_names.csv order, all 300 panel targets covered) but
replaces HeterogeneousTransportSampler with build_prediction_dual_moment —
the winning generation arm from Gate B sweep gate-20260922-02. Exact arm
metrics are embargoed (experiments/_embargoed/k025-eval2-gate/).

Dual-moment generation preserves per-cell library depth exactly and matches
both the per-cell mean-CPM moment and the pseudobulk moment under the
applied delta — no kd_std/noise_scale/library_cap tuning.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

RUN_ID = "k027-consensus-dm"


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
    ap.add_argument("--amplitude", type=float, default=1.0)
    ap.add_argument("--bulk-amplitude", type=float, default=0.5)
    ap.add_argument("--pool-k", type=int, default=4)
    args = ap.parse_args(argv)

    import hashlib
    import json
    import time

    import anndata as ad
    import numpy as np
    import pandas as pd
    from scipy import sparse

    from kytos.models.dual_moment import build_prediction_dual_moment
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

    t0 = time.time()
    ctx_blocks: list[sparse.csr_matrix] = []
    ctx_obs: list[pd.DataFrame] = []
    for ctx in contexts:
        ctrl_path = raw_dir / f"context_{ctx}.h5ad"
        if not ctrl_path.exists():
            print(f"missing {ctrl_path}", file=sys.stderr)
            return 3
        print(f"[{ctx}] loading {ctrl_path.name} ...", flush=True)
        ctrl = ad.read_h5ad(str(ctrl_path))
        X_ctx = build_prediction_dual_moment(
            ctrl,
            real_deltas,
            targets,
            gene_order,
            cells_per_target=args.cells_per_pert,
            amplitude=args.amplitude,
            bulk_amplitude=args.bulk_amplitude,
            pool_k=args.pool_k,
            seed=args.seed,
        )
        ctx_blocks.append(X_ctx)
        ctx_obs.append(
            pd.DataFrame(
                {
                    PERT_COL: np.repeat(targets, args.cells_per_pert),
                    CONTEXT_COL: ctx,
                }
            )
        )
        del ctrl
        print(f"[{ctx}] {X_ctx.shape[0]} cells x {X_ctx.shape[1]} genes", flush=True)

    X = sparse.vstack(ctx_blocks, format="csr").astype(np.int32)
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
        "mode": "consensus_w_ctr deltas + dual-moment count generation",
        "evidence": "Gate B gate-20260922-02 winning arm; exact metrics "
        "embargoed (experiments/_embargoed/k025-eval2-gate/)",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "n_genes": int(adata.shape[1]),
        "nnz": int(adata.X.nnz),
        "seed": args.seed,
        "deltas_npz": str(args.deltas_npz),
        "deltas_npz_sha256": npz_sha,
        "generator": {
            "type": "dual_moment",
            "amplitude": args.amplitude,
            "bulk_amplitude": args.bulk_amplitude,
            "pool_k": args.pool_k,
            "space": "bulk_delta",
        },
        "dispatch": {"real": len(targets) * len(contexts) - len(uncovered) * len(contexts)},
        "uncovered_targets": uncovered,
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
