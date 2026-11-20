"""k202 peek -- inspect an h5ad's obs/var structure on Modal (no compute).

Downloads the file if needed, prints obs columns, candidate pert/batch
columns with cardinalities, var axis, X dtype -- enough to pin catalog
spec fields before a real harvest.
"""

from __future__ import annotations

import modal

app = modal.App("kytos-k202-peek")

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "anndata==0.11.4",
    "h5py==3.13.0",
    "numpy==2.2.6",
    "pandas==2.2.3",
    "requests==2.32.4",
)


@app.function(image=image, memory=(16384, 16384), timeout=7200, ephemeral_disk=524288)
def peek(url: str, local_name: str = "/tmp/peek.h5ad") -> dict:
    import hashlib
    from pathlib import Path

    import anndata as ad
    import requests

    local = Path(local_name)
    digest = hashlib.sha256()
    if not local.exists():
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with local.open("wb") as fh:
                for chunk in r.iter_content(1024 * 1024 * 8):
                    fh.write(chunk)
                    digest.update(chunk)
    else:
        with local.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 26), b""):
                digest.update(chunk)

    adata = ad.read_h5ad(local, backed="r")
    try:
        obs = adata.obs
        info = {
            "sha256": digest.hexdigest(),
            "n_obs": int(adata.n_obs),
            "n_vars": int(adata.n_vars),
            "x_type": type(adata.X).__name__,
            "obs_cols": list(obs.columns),
            "var_cols": list(adata.var.columns),
            "obs_names_head": adata.obs_names[:5].tolist(),
            "var_names_head": adata.var_names[:5].tolist(),
            "cardinalities": {},
        }
        for c in obs.columns:
            try:
                u = obs[c].nunique()
                info["cardinalities"][c] = int(u) if u < 1e7 else "huge"
            except Exception:
                pass
        for c in (
            "gem_group",
            "batch",
            "sample",
            "gene",
            "perturbation",
            "condition",
            "target",
            "replicate",
            "donor",
        ):
            if c in obs.columns:
                vals = obs[c].astype(str)
                info.setdefault("sample_values", {})[c] = vals.value_counts().head(8).to_dict()
        return info
    finally:
        adata.file.close()


@app.local_entrypoint()
def main(url: str, local_name: str = "/tmp/peek.h5ad") -> None:
    import json

    print(json.dumps(peek.remote(url, local_name), indent=2))
