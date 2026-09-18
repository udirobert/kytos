"""Modal job: download 2025 H1 training h5ad and extract per-target deltas.

The 2025 H1 training set has 150 targets (vs 47 in validation). This gives
much richer paired data for learning context-C (hESC-like) transfer maps.

Output persisted to /kytos-vol/h1-2025-train/:
  h1_train_deltas.npz   - per-target log1p pseudobulk deltas vs non-targeting
  h1_train_meta.json    - target list, cell counts, gene axis info

Run:
  modal run tools/modal_h1_train_extract.py
  modal run tools/modal_h1_train_extract.py::extract_h1_train_deltas
"""

from __future__ import annotations

import json
import subprocess
import time

import modal

app = modal.App("kytos-h1-train-extract")
vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

H1_TRAIN_URL = (
    "https://storage.googleapis.com/arc-institute-virtual-cell-atlas/"
    "virtual-cell-challenge/2025/train/adata_Training.h5ad?generation=1765904883947296"
)
OUT_VOL_DIR = "/kytos-vol/h1-2025-train"


@app.function(
    image=modal.Image.debian_slim()
    .apt_install("curl", "ca-certificates")
    .pip_install("anndata", "numpy", "pandas", "scipy", "h5py"),
    timeout=60 * 60 * 4,
    memory=64 * 1024,
    cpu=8,
    volumes={"/kytos-vol": vol},
)
def extract_h1_train_deltas(
    min_cells: int = 10,
    pseudobulk_chunk: int = 4096,
) -> dict:
    """Download H1 training h5ad, compute per-target pseudobulk deltas, persist."""
    import os

    import anndata as ad
    import numpy as np
    import pandas as pd
    from scipy import sparse

    t0 = time.time()
    os.makedirs(OUT_VOL_DIR, exist_ok=True)
    # Download directly to the volume so the 15.5 GB file persists and does not
    # rely on ephemeral disk space.
    h5ad_path = f"{OUT_VOL_DIR}/adata_Training.h5ad"

    if os.path.exists(h5ad_path):
        print(f"[cache] using existing volume file: {h5ad_path}", flush=True)
    else:
        print("[download] fetching H1 training h5ad (~15.5 GB) to volume...", flush=True)
        subprocess.run(
            [
                "curl",
                "-L",
                "--fail",
                "--retry",
                "3",
                "--retry-all-errors",
                "--connect-timeout",
                "30",
                "-o",
                h5ad_path,
                H1_TRAIN_URL,
            ],
            check=True,
        )
        print(f"[download] done: {os.path.getsize(h5ad_path) / 1e9:.2f} GB", flush=True)

    print("[load] reading h5ad in backed mode...", flush=True)
    adata = ad.read_h5ad(h5ad_path, backed="r")
    print(f"[load] shape: {adata.shape}", flush=True)

    # Identify target column
    obs_cols = list(adata.obs.columns)
    print(f"[obs] columns: {obs_cols}", flush=True)

    target_col = None
    for candidate in ["target_gene", "gene", "perturbation", "pert", "target"]:
        if candidate in obs_cols:
            target_col = candidate
            break
    if target_col is None:
        # Fallback: look for column with many unique gene-like values
        for col in obs_cols:
            nunique = adata.obs[col].nunique()
            if nunique > 50:
                target_col = col
                break
    if target_col is None:
        raise ValueError(f"Could not identify target column in obs: {obs_cols}")

    print(f"[targets] using column: {target_col}", flush=True)
    labels = adata.obs[target_col].astype(str).to_numpy()
    genes = adata.var_names.astype(str).to_numpy()

    # Find control label
    control_label = None
    candidates = [
        "non-targeting",
        "Non-Targeting",
        "control",
        "NT",
        "non_targeting",
        "nontargeting",
    ]
    for cand in candidates:
        if cand in set(labels):
            control_label = cand
            break
    if control_label is None:
        # Use most frequent label as control
        vc = pd.Series(labels).value_counts()
        control_label = vc.index[0]
        print(f"[control] inferred as most frequent: {control_label}", flush=True)
    else:
        print(f"[control] found: {control_label}", flush=True)

    unique_targets = sorted(set(labels) - {control_label})
    print(f"[targets] {len(unique_targets)} unique targets (excl control)", flush=True)

    # Compute pseudobulk control first
    ctrl_mask = labels == control_label
    ctrl_idx = np.flatnonzero(ctrl_mask)
    print(f"[control] {len(ctrl_idx)} control cells", flush=True)

    ctrl_sum = np.zeros(len(genes), dtype=np.float64)
    for left in range(0, len(ctrl_idx), pseudobulk_chunk):
        chunk = ctrl_idx[left : left + pseudobulk_chunk]
        x = sparse.csr_matrix(adata.X[chunk])
        ctrl_sum += np.asarray(x.sum(axis=0)).ravel()
    ctrl_mean = ctrl_sum / max(len(ctrl_idx), 1)
    ctrl_log1p = np.log1p(ctrl_mean)

    # Compute per-target pseudobulk deltas
    deltas = {}
    target_cell_counts = {}
    skipped = []

    for ti, target in enumerate(unique_targets):
        t_mask = labels == target
        t_idx = np.flatnonzero(t_mask)
        n_cells = len(t_idx)
        if n_cells < min_cells:
            skipped.append((target, n_cells))
            continue

        t_sum = np.zeros(len(genes), dtype=np.float64)
        for left in range(0, n_cells, pseudobulk_chunk):
            chunk = t_idx[left : left + pseudobulk_chunk]
            x = sparse.csr_matrix(adata.X[chunk])
            t_sum += np.asarray(x.sum(axis=0)).ravel()

        t_mean = t_sum / n_cells
        t_log1p = np.log1p(t_mean)
        delta = t_log1p - ctrl_log1p
        deltas[target] = delta.astype(np.float32)
        target_cell_counts[target] = n_cells

        if (ti + 1) % 25 == 0:
            print(f"[deltas] {ti + 1}/{len(unique_targets)} targets processed", flush=True)

    adata.file.close()

    print(
        f"[deltas] extracted {len(deltas)} targets, "
        f"skipped {len(skipped)} with < {min_cells} cells",
        flush=True,
    )

    # Save to volume
    os.makedirs(OUT_VOL_DIR, exist_ok=True)
    out_npz = f"{OUT_VOL_DIR}/h1_train_deltas.npz"
    np.savez_compressed(
        out_npz,
        genes=np.asarray(genes),
        targets=np.asarray(list(deltas.keys())),
        deltas=np.stack(list(deltas.values())),  # shape (n_targets, n_genes)
        n_cells=np.array([target_cell_counts[t] for t in deltas], dtype=np.int32),
        control_log1p=ctrl_log1p.astype(np.float32),
    )

    meta = {
        "source": "2025 H1 training set",
        "url": H1_TRAIN_URL,
        "n_targets_extracted": len(deltas),
        "n_targets_skipped_low_cells": len(skipped),
        "skipped_examples": skipped[:20],
        "n_genes": len(genes),
        "control_label": control_label,
        "control_n_cells": int(len(ctrl_idx)),
        "min_cells": min_cells,
        "total_h5ad_shape": list(adata.shape),
        "target_column": target_col,
        "elapsed_s": time.time() - t0,
    }
    out_meta = f"{OUT_VOL_DIR}/h1_train_meta.json"
    with open(out_meta, "w") as f:
        json.dump(meta, f, indent=2)

    vol.commit()
    print(f"[done] saved to {OUT_VOL_DIR}, elapsed {time.time() - t0:.1f}s", flush=True)
    return meta


@app.local_entrypoint()
def main(min_cells: int = 10):
    result = extract_h1_train_deltas.remote(min_cells=min_cells)
    print(json.dumps(result, indent=2))
