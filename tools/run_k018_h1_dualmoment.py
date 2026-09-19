"""Kytos k018 — H1-trained low-rank transfer + dual-moment count generation.

Hybrid 2026 submission builder. Contexts listed in --h1-contexts use an
H1-trained rank-64 source->H1 delta transform plus dual-moment integer
count generation. Other contexts keep the k011 champion pipeline:
source/neighbor/fallback deltas + HeterogeneousTransportSampler.
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
for p in ("src", "tools"):
    if str(REPO / p) not in sys.path:
        sys.path.insert(0, str(REPO / p))

from kytos.features.basal import extract_basal_context  # noqa: E402
from kytos.models.dual_moment import build_prediction_dual_moment  # noqa: E402
from kytos.models.layer_a import ContextConditionedTransfer  # noqa: E402
from kytos.models.layer_b import HeterogeneousTransportSampler  # noqa: E402
import run_k007_neighbor_prior as k007  # noqa: E402
from run_k005_atlas_prior import CONTEXT_COL, PERT_COL  # noqa: E402
from run_k007_neighbor_prior import build_neighbor_deltas  # noqa: E402


def up(x: object) -> str:
    return str(x).strip().upper()


def read_gene_order(raw_dir: Path) -> list[str]:
    return [up(g) for g in pd.read_csv(raw_dir / "gene_names.csv", header=None, skiprows=1)[0]]


def read_targets(raw_dir: Path) -> list[str]:
    return [up(t) for t in pd.read_csv(raw_dir / "pert_counts.csv", header=None, skiprows=1)[0]]


def row_mapper(src_genes: list[str], dst_genes: list[str]):
    src_index = {g: i for i, g in enumerate(src_genes)}
    cols = np.array([src_index.get(g, -1) for g in dst_genes], dtype=np.int64)
    valid = cols >= 0

    def map_row(row: np.ndarray) -> np.ndarray:
        out = np.zeros(len(dst_genes), dtype=np.float32)
        out[valid] = np.asarray(row)[cols[valid]].astype(np.float32)
        return out

    return map_row


def fit_lowrank(x_train: np.ndarray, y_train: np.ndarray, rank: int):
    rank = max(1, min(rank, x_train.shape[0] - 1, x_train.shape[1] - 1))
    _, _, vx = np.linalg.svd(x_train.astype(np.float64), full_matrices=False)
    _, _, vy = np.linalg.svd(y_train.astype(np.float64), full_matrices=False)
    bx = vx[:rank].astype(np.float32)
    by = vy[:rank].astype(np.float32)
    xp = x_train @ bx.T
    yp = y_train @ by.T
    lam = max(1.0, 0.1 * float(np.trace(xp.T @ xp)) / max(rank, 1))
    w = np.linalg.solve(xp.T @ xp + lam * np.eye(rank, dtype=np.float32), xp.T @ yp)
    return bx, by, w


def finite(x: np.ndarray) -> np.ndarray:
    return np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)


def to_csr(x):
    return x.tocsr() if sparse.issparse(x) else sparse.csr_matrix(np.asarray(x))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument("--src-matrix", type=Path, required=True)
    ap.add_argument("--paired-npz", type=Path, required=True)
    ap.add_argument("--h1-npz", type=Path, required=True)
    ap.add_argument(
        "--neighbor-map",
        type=Path,
        default=REPO / "experiments" / "k007-neighbor-prior-validation" / "neighbor_map.json",
    )
    ap.add_argument("--out-dir", type=Path, default=REPO / "experiments" / "k018-h1-dualmoment")
    ap.add_argument("--contexts", default="A,B,C")
    ap.add_argument("--h1-contexts", default="C")
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-targets", type=int, default=0)
    ap.add_argument("--champion-delta-scale", type=float, default=1.7)
    ap.add_argument("--h1-delta-scale", type=float, default=2.0)
    ap.add_argument("--kd-std", type=float, default=2.0)
    ap.add_argument("--noise-scale", type=float, default=0.05)
    ap.add_argument("--knockdown-efficiency", type=float, default=2.5)
    ap.add_argument("--attenuation-factor", type=float, default=0.5)
    ap.add_argument("--amplitude", type=float, default=1.0)
    ap.add_argument("--bulk-amplitude", type=float, default=1.0)
    ap.add_argument("--pool-k", type=int, default=4)
    args = ap.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    gene_order = read_gene_order(args.raw_dir)
    all_targets = read_targets(args.raw_dir)
    targets = all_targets[: args.max_targets] if args.max_targets else all_targets
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]
    h1_contexts = {c.strip() for c in args.h1_contexts.split(",") if c.strip()}
    gene_index = {g: i for i, g in enumerate(gene_order)}

    if not args.src_matrix.exists():
        print(f"missing src matrix {args.src_matrix}", file=sys.stderr)
        return 2
    if not args.paired_npz.exists():
        print(f"missing paired npz {args.paired_npz}", file=sys.stderr)
        return 2
    if not args.h1_npz.exists():
        print(f"missing h1 npz {args.h1_npz}", file=sys.stderr)
        return 2
    if not args.neighbor_map.exists():
        print(f"missing neighbor map {args.neighbor_map}", file=sys.stderr)
        return 2

    paired = np.load(str(args.paired_npz), allow_pickle=True)
    src_genes = [up(g) for g in paired["genes"]]
    if len(src_genes) != len(gene_order) or src_genes != gene_order:
        print("[warn] source matrix gene order differs; remapping", flush=True)
    src = np.load(str(args.src_matrix), allow_pickle=True)
    src_targets = [up(t) for t in src["targets"]]
    src_target_idx = {t: i for i, t in enumerate(src_targets)}
    src_map = row_mapper(src_genes, gene_order)

    panel_source: dict[str, np.ndarray] = {}
    for t in targets:
        idx = src_target_idx.get(t)
        if idx is not None:
            panel_source[t] = src_map(src["deltas"][idx])
    print(f"[source] {len(panel_source)}/{len(targets)} targets have source deltas", flush=True)

    raw_neighbor_map = json.loads(args.neighbor_map.read_text())
    neighbor_map = {
        up(k): [{"gene": up(p["gene"]), "score": float(p["score"])} for p in v]
        for k, v in raw_neighbor_map.items()
    }
    covered_for_neighbors = dict(panel_source)
    for partners in neighbor_map.values():
        for p in partners:
            g = p["gene"]
            if g not in covered_for_neighbors and g in src_target_idx:
                covered_for_neighbors[g] = src_map(src["deltas"][src_target_idx[g]])
    neighbor_deltas = build_neighbor_deltas(
        neighbor_map,
        covered_for_neighbors,
        gene_order,
        min_partners=2,
        min_score=0.7,
        topk=5,
    )

    h1 = np.load(str(args.h1_npz), allow_pickle=True)
    h1_genes = [up(g) for g in h1["genes"]]
    h1_targets = [up(t) for t in h1["targets"]]
    h1_deltas = h1["deltas"]
    common_genes = [g for g in gene_order if g in set(h1_genes)]
    common_idx_2026 = np.array([gene_index[g] for g in common_genes], dtype=np.int64)
    h1_index = {g: i for i, g in enumerate(h1_genes)}
    common_idx_h1 = np.array([h1_index[g] for g in common_genes], dtype=np.int64)

    x_rows, y_rows, train_targets = [], [], []
    for hi, t in enumerate(h1_targets):
        si = src_target_idx.get(t)
        if si is None:
            continue
        x_rows.append(src_map(src["deltas"][si])[common_idx_2026])
        y_rows.append(np.asarray(h1_deltas[hi][common_idx_h1], dtype=np.float32))
        train_targets.append(t)
    if not x_rows:
        print("no H1 train/source pairs found", file=sys.stderr)
        return 3
    X = np.vstack(x_rows)
    Y = np.vstack(y_rows)
    bx, by, w = fit_lowrank(X, Y, rank=64)
    self_vals = []
    common_pos = {g: i for i, g in enumerate(common_genes)}
    for row, t in zip(range(len(train_targets)), train_targets):
        j = common_pos.get(t)
        if j is not None:
            self_vals.append(float(Y[row, j]))
    self_median = float(np.median(self_vals)) if self_vals else -1.6
    print(
        f"[train] pairs={len(train_targets)} common_genes={len(common_genes)} "
        f"self_median={self_median:.3f}",
        flush=True,
    )

    def transform_source_delta(delta_full: np.ndarray, target: str) -> np.ndarray:
        out = delta_full * args.h1_delta_scale
        if common_idx_2026.size:
            x = delta_full[common_idx_2026]
            y = ((x @ bx.T) @ w) @ by
            out[common_idx_2026] = y * args.h1_delta_scale
        j = gene_index.get(target)
        if j is not None:
            out[j] = self_median * args.h1_delta_scale
        return finite(out)

    direct_h1: dict[str, np.ndarray] = {}
    if "delta_hesc" in paired:
        paired_map = row_mapper([up(g) for g in paired["genes"]], gene_order)
        for i, t in enumerate([up(t) for t in paired["paired_targets"]]):
            if t in set(targets):
                direct_h1[t] = paired_map(paired["delta_hesc"][i])
    h1_map = row_mapper(h1_genes, gene_order)
    for hi, t in enumerate(h1_targets):
        if t in set(targets) and t not in direct_h1:
            direct_h1[t] = h1_map(h1_deltas[hi])
    print(f"[direct] {len(direct_h1)} panel targets have direct H1 deltas", flush=True)

    fallback = ContextConditionedTransfer(
        knockdown_efficiency=args.knockdown_efficiency,
        attenuation_factor=args.attenuation_factor,
    )
    sampler = HeterogeneousTransportSampler(noise_scale=args.noise_scale, kd_std=args.kd_std)

    ctx_blocks: list[sparse.csr_matrix] = []
    ctx_obs: list[pd.DataFrame] = []
    totals = {"champion": 0, "h1_direct": 0, "h1_transfer": 0, "h1_neighbor": 0, "fallback": 0}
    t0 = time.time()

    for ci, ctx in enumerate(contexts):
        ctrl_path = args.raw_dir / f"context_{ctx}.h5ad"
        if not ctrl_path.exists():
            print(f"missing {ctrl_path}", file=sys.stderr)
            return 4
        print(f"[ctx {ctx}] loading controls ...", flush=True)
        ctrl = ad.read_h5ad(str(ctrl_path))
        ctrl.X = to_csr(ctrl.X)

        if ctx in h1_contexts:
            basal = extract_basal_context(ctrl.X, gene_order)
            deltas: dict[str, np.ndarray] = {}
            for tgt in targets:
                if tgt in direct_h1:
                    deltas[tgt] = finite(direct_h1[tgt] * args.champion_delta_scale)
                    totals["h1_direct"] += 1
                elif tgt in panel_source:
                    deltas[tgt] = transform_source_delta(panel_source[tgt], tgt)
                    totals["h1_transfer"] += 1
                elif tgt in neighbor_deltas:
                    deltas[tgt] = transform_source_delta(neighbor_deltas[tgt], tgt)
                    totals["h1_neighbor"] += 1
                else:
                    d = fallback.predict_delta(tgt, basal).astype(np.float32)
                    d *= args.h1_delta_scale
                    j = gene_index.get(tgt)
                    if j is not None:
                        d[j] = self_median * args.h1_delta_scale
                    deltas[tgt] = finite(d)
                    totals["fallback"] += 1
            X_pred = build_prediction_dual_moment(
                ctrl,
                deltas,
                targets,
                gene_order,
                cells_per_target=args.cells_per_pert,
                amplitude=args.amplitude,
                bulk_amplitude=args.bulk_amplitude,
                pool_k=args.pool_k,
                seed=args.seed + ci,
            )
            obs = pd.DataFrame(
                {
                    PERT_COL: np.repeat(targets, args.cells_per_pert),
                    CONTEXT_COL: ctx,
                }
            )
            ctx_blocks.append(X_pred)
            ctx_obs.append(obs)
            print(
                f"[ctx {ctx}] dual-moment done ({X_pred.shape}, nnz {X_pred.nnz / 1e6:.1f}M)",
                flush=True,
            )
        else:
            rng = np.random.default_rng(args.seed + ci)
            X_pred, obs, used = k007.build_context_predictions(
                ctx,
                ctrl_path,
                targets,
                gene_order,
                args.cells_per_pert,
                rng,
                panel_source,
                neighbor_deltas,
                fallback,
                sampler,
                library_cap="median",
                delta_scale=args.champion_delta_scale,
            )
            totals["champion"] += used["real"] + used["neighbor"] + used["fallback"]
            ctx_blocks.append(X_pred)
            ctx_obs.append(obs)
            print(
                f"[ctx {ctx}] champion done ({X_pred.shape}, nnz {X_pred.nnz / 1e6:.1f}M)",
                flush=True,
            )

    X = sparse.vstack(ctx_blocks, format="csr")
    obs = pd.concat(ctx_obs, ignore_index=True)
    obs.index = pd.Index(
        [f"{c}-{t}-{i}" for i, (c, t) in enumerate(zip(obs[CONTEXT_COL], obs[PERT_COL]))],
        name="cell_id",
    )
    var = pd.DataFrame(index=pd.Index(gene_order, name="gene_name"))
    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.obs[PERT_COL] = adata.obs[PERT_COL].astype("category")
    adata.obs[CONTEXT_COL] = adata.obs[CONTEXT_COL].astype("category")
    adata.X.data = np.clip(np.rint(adata.X.data), 0, None).astype(np.int32)

    out = args.out_dir / "prediction.h5ad"
    print(f"[write] {out} shape={adata.shape} nnz={adata.X.nnz / 1e6:.1f}M", flush=True)
    adata.write_h5ad(str(out), compression="gzip")

    meta = {
        "run_id": "k018-h1-dualmoment",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contexts": contexts,
        "h1_contexts": sorted(h1_contexts),
        "targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": int(adata.shape[0]),
        "dispatch_totals": totals,
        "self_median_train": self_median,
        "rank": 64,
        "h1_delta_scale": args.h1_delta_scale,
        "champion_delta_scale": args.champion_delta_scale,
        "dual_moment": {
            "amplitude": args.amplitude,
            "bulk_amplitude": args.bulk_amplitude,
            "pool_k": args.pool_k,
        },
        "champion_sampler": {
            "type": "heterogeneous",
            "kd_std": args.kd_std,
            "noise_scale": args.noise_scale,
        },
        "elapsed_s": round(time.time() - t0, 1),
    }
    (args.out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"[done] {meta['elapsed_s']}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
