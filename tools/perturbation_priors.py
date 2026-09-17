"""Helpers to build per-target perturbation deltas from public datasets."""

from __future__ import annotations

import anndata as ad
import numpy as np
from scipy import sparse

PERT_COL = "target_gene"
CONTROL_LABEL = "non-targeting"


def log1p_sparse(X: sparse.spmatrix | np.ndarray) -> sparse.spmatrix | np.ndarray:
    if sparse.issparse(X):
        X_log = X.copy()
        X_log.data = np.log1p(X_log.data)
        return X_log
    return np.log1p(np.asarray(X))


def build_atlas_deltas_with_control(
    atlas_path: str,
    context_genes: list[str],
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Atlas deltas plus the control log1p mean, both mapped to context gene order."""
    print(f"[atlas] loading {atlas_path} ...", flush=True)
    atlas = ad.read_h5ad(str(atlas_path))
    print(
        f"[atlas] loaded {atlas.shape[0]} cells x {atlas.shape[1]} genes; "
        f"obs cols: {list(atlas.obs.columns)}",
        flush=True,
    )
    if PERT_COL not in atlas.obs.columns:
        raise ValueError(f"{PERT_COL} not found in atlas.obs")

    X_log = log1p_sparse(atlas.X)
    atlas_genes = list(atlas.var.index)
    gene_index = {g: i for i, g in enumerate(atlas_genes)}

    obs = atlas.obs
    pert_col = obs[PERT_COL].to_numpy()
    control_mask = pert_col == CONTROL_LABEL
    control_mean = np.asarray(X_log[control_mask].mean(axis=0)).ravel()

    targets = sorted({str(t) for t in obs.loc[~control_mask, PERT_COL].unique()})
    deltas: dict[str, np.ndarray] = {}
    for tgt in targets:
        tgt_mask = pert_col == tgt
        tgt_mean = np.asarray(X_log[tgt_mask].mean(axis=0)).ravel()
        delta = tgt_mean - control_mean

        mapped = np.zeros(len(context_genes), dtype=np.float32)
        for i, g in enumerate(context_genes):
            idx = gene_index.get(g)
            if idx is not None:
                mapped[i] = delta[idx]
        deltas[tgt] = mapped

    control_mapped = np.zeros(len(context_genes), dtype=np.float32)
    for i, g in enumerate(context_genes):
        idx = gene_index.get(g)
        if idx is not None:
            control_mapped[i] = control_mean[idx]

    print(f"[atlas] built deltas for {len(deltas)} targets", flush=True)
    return deltas, control_mapped


def build_atlas_deltas(
    atlas_path: str,
    context_genes: list[str],
) -> dict[str, np.ndarray]:
    """Compute per-target log1p mean-shift deltas from the VCC 2025 validation set."""
    deltas, _ = build_atlas_deltas_with_control(atlas_path, context_genes)
    return deltas


def build_replogle_deltas_with_control(
    replogle_path: str,
    context_genes: list[str],
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Replogle deltas plus the control log1p mean, both mapped to context gene order."""
    print(f"[replogle] loading {replogle_path} ...", flush=True)
    adata = ad.read_h5ad(str(replogle_path))
    print(
        f"[replogle] loaded {adata.shape[0]} pseudobulks x {adata.shape[1]} genes",
        flush=True,
    )

    # obs index is gene_transcript like "0_A1BG_P1_ENSG00000121410"
    obs_index = adata.obs.index.astype(str)
    genes = obs_index.str.split("_").str[1].to_numpy()
    adata.obs["gene"] = genes

    # var has gene_name (symbol) and gene_id (Ensembl)
    var_genes = adata.var["gene_name"].astype(str).tolist()
    var_index = {g: i for i, g in enumerate(var_genes)}

    X_log = log1p_sparse(adata.X)

    control_mask = adata.obs["gene"].str.contains(CONTROL_LABEL, case=False).to_numpy()
    control_mean = np.asarray(X_log[control_mask].mean(axis=0)).ravel()

    targets = sorted({str(t) for t in adata.obs.loc[~control_mask, "gene"].unique()})
    deltas: dict[str, np.ndarray] = {}
    for tgt in targets:
        tgt_mask = adata.obs["gene"].to_numpy() == tgt
        tgt_mean = np.asarray(X_log[tgt_mask].mean(axis=0)).ravel()
        delta = tgt_mean - control_mean

        mapped = np.zeros(len(context_genes), dtype=np.float32)
        for i, g in enumerate(context_genes):
            idx = var_index.get(g)
            if idx is not None:
                mapped[i] = delta[idx]
        deltas[tgt] = mapped

    control_mapped = np.zeros(len(context_genes), dtype=np.float32)
    for i, g in enumerate(context_genes):
        idx = var_index.get(g)
        if idx is not None:
            control_mapped[i] = control_mean[idx]

    print(f"[replogle] built deltas for {len(deltas)} targets", flush=True)
    return deltas, control_mapped


def build_replogle_deltas(
    replogle_path: str,
    context_genes: list[str],
) -> dict[str, np.ndarray]:
    """Compute per-gene log1p mean-shift deltas from Replogle K562 GWPS bulk."""
    deltas, _ = build_replogle_deltas_with_control(replogle_path, context_genes)
    return deltas
