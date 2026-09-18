"""Track 2 — Graph-smoothed deltas for improved perturbation predictions.

Instead of predicting deltas from scratch (which failed in k014/k016),
we denoise the existing K562 GWPS deltas using graph signal processing.

Approach:
  1. Build a gene co-expression graph from the K562 delta matrix
  2. For each target's delta vector, apply graph-based smoothing
  3. The smoothed deltas should have less noise → better nmae
  4. Optionally combine with sparsification for further improvement

The key insight: perturbation effects should be smooth on the gene
interaction graph. Genes that are co-expressed or functionally related
should have correlated perturbation responses. Smoothing enforces this.

Usage:
  python tools/track2/graph_smooth_deltas.py \
    --src-matrix /data/derived/delta_matrix_src.npz \
    --paired /data/derived/paired_transfer_train.npz \
    --out-dir /data/k016-graph-smooth \
    --n-neighbors 20 --smoothing-steps 3 --sparsity-k 500
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, diags

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

RUN_ID = "k016-graph-smooth"


def build_knn_graph(deltas: np.ndarray, n_neighbors: int = 20, min_corr: float = 0.1):
    """Build a KNN graph over genes based on correlation of their delta profiles.

    Args:
        deltas: (n_targets, n_genes) matrix of perturbation deltas
        n_neighbors: number of neighbors per gene
        min_corr: minimum correlation to include an edge

    Returns:
        adjacency: sparse adjacency matrix (n_genes, n_genes)
    """
    n_targets, n_genes = deltas.shape
    print(
        f"[graph] Building KNN graph: {n_genes} genes, {n_targets} targets, k={n_neighbors}",
        flush=True,
    )

    # Filter to genes with non-trivial variance (top 75%)
    gene_var = deltas.var(axis=0)
    var_threshold = np.percentile(gene_var, 25)
    active_mask = gene_var > var_threshold
    active_indices = np.where(active_mask)[0]
    n_active = len(active_indices)
    print(f"[graph] {n_active} genes with variance > {var_threshold:.6f}", flush=True)

    # Normalize active gene profiles
    active_deltas = deltas[:, active_indices]  # (n_targets, n_active)
    mean = active_deltas.mean(axis=0, keepdims=True)
    std = active_deltas.std(axis=0, keepdims=True) + 1e-8
    normalized = (active_deltas - mean) / std

    # Compute correlation matrix in chunks to manage memory
    # normalized is (n_targets, n_active), we want (n_active, n_active) correlation
    chunk_size = 2000
    rows, cols, vals = [], [], []

    for i_start in range(0, n_active, chunk_size):
        i_end = min(i_start + chunk_size, n_active)
        chunk = normalized[:, i_start:i_end]  # (n_targets, chunk_len)

        # Correlation of this chunk with all active genes
        corr_chunk = (chunk.T @ normalized) / n_targets  # (chunk_len, n_active)

        for local_i in range(corr_chunk.shape[0]):
            global_i = active_indices[i_start + local_i]
            corrs = corr_chunk[local_i].copy()
            corrs[i_start + local_i] = -1  # exclude self

            # Get top-k neighbors
            top_k_idx = np.argpartition(corrs, -n_neighbors)[-n_neighbors:]
            for j_local in top_k_idx:
                if corrs[j_local] > min_corr:
                    global_j = active_indices[j_local]
                    rows.append(global_i)
                    cols.append(global_j)
                    vals.append(corrs[j_local])

    # Make symmetric
    rows_sym = rows + cols
    cols_sym = cols + rows
    vals_sym = vals + vals

    adjacency = csr_matrix((vals_sym, (rows_sym, cols_sym)), shape=(n_genes, n_genes))
    # Remove duplicates by taking max
    adjacency = adjacency.maximum(adjacency.T)

    n_edges = adjacency.nnz // 2
    print(f"[graph] Built graph with {n_edges} undirected edges", flush=True)

    return adjacency


def graph_smooth(deltas: np.ndarray, adjacency: csr_matrix, n_steps: int = 3, alpha: float = 0.5):
    """Apply iterative graph smoothing to delta vectors.

    Uses the formula: x_new = (1-alpha) * x + alpha * (D^{-1} A x)
    This is a diffusion process on the graph.

    Args:
        deltas: (n_targets, n_genes) matrix
        adjacency: sparse adjacency matrix
        n_steps: number of smoothing iterations
        alpha: smoothing strength (0 = no smoothing, 1 = full neighbor average)

    Returns:
        smoothed: (n_targets, n_genes) smoothed delta matrix
    """

    # Compute degree-normalized adjacency
    degrees = np.array(adjacency.sum(axis=1)).flatten()
    degrees[degrees == 0] = 1  # avoid division by zero
    D_inv = diags(1.0 / degrees)
    norm_adj = D_inv @ adjacency  # Row-normalized adjacency

    smoothed = deltas.copy()
    for step in range(n_steps):
        # x_new = (1-alpha) * x + alpha * (norm_adj @ x)
        neighbor_avg = smoothed @ norm_adj.T  # (n_targets, n_genes)
        smoothed = (1 - alpha) * smoothed + alpha * neighbor_avg

    return smoothed


def sparsify_deltas(deltas: np.ndarray, top_k: int = 500):
    """Keep only top-K genes by absolute delta value for each target.

    Args:
        deltas: (n_targets, n_genes) matrix
        top_k: number of genes to keep per target

    Returns:
        sparse_deltas: (n_targets, n_genes) with only top-K entries per row
    """
    sparse_deltas = np.zeros_like(deltas)
    for i in range(deltas.shape[0]):
        top_indices = np.argsort(np.abs(deltas[i]))[-top_k:]
        sparse_deltas[i, top_indices] = deltas[i, top_indices]
    return sparse_deltas


def evaluate_against_paired(smoothed_deltas, target_names, paired_data, gene_names):
    """Evaluate smoothed deltas against paired hESC data."""
    paired_targets = paired_data["paired_targets"].tolist()
    paired_deltas_hesc = paired_data["delta_hesc"]  # hESC deltas
    paired_deltas_k562 = paired_data["delta_k562"]  # K562 deltas

    target_to_idx = {t: i for i, t in enumerate(target_names)}

    cosines_smooth = []
    cosines_raw = []

    for i, target in enumerate(paired_targets):
        if target not in target_to_idx:
            continue
        idx = target_to_idx[target]

        true_delta = paired_deltas_hesc[i]

        # Get smoothed and raw predictions
        smooth_pred = smoothed_deltas[idx]
        raw_pred = paired_deltas_k562[i]

        # Compute cosine similarity
        norm_s = np.linalg.norm(smooth_pred)
        norm_t = np.linalg.norm(true_delta)
        norm_r = np.linalg.norm(raw_pred)

        if norm_s > 1e-8 and norm_t > 1e-8:
            cos_s = np.dot(smooth_pred, true_delta) / (norm_s * norm_t)
            cosines_smooth.append(cos_s)

        if norm_r > 1e-8 and norm_t > 1e-8:
            cos_r = np.dot(raw_pred, true_delta) / (norm_r * norm_t)
            cosines_raw.append(cos_r)

    result = {
        "n_paired_eval": len(cosines_smooth),
        "mean_cosine_smoothed": float(np.mean(cosines_smooth)) if cosines_smooth else 0,
        "mean_cosine_raw": float(np.mean(cosines_raw)) if cosines_raw else 0,
        "improvement": float(np.mean(cosines_smooth) - np.mean(cosines_raw))
        if cosines_smooth and cosines_raw
        else 0,
    }
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src-matrix", type=Path, required=True)
    ap.add_argument("--paired", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=Path("/data/k016-graph-smooth"))
    ap.add_argument("--n-neighbors", type=int, default=20)
    ap.add_argument("--smoothing-steps", type=int, default=3)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument(
        "--sparsity-k",
        type=int,
        default=500,
        help="Top-K genes to keep per target (0 = no sparsification)",
    )
    ap.add_argument("--min-corr", type=float, default=0.1)
    args = ap.parse_args(argv)

    t0 = time.time()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    print("[data] Loading source matrix...", flush=True)
    src = np.load(args.src_matrix, allow_pickle=False)
    src_targets = src["targets"].tolist()
    src_deltas = src["deltas"].astype(np.float32)
    n_targets, n_genes = src_deltas.shape
    print(f"[data] {n_targets} targets x {n_genes} genes", flush=True)

    print("[data] Loading paired transfer data...", flush=True)
    paired = np.load(args.paired, allow_pickle=False)
    gene_names = paired["genes"].tolist()
    assert len(gene_names) == n_genes

    # Build graph
    adjacency = build_knn_graph(src_deltas, n_neighbors=args.n_neighbors, min_corr=args.min_corr)

    # Smooth deltas
    print(
        f"\n[smooth] Applying graph smoothing: steps={args.smoothing_steps}, alpha={args.alpha}",
        flush=True,
    )
    smoothed = graph_smooth(src_deltas, adjacency, n_steps=args.smoothing_steps, alpha=args.alpha)

    # Evaluate against paired data
    print("\n[eval] Evaluating against paired hESC data...", flush=True)
    eval_result = evaluate_against_paired(smoothed, src_targets, paired, gene_names)
    print(f"  Raw K562 cosine: {eval_result['mean_cosine_raw']:.4f}")
    print(f"  Smoothed cosine: {eval_result['mean_cosine_smoothed']:.4f}")
    print(f"  Improvement: {eval_result['improvement']:.4f}")

    # Apply sparsification if requested
    if args.sparsity_k > 0:
        print(f"\n[sparsify] Keeping top {args.sparsity_k} genes per target", flush=True)
        smoothed_sparse = sparsify_deltas(smoothed, top_k=args.sparsity_k)

        # Evaluate sparse version too
        eval_sparse = evaluate_against_paired(smoothed_sparse, src_targets, paired, gene_names)
        print(f"  Sparse smoothed cosine: {eval_sparse['mean_cosine_smoothed']:.4f}")
        eval_result["sparse_cosine"] = eval_sparse["mean_cosine_smoothed"]
    else:
        smoothed_sparse = smoothed

    # Save smoothed deltas
    print("\n[save] Saving smoothed deltas...", flush=True)
    np.savez_compressed(
        args.out_dir / "smoothed_deltas.npz",
        targets=np.array(src_targets),
        deltas=smoothed.astype(np.float32),
        genes=np.array(gene_names),
    )

    if args.sparsity_k > 0:
        np.savez_compressed(
            args.out_dir / "smoothed_sparse_deltas.npz",
            targets=np.array(src_targets),
            deltas=smoothed_sparse.astype(np.float32),
            genes=np.array(gene_names),
        )

    # Save report
    report = {
        "run_id": RUN_ID,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_targets": n_targets,
        "n_genes": n_genes,
        "n_edges": int(adjacency.nnz // 2),
        "config": {
            "n_neighbors": args.n_neighbors,
            "smoothing_steps": args.smoothing_steps,
            "alpha": args.alpha,
            "sparsity_k": args.sparsity_k,
            "min_corr": args.min_corr,
        },
        "eval": eval_result,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (args.out_dir / "report.json").write_text(json.dumps(report, indent=2))

    print(f"\n[done] Total time: {time.time() - t0:.1f}s")
    print(f"[done] Results saved to {args.out_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
