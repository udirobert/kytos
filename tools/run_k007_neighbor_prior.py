"""Kytos k007 — k006 priors + STRING-neighbor imputation for uncovered targets.

k006 left 28/300 targets on the hand-tuned ContextConditionedTransfer fallback
because they are unscreened in every Replogle arm (not expressed in K562 GWPS,
not DepMap-essential). In-corpus validation on held-out GWPS genes showed that
a score-weighted mean of a missing gene's STRING partners' deltas discriminates
its true signature (median 36th percentile vs 50% random; strong-partner genes
reach the top 5%).

For each still-uncovered target with enough confident covered partners, the
delta is the STRING-score-weighted mean of the partners' context-mapped
Replogle deltas, with each partner's own knockdown coordinate masked, plus the
same target self-knockdown the fallback would apply. Targets below the
evidence gate keep the k006 fallback.

Dispatch per target: Atlas/Replogle real delta > neighbor-imputed > fallback.
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
from kytos.features.basal import extract_basal_context  # noqa: E402
from run_k005_atlas_prior import CONTEXT_COL, PERT_COL  # noqa: E402
from run_k006_replogle_prior import build_combined_deltas  # noqa: E402

RUN_ID = "k007-neighbor-prior-validation"


def build_neighbor_deltas(
    neighbor_map: dict[str, list[dict]],
    covered_deltas: dict[str, np.ndarray],
    context_genes: list[str],
    *,
    min_partners: int = 2,
    min_score: float = 0.7,
    topk: int = 5,
) -> dict[str, np.ndarray]:
    """Score-weighted mean of STRING partners' deltas for uncovered targets.

    Each partner's own knockdown coordinate is masked so the borrowed
    signature carries only trans effects; the target's own knockdown is
    added later per context (basal-rank-scaled, same rule as the fallback).
    """
    gene_idx = {g: i for i, g in enumerate(context_genes)}
    out: dict[str, np.ndarray] = {}
    for tgt, partners in neighbor_map.items():
        strong = [
            (p["gene"], float(p["score"]))
            for p in partners
            if p["gene"] in covered_deltas and float(p["score"]) >= min_score
        ]
        strong = sorted(strong, key=lambda x: -x[1])[:topk]
        if len(strong) < min_partners:
            continue
        weights = np.array([s for _, s in strong])
        weights /= weights.sum()
        acc = np.zeros(len(context_genes), dtype=np.float64)
        for (pgene, _), w in zip(strong, weights):
            d = covered_deltas[pgene].astype(np.float64).copy()
            pi = gene_idx.get(pgene)
            if pi is not None:
                d[pi] = 0.0  # mask partner self-knockdown
            acc += w * d
        out[tgt] = acc.astype(np.float32)
    return out


def self_knockdown(tgt: str, basal, knockdown_efficiency: float) -> tuple[int | None, float]:
    """Target self-KD term, mirroring ContextConditionedTransfer's rule."""
    if tgt not in basal.genes:
        return None, 0.0
    t_idx = basal.genes.index(tgt)
    target_rank = float(basal.expression_rank[t_idx])
    eff = knockdown_efficiency * min(1.0, max(0.1, target_rank))
    return t_idx, -eff


