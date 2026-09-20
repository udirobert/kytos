"""Metadata-only k022 gene-axis audit on the real artifacts (Modal).

Reads ONLY axis metadata — no expression matrix, no training, no scoring:

- ``adata_Validation.h5ad``  : var frame + var_names + obs target counts
- ``paired_transfer_train.npz`` : genes / paired_targets / delta shape
- ``delta_matrix_src.npz``   : targets / delta shape (records that it ships
  no explicit ``genes`` array — its column order is implicit)
- ``gene_names.csv``         : the 2026 reference axis, baked into the image

Writes ``axis_report.json`` to the Modal volume under
``k022-pipeline-audit/<run_id>/`` and prints it. The report PROPOSES
resolutions for uncovered consumer labels; nothing is mapped or dropped
silently (see tools/audit_gene_axis.py).

Run:
  modal run tools/modal_k022_axis_audit.py --run-id axis-YYYYMMDD-NN
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
REAL_PATH = VOLUME_ROOT / "atlas/adata_Validation.h5ad"
SOURCE_PATH = VOLUME_ROOT / "paired-transfer/paired_transfer_train.npz"
SRC_MATRIX_PATH = VOLUME_ROOT / "paired-transfer/delta_matrix_src.npz"
REMOTE_AXIS_CSV = REMOTE_ROOT / "data/vcc2026/gene_names.csv"

app = modal.App("kytos-k022-axis-audit")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "pandas==2.2.3",
        "anndata==0.11.4",
        "h5py==3.13.0",
        "zarr==2.18.7",
    )
    .add_local_file(
        LOCAL_ROOT / "tools/audit_gene_axis.py",
        str(REMOTE_ROOT / "tools/audit_gene_axis.py"),
        copy=True,
    )
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/gene_names.csv",
        str(REMOTE_AXIS_CSV),
        copy=True,
    )
)


@app.function(
    image=image,
    cpu=(2.0, 2.0),
    memory=(8192, 8192),
    timeout=600,
    startup_timeout=120,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
)
def run_axis_audit(run_id: str) -> dict:
    import sys

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import anndata as ad
    import numpy as np
    import pandas as pd

    import audit_gene_axis as axis

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Use a new alphanumeric run ID (hyphens/underscores allowed)")
    for path in (REAL_PATH, SOURCE_PATH, SRC_MATRIX_PATH):
        if not path.is_file():
            raise FileNotFoundError(path)

    real = ad.read_h5ad(REAL_PATH, backed="r")
    try:
        consumer_genes = real.var_names.astype(str).tolist()
        consumer_var = real.var.copy()
        target_counts = (
            real.obs["target_gene"].astype(str).value_counts().to_dict()
            if "target_gene" in real.obs.columns
            else None
        )
        obs_columns = [str(c) for c in real.obs.columns]
    finally:
        real.file.close()

    with np.load(SOURCE_PATH, allow_pickle=False) as source:
        source_genes = source["genes"].astype(str).tolist()
        paired_targets = source["paired_targets"].astype(str).tolist()
        source_delta_shape = list(source["delta_k562"].shape)
        source_keys = sorted(source.files)

    with np.load(SRC_MATRIX_PATH, allow_pickle=False) as src:
        src_keys = sorted(src.files)
        src_targets = src["targets"].astype(str).tolist() if "targets" in src.files else []
        src_delta_shape = list(src["deltas"].shape) if "deltas" in src.files else None
        src_has_gene_axis = "genes" in src.files

    reference_genes = pd.read_csv(REMOTE_AXIS_CSV).iloc[:, 0].astype(str).tolist()

    report = axis.build_report(
        consumer_genes,
        {SOURCE_PATH.name: source_genes},
        references={REMOTE_AXIS_CSV.name: reference_genes},
        consumer_var=consumer_var,
        consumer_name=REAL_PATH.name,
    )
    report["run_id"] = run_id
    report["real"] = {
        "path": str(REAL_PATH),
        "obs_columns": obs_columns,
        "target_counts_top10": (
            dict(sorted(target_counts.items(), key=lambda kv: -kv[1])[:10])
            if target_counts
            else None
        ),
        "control_cells": int(target_counts.get("non-targeting", 0)) if target_counts else None,
    }
    report["source_artifacts"] = {
        SOURCE_PATH.name: {
            "keys": source_keys,
            "n_paired_targets": len(paired_targets),
            "delta_k562_shape": source_delta_shape,
        },
        SRC_MATRIX_PATH.name: {
            "keys": src_keys,
            "n_targets": len(src_targets),
            "deltas_shape": src_delta_shape,
            "has_explicit_gene_axis": src_has_gene_axis,
            "contract_note": (
                "delta_matrix_src.npz stores targets+deltas but no 'genes' array; "
                "consumers assume the paired_transfer gene order — an implicit "
                "axis the audit flags for a future schema fix."
            ),
        },
    }

    out = VOLUME_ROOT / "k022-pipeline-audit" / run_id
    out.mkdir(parents=True, exist_ok=False)
    (out / "axis_report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    volume.commit()
    return {
        "status": "completed",
        "report_path": str(out / "axis_report.json"),
        "decision": report["decision"],
        "missing_from_source": report["missing_from_source"],
        "labels_without_source_mapping": report["labels_without_source_mapping"],
        "axis_report": report,
    }


@app.local_entrypoint()
def main(run_id: str):
    print(json.dumps(run_axis_audit.remote(run_id), indent=2))
