from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
REAL_PATH = VOLUME_ROOT / "atlas/adata_Validation.h5ad"
SOURCE_PATH = VOLUME_ROOT / "paired-transfer/paired_transfer_train.npz"

app = modal.App("kytos-k022-pipeline-audit")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "scipy==1.15.3",
        "pandas==2.2.3",
        "anndata==0.11.4",
        "h5py==3.13.0",
        "zarr==2.18.7",
    )
    .add_local_dir(LOCAL_ROOT / "src/kytos", str(REMOTE_ROOT / "src/kytos"), copy=True)
)
for filename in (
    "run_k022_pipeline_audit.py",
    "run_k007_neighbor_prior.py",
    "run_k006_replogle_prior.py",
    "run_k005_atlas_prior.py",
    "perturbation_priors.py",
):
    image = image.add_local_file(
        LOCAL_ROOT / "tools" / filename,
        str(REMOTE_ROOT / "tools" / filename),
        copy=True,
    )


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(32768, 32768),
    timeout=900,
    startup_timeout=120,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
)
def run_pilot(run_id: str) -> dict:
    import anndata as ad
    import numpy as np

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Use a new alphanumeric run ID (hyphens/underscores allowed)")
    for path in (REAL_PATH, SOURCE_PATH):
        if not path.is_file():
            raise FileNotFoundError(path)
    out = VOLUME_ROOT / "k022-pipeline-audit" / run_id
    out.mkdir(parents=True, exist_ok=False)
    real = ad.read_h5ad(REAL_PATH, backed="r")
    try:
        genes = real.var_names.astype(str).tolist()
        counts = real.obs["target_gene"].astype(str).value_counts()
        with np.load(SOURCE_PATH, allow_pickle=False) as source:
            source_genes = source["genes"].astype(str).tolist()
            source_targets = source["paired_targets"].astype(str).tolist()
            delta_shape = list(source["delta_k562"].shape)
            finite = bool(np.isfinite(source["delta_k562"]).all())
        shared = sorted(set(counts.index) & set(source_targets) - {"non-targeting"})
        selected = shared[:3]
        missing_genes = sorted(set(genes) - set(source_genes))
        # The axis audit (axis-20260921-01) ruled: Atlas-only duplicate-symbol
        # labels have no source counterpart and no stable IDs, so the
        # defensible resolution is a RECORDED drop. A large mismatch is a
        # different problem and still blocks.
        axis_drop_limit = 50
        axis_drop = missing_genes if len(missing_genes) <= axis_drop_limit else []
        blockers = []
        if (
            not real.obs_names.is_unique
            or len(set(genes)) != len(genes)
            or len(set(source_genes)) != len(source_genes)
            or len(set(source_targets)) != len(source_targets)
        ):
            blockers.append("non_unique_axes")
        if missing_genes and not axis_drop:
            blockers.append("source_gene_axis_incomplete")
        if delta_shape != [len(source_targets), len(source_genes)] or not finite:
            blockers.append("invalid_source_delta_matrix")
        if int(counts.get("non-targeting", 0)) < 3200:
            blockers.append("need_3200_disjoint_control_cells")
        if len(selected) < 3 or any(int(counts[t]) < 800 for t in selected):
            blockers.append("need_800_cells_for_each_of_first_three_shared_targets")
        preflight = {
            "run_id": run_id,
            "status": "blocked" if blockers else "ready",
            "blockers": blockers,
            "real_shape": list(real.shape),
            "source_delta_shape": delta_shape,
            "source_genes": len(source_genes),
            "missing_source_genes": missing_genes,
            "axis_resolution": (
                {
                    "rule": "drop_from_diagnostic_axis",
                    "dropped_labels": axis_drop,
                    "n_aligned_labels": len(genes) - len(axis_drop),
                }
                if axis_drop
                else None
            ),
            "shared_targets": shared,
            "pilot_targets": selected,
            "pilot_cell_counts": {t: int(counts[t]) for t in selected},
            "control_cells": int(counts.get("non-targeting", 0)),
            "sampling": {
                "cells_per_target": 400,
                "fit_controls": 1600,
                "eval_controls": 1600,
                "pool_k": 4,
                "seed": 0,
            },
            "official_score_computed": False,
        }
    finally:
        real.file.close()
    (out / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n")
    volume.commit()
    if blockers:
        return {"status": "blocked", "preflight": str(out / "preflight.json"), "blockers": blockers}
    command = [
        "python",
        str(REMOTE_ROOT / "tools/run_k022_pipeline_audit.py"),
        "--real-h5ad",
        str(REAL_PATH),
        "--source-npz",
        str(SOURCE_PATH),
        "--out-dir",
        str(out / "diagnostics"),
        "--cells",
        "400",
        "--controls",
        "1600",
        "--pool-k",
        "4",
        "--max-targets",
        "3",
        "--seed",
        "0",
        "--allow-large-input",
    ]
    if axis_drop:
        command += ["--allow-axis-drop"]
    with (out / "run.log").open("w") as log:
        try:
            result = subprocess.run(
                command,
                cwd=REMOTE_ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=780,
                check=False,
            )
        finally:
            log.flush()
            volume.commit()
    if result.returncode:
        raise RuntimeError(f"Diagnostic failed ({result.returncode}); see {out / 'run.log'}")
    return {
        "status": "completed",
        "summary": str(out / "diagnostics/summary.json"),
        "preflight": str(out / "preflight.json"),
        "official_score_computed": False,
    }


@app.local_entrypoint()
def main(run_id: str):
    print(json.dumps(run_pilot.remote(run_id), indent=2))