def build_context_predictions(
    context: str,
    control_path: Path,
    targets: list[str],
    gene_order: list[str],
    cells_per_pert: int,
    rng: np.random.Generator,
    real_deltas: dict[str, np.ndarray],
    neighbor_deltas: dict[str, np.ndarray],
    fallback: ContextConditionedTransfer,
    sampler: AdditiveTransportSampler,
    library_cap: float | str | None = None,
) -> tuple[sparse.csr_matrix, pd.DataFrame, dict]:
    """Sparse prediction for one context: real > neighbor-imputed > fallback.

    library_cap rescales cells whose post-rounding count total exceeds the
    cap: a number, or "median" for the context's median control library
    size. Backstop for heavy-tailed samplers whose extreme draws would
    otherwise trip the VCC 1e6 per-cell count limit.
    """
    print(f"[{context}] loading {control_path.name} ...", flush=True)
    ctrl = ad.read_h5ad(str(control_path))
    X_ctrl = ctrl.X.tocsr() if not sparse.isspmatrix_csr(ctrl.X) else ctrl.X
    n_cells, n_genes = X_ctrl.shape
    assert n_genes == len(gene_order)

    if isinstance(library_cap, str):
        if library_cap != "median":
            raise ValueError(f"unknown library_cap {library_cap!r}")
        lib_sizes = np.asarray(X_ctrl.sum(axis=1)).ravel()
        library_cap = float(np.median(lib_sizes))
        print(f"  library_cap=median -> {library_cap:.0f}", flush=True)

    basal = extract_basal_context(X_ctrl, gene_order)
    print(
        f"  basal: {n_cells} cells, mean nnz/cell {ctrl.X.nnz / ctrl.n_obs:.1f}",
        flush=True,
    )

    blocks: list[sparse.csr_matrix] = []
    obs_parts: list[pd.DataFrame] = []
    used = {"real": 0, "neighbor": 0, "fallback": 0}
    for i, tgt in enumerate(targets):
        if i % 50 == 0:
            print(f"  [{context}] {i}/{len(targets)} {tgt}", flush=True)

        if tgt in real_deltas:
            delta = real_deltas[tgt]
            used["real"] += 1
        elif tgt in neighbor_deltas:
            delta = neighbor_deltas[tgt].copy()
            t_idx, kd = self_knockdown(tgt, basal, fallback.knockdown_efficiency)
            if t_idx is not None:
                delta[t_idx] = kd
            used["neighbor"] += 1
        else:
            delta = fallback.predict_delta(tgt, basal)
            used["fallback"] += 1

        idx = rng.choice(n_cells, size=cells_per_pert, replace=True)
        basal_slice = X_ctrl[idx].todense().astype(np.float32)

        log_basal = np.log1p(basal_slice, out=np.empty_like(basal_slice))
        seed = int(rng.integers(0, 1_000_000))
        perturbed = sampler.sample_cells(
            log_basal, delta.astype(np.float32), n_samples=cells_per_pert, seed=seed
        )
        perturbed = np.expm1(perturbed)
        np.clip(perturbed, a_min=0.0, a_max=None, out=perturbed)
        perturbed = np.rint(perturbed).astype(np.float32)

        if library_cap:
            totals = perturbed.sum(axis=1, keepdims=True)
            over = totals > library_cap
            if over.any():
                scale = np.where(over, library_cap / np.maximum(totals, 1.0), 1.0)
                perturbed = np.rint(perturbed * scale)

        blocks.append(sparse.csr_matrix(perturbed))
        obs_parts.append(
            pd.DataFrame(
                {
                    PERT_COL: [tgt] * cells_per_pert,
                    CONTEXT_COL: [context] * cells_per_pert,
                }
            )
        )

    X_pred = sparse.vstack(blocks, format="csr")
    obs = pd.concat(obs_parts, ignore_index=True)
    return X_pred, obs, used


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument("--atlas-src", type=Path, default=None)
    ap.add_argument("--replogle-src", type=Path, required=True)
    ap.add_argument(
        "--neighbor-map",
        type=Path,
        default=REPO / "experiments" / RUN_ID / "neighbor_map.json",
    )
    ap.add_argument("--out-dir", type=Path, default=REPO / "experiments" / RUN_ID)
    ap.add_argument("--contexts", default="A,B,C")
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-targets", type=int, default=0)
    ap.add_argument("--knockdown-efficiency", type=float, default=2.5)
    ap.add_argument("--attenuation-factor", type=float, default=0.5)
    ap.add_argument("--noise-scale", type=float, default=0.05)
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

    if not args.replogle_src.exists():
        print(f"missing replogle source {args.replogle_src}", file=sys.stderr)
        return 2
    if not args.neighbor_map.exists():
        print(f"missing neighbor map {args.neighbor_map}", file=sys.stderr)
        return 4

    real_deltas = build_combined_deltas(args.atlas_src, args.replogle_src, gene_order)

    neighbor_map = json.loads(args.neighbor_map.read_text())
    neighbor_deltas = build_neighbor_deltas(
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
        f"{len(neighbor_targets)} are otherwise uncovered: {neighbor_targets}",
        flush=True,
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
    totals = {"real": 0, "neighbor": 0, "fallback": 0}
    for ctx in contexts:
        ctrl_path = raw_dir / f"context_{ctx}.h5ad"
        if not ctrl_path.exists():
            print(f"missing {ctrl_path}", file=sys.stderr)
            return 3
        X_pred, obs, used = build_context_predictions(
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
    data_gb = adata.X.data.nbytes / 1e9
    print(
        f"[write] {pred_path} ({adata.shape[0]} x {adata.shape[1]}, "
        f"{adata.X.nnz / 1e6:.1f}M nnz, ~{data_gb:.2f} GB data) ...",
        flush=True,
    )
    adata.write_h5ad(str(pred_path), compression="gzip")

    meta = {
        "run_id": RUN_ID,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "replogle_prior+neighbor_imputation",
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
        "dispatch": totals,
        "imputed_targets": neighbor_targets,
        "knockdown_efficiency": args.knockdown_efficiency,
        "attenuation_factor": args.attenuation_factor,
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
    raise SystemExit(main())
