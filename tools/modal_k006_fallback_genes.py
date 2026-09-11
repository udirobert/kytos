"""Compute the k006 fallback target list — which 2026 targets had no real
signature in Replogle K562 GWPS or the 2025 Atlas.

Cheap Modal job (~30s): downloads the Replogle h5ad, reads the obs index,
and diffs against the 300-target list from pert_counts.csv (mounted from
the local repo since it's gitignored).

Run:
  modal run tools/modal_k006_fallback_genes.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import modal

app = modal.App("kytos-k006-fallback-genes")

REPLOGLE_URL = "https://ndownloader.figshare.com/files/35774443"

LOCAL_PERT_COUNTS = (
    Path(__file__).resolve().parent.parent / "data" / "raw" / "vcc2026" / "pert_counts.csv"
)


@app.function(
    image=modal.Image.debian_slim()
    .apt_install("curl")
    .pip_install("anndata", "pandas", "numpy", "scipy", "h5py")
    .add_local_file(LOCAL_PERT_COUNTS, remote_path="/mnt/pert_counts.csv"),
    timeout=60 * 20,
    memory=16 * 1024,
    cpu=2,
)
def compute_fallback() -> dict:
    subprocess.run(
        [
            "bash",
            "-c",
            "mkdir -p /root/replogle && curl -sL --fail -o "
            "/root/replogle/K562_gwps_raw_bulk_01.h5ad " + REPLOGLE_URL,
        ],
        check=True,
    )

    import anndata as ad
    import pandas as pd

    perts = pd.read_csv("/mnt/pert_counts.csv")
    targets_2026 = set(perts["target_gene"].astype(str))

    adata = ad.read_h5ad("/root/replogle/K562_gwps_raw_bulk_01.h5ad")
    replogle_genes = set(adata.obs.index.astype(str).str.split("_").str[1])
    replogle_genes = {g for g in replogle_genes if "non-targeting" not in g.lower()}

    covered = targets_2026 & replogle_genes
    fallback = sorted(targets_2026 - covered)

    return {
        "total_targets": len(targets_2026),
        "covered": len(covered),
        "fallback_count": len(fallback),
        "fallback_genes": fallback,
    }


@app.local_entrypoint()
def main():
    result = compute_fallback.remote()
    import json

    print(json.dumps(result, indent=2))
