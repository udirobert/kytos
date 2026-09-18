"""Kytos k015 — 4-lineage essential-screen transfer learning.

Learns context-transfer maps (K562 -> Jurkat, K562 -> RPE1, K562 -> HepG2)
from the ~2,000 shared essential-screen targets, then applies the best map
to the 272 panel targets' K562 GWPS deltas.

Key advantage over k014 (47 Atlas pairs): 40-50x more training data, and
Jurkat is much closer to K562 (median cosine 0.466 vs hESC 0.13).

Data sources (all on /kytos-vol/refs/):
  k562_bulk.h5ad  — Replogle K562 essential screen (2,285 targets, bulk)
  rpe1_bulk.h5ad  — Replogle RPE1 essential screen (2,679 targets, bulk)
  jurkat.h5ad     — Nadig 2024 Jurkat essential screen (single-cell, ~263k cells)
  hepg2.h5ad      — Nadig 2024 HepG2 essential screen (single-cell)

Two modes:
  --mode evaluate: fit transfer models, report metrics (no submission)
  --mode apply:    apply best transfer to panel targets, build prediction.h5ad

Run on Modal: tools/modal_k015_essential_transfer.py
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
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

from perturbation_priors import (  # noqa: E402
    build_replogle_deltas_with_control,
    log1p_sparse,
)

RUN_ID = "k015-essential-transfer"
CONTROL_LABEL = "non-targeting"


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------


def extract_singlecell_deltas(
    path: Path, context_genes: list[str], min_cells: int = 10
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Extract per-target pseudobulk deltas from single-cell Nadig h5ad.

    Vectorized: builds an indicator matrix and computes all target means via
    a single sparse matmul, then subtracts the control mean.
    """
    print(f"[sc] loading {path.name} ...", flush=True)
    adata = ad.read_h5ad(str(path))
    n_cells_total, n_genes_src = adata.shape
    print(f"[sc] {path.name}: {n_cells_total} cells x {n_genes_src} genes", flush=True)

    # Find perturbation column: prefer plain gene-symbol columns. Nadig h5ad
    # files also contain composite sgID_AB / gene_transcript labels, which do
    # not match bare K562/RPE1 target symbols.
    ctrl_regex = "non.targeting|nontargeting|^neg|^nt$|^control|safe.target"
    preferred_cols = ["gene_name", "target_gene", "gene", "target", "perturbation", "pert"]
    pert_col = None
    for col in preferred_cols:
        if col not in adata.obs.columns:
            continue
        vals = adata.obs[col].astype(str)
        hits = vals.str.contains(ctrl_regex, case=False, regex=True)
        if hits.sum() > 0 and hits.mean() < 0.5:
            pert_col = col
            print(
                f"[sc] using preferred pert column '{col}': {hits.sum()} ctrl-like / "
                f"{vals.nunique()} unique",
                flush=True,
            )
            break
    if pert_col is None:
        for col in adata.obs.columns:
            vals = adata.obs[col].astype(str)
            hits = vals.str.contains(ctrl_regex, case=False, regex=True)
            frac = hits.mean()
            if hits.sum() > 0 and 0.001 < frac < 0.5:
                pert_col = col
                print(
                    f"[sc] fallback pert column '{col}': {hits.sum()} ctrl-like / "
                    f"{vals.nunique()} unique",
                    flush=True,
                )
                break
    if pert_col is None:
        idx = adata.obs.index.astype(str)
        hits = idx.str.contains(ctrl_regex, case=False, regex=True)
        if hits.sum() == 0:
            raise ValueError(f"{path.name}: cannot find perturbation column")
        adata.obs["_pert"] = adata.obs.index
        pert_col = "_pert"

    print(f"[sc] using obs['{pert_col}'] as perturbation label", flush=True)

    # Gene mapping
    if "gene_name" in adata.var.columns:
        src_genes = adata.var["gene_name"].astype(str).tolist()
    else:
        src_genes = adata.var.index.astype(str).tolist()
    gene_index = {g: i for i, g in enumerate(src_genes)}

    X_log = log1p_sparse(adata.X)
    if not sparse.issparse(X_log):
        X_log = sparse.csr_matrix(X_log)
    else:
        X_log = X_log.tocsr()

    labels = adata.obs[pert_col].astype(str).to_numpy()
    # Regex-based control detection matching common control labels
    ctrl_mask = pd.Series(labels).str.contains(ctrl_regex, case=False, regex=True).to_numpy()
    n_ctrl = int(ctrl_mask.sum())
    if n_ctrl == 0:
        raise ValueError(f"{path.name}: no control cells found")

    # Control mean (in source gene space)
    ctrl_mean_src = np.asarray(X_log[ctrl_mask].mean(axis=0)).ravel().astype(np.float32)

    # Unique perturbed targets
    pert_labels = labels[~ctrl_mask]
    unique_targets, inverse = np.unique(pert_labels, return_inverse=True)
    counts = np.bincount(inverse)
    keep = counts >= min_cells
    kept_targets = unique_targets[keep]
    kept_map = {t: i for i, t in enumerate(kept_targets)}
    X_pert = X_log[~ctrl_mask]

    n_kept = len(kept_targets)
    print(f"[sc] {n_kept} targets with >= {min_cells} cells ({n_ctrl} control cells)", flush=True)

    # Build indicator matrix (n_kept x n_pert_cells) for groupby-sum
    kept_cell_mask = np.isin(pert_labels, kept_targets)
    pert_labels_kept = pert_labels[kept_cell_mask]
    row_idx = np.array([kept_map[t] for t in pert_labels_kept], dtype=np.int64)
    col_idx = np.arange(int(kept_cell_mask.sum()), dtype=np.int64)
    indicator = sparse.csr_matrix(
        (np.ones(len(row_idx), dtype=np.float32), (row_idx, col_idx)),
        shape=(n_kept, int(kept_cell_mask.sum())),
    )
    X_kept = X_pert[kept_cell_mask]

    # Group sums: (n_kept, n_genes_src)
    group_sums = indicator @ X_kept
    group_counts = np.asarray(indicator.sum(axis=1)).ravel().astype(np.float32)
    group_counts[group_counts == 0] = 1.0

    # Map source gene indices -> context gene indices
    ctx_to_src = np.full(len(context_genes), -1, dtype=np.int64)
    for i, g in enumerate(context_genes):
        j = gene_index.get(g)
        if j is not None:
            ctx_to_src[i] = j
    valid_ctx = ctx_to_src >= 0
    src_cols = ctx_to_src[valid_ctx]

    # Extract only the mapped columns from group_sums (sparse column slice)
    group_means_src = (group_sums[:, src_cols].toarray() / group_counts[:, None]).astype(np.float32)
    ctrl_mean_mapped = ctrl_mean_src[src_cols].astype(np.float32)

    deltas_mapped = group_means_src - ctrl_mean_mapped[np.newaxis, :]

    # Assemble full-width delta matrix in context gene order. Normalize target
    # labels to bare uppercase symbols so they intersect the bulk K562/RPE1 keys.
    deltas: dict[str, np.ndarray] = {}
    for idx_t, tgt in enumerate(kept_targets):
        norm_tgt = str(tgt).strip().upper()
        if norm_tgt in deltas:
            continue
        full = np.zeros(len(context_genes), dtype=np.float32)
        full[valid_ctx] = deltas_mapped[idx_t]
        deltas[norm_tgt] = full

    # Control mapped to context order
    ctrl_mapped = np.zeros(len(context_genes), dtype=np.float32)
    ctrl_mapped[valid_ctx] = ctrl_mean_mapped

    n_skipped = int(len(unique_targets) - n_kept)
    print(
        f"[sc] {path.name}: {len(deltas)} targets extracted "
        f"({n_skipped} skipped < {min_cells} cells), {n_ctrl} control cells",
        flush=True,
    )
    return deltas, ctrl_mapped


