"""Inspect the 2025 Atlas validation h5ad on Modal and write a small JSON summary.

Run:
  modal run tools/modal_h1_val_inspect.py
  modal volume get kytos-vcc /h1-2025-train/val_inspect.json \
    experiments/h1-val-inspect/val_inspect.json --force
"""

from __future__ import annotations

import json
import subprocess

import modal

app = modal.App("kytos-h1-val-inspect")
vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

IMAGE = (
    modal.Image.debian_slim()
    .apt_install("curl", "git")
    .pip_install("anndata", "numpy", "pandas", "scipy", "h5py")
)

ATLAS_URL = (
    "https://storage.googleapis.com/arc-institute-virtual-cell-atlas/"
    "virtual-cell-challenge/2025/validation/adata_Validation.h5ad"
)
ATLAS_PATH = "/kytos-vol/atlas/adata_Validation.h5ad"
OUT_PATH = "/kytos-vol/h1-2025-train/val_inspect.json"


@app.function(
    image=IMAGE,
    volumes={"/kytos-vol": vol},
    timeout=60 * 30,
    cpu=4,
    memory=16384,
)
def inspect_validation() -> dict:
    import os

    import anndata as ad
    import pandas as pd

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    if not os.path.exists(ATLAS_PATH):
        subprocess.run(
            ["curl", "-L", "--fail", "--retry", "3", "-o", ATLAS_PATH, ATLAS_URL],
            check=True,
        )

    adata = ad.read_h5ad(ATLAS_PATH, backed="r")
    obs = adata.obs

    summary = {
        "n_obs": int(adata.n_obs),
        "n_vars": int(adata.n_vars),
        "obs_columns": list(obs.columns),
        "obsm_keys": list(adata.obsm.keys()) if hasattr(adata, "obsm") else [],
        "var_columns": list(adata.var.columns),
        "uns_keys": list(adata.uns.keys()) if hasattr(adata, "uns") else [],
    }

    for col in obs.columns:
        try:
            if pd.api.types.is_categorical_dtype(obs[col]) or obs[col].nunique() < 1000:
                vc = obs[col].value_counts(dropna=False)
                summary[f"counts_{col}"] = {str(k): int(v) for k, v in vc.head(100).items()}
                summary[f"nunique_{col}"] = int(obs[col].nunique())
        except Exception as exc:
            summary[f"error_{col}"] = str(exc)

    # If common columns exist, provide cross-tab snippets.
    for pert_col in ["target_gene", "perturbation", "pert", "condition"]:
        if pert_col in obs.columns:
            summary["pert_col_used"] = pert_col
            break

    if "target_gene" in obs.columns and "cell_line" in obs.columns:
        ct = pd.crosstab(obs["target_gene"], obs["cell_line"])
        summary["cell_line_by_target_shape"] = list(ct.shape)
        summary["cell_line_columns"] = list(ct.columns.astype(str))
        summary["target_sample"] = list(ct.index[:50].astype(str))

    with open(OUT_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    adata.file.close()
    vol.commit()
    print(json.dumps(summary, indent=2)[:10000], flush=True)
    return summary


@app.local_entrypoint()
def main():
    inspect_validation.remote()