def extract_bulk_deltas(
    path: Path, context_genes: list[str]
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Extract per-target deltas from Replogle-format bulk h5ad."""
    return build_replogle_deltas_with_control(str(path), context_genes)


# ---------------------------------------------------------------------------
# Transfer model fitting (vectorized, no LOO for large datasets)
# ---------------------------------------------------------------------------


def fit_and_evaluate(
    src_mat: np.ndarray,
    dst_mat: np.ndarray,
    basal_src: np.ndarray | None,
    basal_dst: np.ndarray | None,
    test_frac: float = 0.2,
    seed: int = 42,
    top_k: int = 200,
) -> dict:
    """Fit transfer models on train split, evaluate on test split."""
    rng = np.random.default_rng(seed)
    n = src_mat.shape[0]
    n_test = max(10, int(n * test_frac))
    perm = rng.permutation(n)
    test_idx = perm[:n_test]
    train_idx = perm[n_test:]

    src_train, dst_train = src_mat[train_idx], dst_mat[train_idx]
    src_test, dst_test = src_mat[test_idx], dst_mat[test_idx]

    results = {}

    # 1. Identity (no transfer)
    cos_id = _mean_cosine(src_test, dst_test, top_k)
    results["identity"] = cos_id

    # 2. Global scalar
    s_global = float((src_train * dst_train).sum() / ((src_train**2).sum() + 1e-8))
    cos_gs = _mean_cosine(s_global * src_test, dst_test, top_k)
    results["global_scalar"] = {"cosine": cos_gs, "s": s_global}

    # 3. Per-gene shrinkage
    den = (src_train**2).sum(axis=0)
    s_raw = (src_train * dst_train).sum(axis=0) / (den + 1e-8)
    tau = float(np.median(den))
    w = den / (den + tau + 1e-8)
    s_gene = s_global + w * (s_raw - s_global)
    pred_pgs = src_test * s_gene[np.newaxis, :]
    cos_pgs = _mean_cosine(pred_pgs, dst_test, top_k)
    results["per_gene_shrunk"] = {
        "cosine": cos_pgs,
        "s_gene_stats": {
            "mean": float(s_gene.mean()),
            "median": float(np.median(s_gene)),
            "std": float(s_gene.std()),
        },
    }

    # 4. Basal ratio modulation
    if basal_src is not None and basal_dst is not None:
        best_br = {"cosine": -1, "gamma": 0, "s": 1.0}
        for gamma in [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]:
            ratio = np.clip(basal_dst / np.maximum(basal_src, 1e-8), 0.25, 4.0) ** gamma
            mod_src_train = src_train * ratio[np.newaxis, :]
            s = float((mod_src_train * dst_train).sum() / ((mod_src_train**2).sum() + 1e-8))
            pred = s * src_test * ratio[np.newaxis, :]
            cos = _mean_cosine(pred, dst_test, top_k)
            if cos > best_br["cosine"]:
                best_br = {"cosine": cos, "gamma": gamma, "s": s}
        results["basal_ratio"] = best_br

    # 5. Low-rank linear map (fit on train, predict on test)
    # Compute SVD once at max rank; uncentered to match the validated config.
    _, _, vt_s = np.linalg.svd(src_train, full_matrices=False)
    _, _, vt_d = np.linalg.svd(dst_train, full_matrices=False)

    best_lr = {"cosine": -1, "rank": 16}
    for rank in [16, 32, 64, 128, 256]:
        try:
            basis_s = vt_s[:rank]
            basis_d = vt_d[:rank]
            src_proj = src_train @ basis_s.T
            dst_proj = dst_train @ basis_d.T
            W = np.linalg.solve(
                src_proj.T @ src_proj + 1.0 * np.eye(rank),
                src_proj.T @ dst_proj,
            )
            pred = (src_test @ basis_s.T) @ W @ basis_d
            cos = _mean_cosine(pred, dst_test, top_k)
            results[f"low_rank_{rank}"] = {"cosine": cos, "rank": rank}
            if cos > best_lr["cosine"]:
                best_lr = {"cosine": cos, "rank": rank}
        except Exception as e:
            results[f"low_rank_{rank}"] = {"cosine": float("nan"), "error": str(e)}

    return {
        "n_train": len(train_idx),
        "n_test": len(test_idx),
        "results": results,
        "best_low_rank": best_lr,
    }


def fit_lowrank_full(src_mat: np.ndarray, dst_mat: np.ndarray, rank: int) -> dict[str, np.ndarray]:
    """Refit the low-rank map on ALL pairs (no held-out split) for panel application."""
    _, _, vt_s = np.linalg.svd(src_mat, full_matrices=False)
    _, _, vt_d = np.linalg.svd(dst_mat, full_matrices=False)
    basis_s = vt_s[:rank].astype(np.float32)
    basis_d = vt_d[:rank].astype(np.float32)
    src_proj = src_mat @ basis_s.T
    dst_proj = dst_mat @ basis_d.T
    W = np.linalg.solve(
        src_proj.T @ src_proj + 1.0 * np.eye(rank),
        src_proj.T @ dst_proj,
    ).astype(np.float32)
    return {"basis_s": basis_s, "basis_d": basis_d, "W": W}


def _mean_cosine(pred: np.ndarray, true: np.ndarray, top_k: int = 200) -> float:
    """Mean cosine similarity, optionally restricted to top-k |true| genes per target."""
    cosines = []
    for i in range(len(pred)):
        p, t = pred[i], true[i]
        if top_k and top_k < len(t):
            top_idx = np.argsort(np.abs(t))[-top_k:]
            p, t = p[top_idx], t[top_idx]
        norm_p, norm_t = np.linalg.norm(p), np.linalg.norm(t)
        if norm_p < 1e-8 or norm_t < 1e-8:
            cosines.append(0.0)
        else:
            cosines.append(float(p @ t / (norm_p * norm_t)))
    return float(np.mean(cosines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument(
        "--k562-essential-src",
        type=Path,
        required=True,
        help="K562 essential screen bulk h5ad (Replogle)",
    )
    ap.add_argument(
        "--rpe1-essential-src",
        type=Path,
        required=True,
        help="RPE1 essential screen bulk h5ad (Replogle)",
    )
    ap.add_argument(
        "--jurkat-src",
        type=Path,
        required=True,
        help="Nadig Jurkat essential screen (single-cell) h5ad",
    )
    ap.add_argument(
        "--hepg2-src",
        type=Path,
        default=None,
        help="Nadig HepG2 essential screen (single-cell) h5ad",
    )
    ap.add_argument(
        "--replogle-gwps-src",
        type=Path,
        default=None,
        help="Replogle K562 GWPS bulk (for panel target deltas)",
    )
    ap.add_argument("--out-dir", type=Path, default=REPO / "experiments" / RUN_ID)
    ap.add_argument("--min-cells", type=int, default=10)
    ap.add_argument("--top-k", type=int, default=200)
    ap.add_argument("--test-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    t0 = time.time()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_order = pd.read_csv(args.raw_dir / "gene_names.csv", header=None, skiprows=1)[0].tolist()
    print(f"[init] {len(gene_order)} genes in context order", flush=True)

    # --- Extract deltas from essential screens ---
    print("\n=== Extracting essential-screen deltas ===", flush=True)

    k562_deltas, k562_ctrl = extract_bulk_deltas(args.k562_essential_src, gene_order)
    print(f"[k562-essential] {len(k562_deltas)} targets", flush=True)

    rpe1_deltas, rpe1_ctrl = extract_bulk_deltas(args.rpe1_essential_src, gene_order)
    print(f"[rpe1-essential] {len(rpe1_deltas)} targets", flush=True)

    jurkat_deltas, jurkat_ctrl = extract_singlecell_deltas(
        args.jurkat_src, gene_order, min_cells=args.min_cells
    )

    hepg2_deltas, hepg2_ctrl = None, None
    if args.hepg2_src and args.hepg2_src.exists():
        hepg2_deltas, hepg2_ctrl = extract_singlecell_deltas(
            args.hepg2_src, gene_order, min_cells=args.min_cells
        )

    # --- Build paired sets and evaluate transfer ---
    print("\n=== Transfer evaluation ===", flush=True)

    transfer_results = {}
    transfer_params = {}
    lowrank_fits: list[tuple[str, np.ndarray, np.ndarray, int]] = []

    # K562 -> Jurkat
    shared_kj = sorted(set(k562_deltas.keys()) & set(jurkat_deltas.keys()))
    if shared_kj:
        src_mat = np.stack([k562_deltas[t] for t in shared_kj]).astype(np.float32)
        dst_mat = np.stack([jurkat_deltas[t] for t in shared_kj]).astype(np.float32)
        print(f"\n--- K562 -> Jurkat ({len(shared_kj)} pairs) ---", flush=True)
        eval_result = fit_and_evaluate(
            src_mat,
            dst_mat,
            k562_ctrl,
            jurkat_ctrl,
            test_frac=args.test_frac,
            seed=args.seed,
            top_k=args.top_k,
        )
        transfer_results["K562_to_Jurkat"] = eval_result
        # Save per-gene shrinkage weights for application
        den = (src_mat**2).sum(axis=0)
        s_global = float((src_mat * dst_mat).sum() / ((src_mat**2).sum() + 1e-8))
        s_raw = (src_mat * dst_mat).sum(axis=0) / (den + 1e-8)
        tau = float(np.median(den))
        w = den / (den + tau + 1e-8)
        s_gene = s_global + w * (s_raw - s_global)
        transfer_params["K562_to_Jurkat"] = {
            "method": "per_gene_shrunk",
            "s_global": s_global,
            "s_gene": s_gene.tolist(),
        }
        for name, res in eval_result["results"].items():
            cos = res if isinstance(res, float) else res.get("cosine", float("nan"))
            print(f"  {name:<20} cosine={cos:.4f}", flush=True)
        best = eval_result["best_low_rank"]
        print(
            f"  best low-rank: rank={best['rank']} cosine={best['cosine']:.4f}",
            flush=True,
        )
        lowrank_fits.append(("k562_to_jurkat", src_mat, dst_mat, best["rank"]))

    # K562 -> RPE1
    shared_kr = sorted(set(k562_deltas.keys()) & set(rpe1_deltas.keys()))
    if shared_kr:
        src_mat = np.stack([k562_deltas[t] for t in shared_kr]).astype(np.float32)
        dst_mat = np.stack([rpe1_deltas[t] for t in shared_kr]).astype(np.float32)
        print(f"\n--- K562 -> RPE1 ({len(shared_kr)} pairs) ---", flush=True)
        eval_result = fit_and_evaluate(
            src_mat,
            dst_mat,
            k562_ctrl,
            rpe1_ctrl,
            test_frac=args.test_frac,
            seed=args.seed,
            top_k=args.top_k,
        )
        transfer_results["K562_to_RPE1"] = eval_result
        den = (src_mat**2).sum(axis=0)
        s_global = float((src_mat * dst_mat).sum() / ((src_mat**2).sum() + 1e-8))
        s_raw = (src_mat * dst_mat).sum(axis=0) / (den + 1e-8)
        tau = float(np.median(den))
        w = den / (den + tau + 1e-8)
        s_gene = s_global + w * (s_raw - s_global)
        transfer_params["K562_to_RPE1"] = {
            "method": "per_gene_shrunk",
            "s_global": s_global,
            "s_gene": s_gene.tolist(),
        }
        for name, res in eval_result["results"].items():
            cos = res if isinstance(res, float) else res.get("cosine", float("nan"))
            print(f"  {name:<20} cosine={cos:.4f}", flush=True)
        best = eval_result["best_low_rank"]
        print(
            f"  best low-rank: rank={best['rank']} cosine={best['cosine']:.4f}",
            flush=True,
        )
        lowrank_fits.append(("k562_to_rpe1", src_mat, dst_mat, best["rank"]))

    # K562 -> HepG2
    if hepg2_deltas:
        shared_kh = sorted(set(k562_deltas.keys()) & set(hepg2_deltas.keys()))
        if shared_kh:
            src_mat = np.stack([k562_deltas[t] for t in shared_kh]).astype(np.float32)
            dst_mat = np.stack([hepg2_deltas[t] for t in shared_kh]).astype(np.float32)
            print(f"\n--- K562 -> HepG2 ({len(shared_kh)} pairs) ---", flush=True)
            eval_result = fit_and_evaluate(
                src_mat,
                dst_mat,
                k562_ctrl,
                hepg2_ctrl,
                test_frac=args.test_frac,
                seed=args.seed,
                top_k=args.top_k,
            )
            transfer_results["K562_to_HepG2"] = eval_result
            den = (src_mat**2).sum(axis=0)
            s_global = float((src_mat * dst_mat).sum() / ((src_mat**2).sum() + 1e-8))
            s_raw = (src_mat * dst_mat).sum(axis=0) / (den + 1e-8)
            tau = float(np.median(den))
            w = den / (den + tau + 1e-8)
            s_gene = s_global + w * (s_raw - s_global)
            transfer_params["K562_to_HepG2"] = {
                "method": "per_gene_shrunk",
                "s_global": s_global,
                "s_gene": s_gene.tolist(),
            }
            for name, res in eval_result["results"].items():
                cos = res if isinstance(res, float) else res.get("cosine", float("nan"))
                print(f"  {name:<20} cosine={cos:.4f}", flush=True)
            best = eval_result["best_low_rank"]
            print(
                f"  best low-rank: rank={best['rank']} cosine={best['cosine']:.4f}",
                flush=True,
            )
            lowrank_fits.append(("k562_to_hepg2", src_mat, dst_mat, best["rank"]))

    # --- Save results ---
    report = {
        "run_id": RUN_ID,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_genes": len(gene_order),
        "sources": {
            "k562_essential": {"n_targets": len(k562_deltas)},
            "rpe1_essential": {"n_targets": len(rpe1_deltas)},
            "jurkat_essential": {"n_targets": len(jurkat_deltas)},
            "hepg2_essential": {"n_targets": len(hepg2_deltas) if hepg2_deltas else 0},
        },
        "paired_counts": {
            "K562_to_Jurkat": len(shared_kj) if shared_kj else 0,
            "K562_to_RPE1": len(shared_kr) if shared_kr else 0,
            "K562_to_HepG2": len(shared_kh) if hepg2_deltas and shared_kh else 0,
        },
        "transfer_results": transfer_results,
        "elapsed_s": round(time.time() - t0, 1),
    }
    report_path = out_dir / "transfer_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n[out] wrote {report_path}", flush=True)

    # Save transfer params (per-gene weights) for later application
    params_path = out_dir / "transfer_params.json"
    params_path.write_text(json.dumps(transfer_params) + "\n")
    print(f"[out] wrote {params_path} ({params_path.stat().st_size / 1e6:.1f} MB)", flush=True)

    # Save low-rank model params, refit on ALL pairs at the rank that won the
    # held-out evaluation, so panel application uses the full evidence base.
    lowrank_save = {}
    for prefix, src_mat, dst_mat, rank in lowrank_fits:
        model = fit_lowrank_full(src_mat, dst_mat, rank)
        lowrank_save[f"{prefix}_rank"] = np.array(rank)
        lowrank_save[f"{prefix}_basis_s"] = model["basis_s"]
        lowrank_save[f"{prefix}_basis_d"] = model["basis_d"]
        lowrank_save[f"{prefix}_W"] = model["W"]
    if lowrank_save:
        lowrank_path = out_dir / "lowrank_models.npz"
        np.savez_compressed(lowrank_path, **lowrank_save)
        print(
            f"[out] wrote {lowrank_path} ({lowrank_path.stat().st_size / 1e6:.1f} MB)",
            flush=True,
        )

    # Save the paired delta matrices for potential neural network training
    npz_path = out_dir / "essential_transfer_data.npz"
    npz_data = {"genes": np.array(gene_order)}
    if shared_kj:
        npz_data["k562_to_jurkat_src"] = np.stack([k562_deltas[t] for t in shared_kj])
        npz_data["k562_to_jurkat_dst"] = np.stack([jurkat_deltas[t] for t in shared_kj])
        npz_data["k562_to_jurkat_targets"] = np.array(shared_kj)
    if shared_kr:
        npz_data["k562_to_rpe1_src"] = np.stack([k562_deltas[t] for t in shared_kr])
        npz_data["k562_to_rpe1_dst"] = np.stack([rpe1_deltas[t] for t in shared_kr])
        npz_data["k562_to_rpe1_targets"] = np.array(shared_kr)
    npz_data["basal_k562"] = k562_ctrl
    npz_data["basal_jurkat"] = jurkat_ctrl
    npz_data["basal_rpe1"] = rpe1_ctrl
    np.savez_compressed(npz_path, **npz_data)
    print(f"[out] wrote {npz_path} ({npz_path.stat().st_size / 1e6:.1f} MB)", flush=True)

    print(f"\n[done] total time: {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
