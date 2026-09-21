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
    "promoter_neighbor.py",
):
    image = image.add_local_file(
        LOCAL_ROOT / "tools" / filename,
        str(REMOTE_ROOT / "tools" / filename),
        copy=True,
    )


def _npz_schema(path):
    """Return (targets_key, deltas_key) for a source NPZ."""
    import numpy as np

    with np.load(path, allow_pickle=False) as data:
        if "paired_targets" in data.files and "delta_k562" in data.files:
            return "paired_targets", "delta_k562"
        if "targets" in data.files and "deltas" in data.files:
            return "targets", "deltas"
        raise ValueError(f"{path} lacks a recognized source schema")


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(32768, 32768),
    timeout=14400,
    startup_timeout=120,
    # Idempotent resume (summary.json marker) makes retries safe: a preempted
    # container restarts the deterministic diagnostic rather than corrupting
    # the run directory.
    retries=2,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
)
def run_pilot(
    run_id: str, max_targets: int = 3, source_npzs=None, promoter_pairs: str = ""
) -> dict:
    import anndata as ad
    import numpy as np

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Use a new alphanumeric run ID (hyphens/underscores allowed)")
    named_sources = {}
    for entry in source_npzs or [str(SOURCE_PATH)]:
        name, _, path = str(entry).partition("=")
        if not path:
            name, path = "default", name
        named_sources[name] = Path(path)
    pairs_path = Path(promoter_pairs) if promoter_pairs else None
    for path in [REAL_PATH, *named_sources.values(), *([pairs_path] if pairs_path else [])]:
        if not path.is_file():
            raise FileNotFoundError(path)
    out = VOLUME_ROOT / "k022-pipeline-audit" / run_id
    done_marker = out / "diagnostics" / "summary.json"
    if done_marker.is_file():
        # Idempotent restart: a previous attempt completed the diagnostic.
        return {
            "status": "completed",
            "summary": str(done_marker),
            "preflight": str(out / "preflight.json"),
            "official_score_computed": False,
            "resumed": True,
        }
    out.mkdir(parents=True, exist_ok=True)
    first_source = next(iter(named_sources.values()))
    real = ad.read_h5ad(REAL_PATH, backed="r")
    try:
        genes = real.var_names.astype(str).tolist()
        counts = real.obs["target_gene"].astype(str).value_counts()
        tkey, dkey = _npz_schema(first_source)
        with np.load(first_source, allow_pickle=False) as source:
            source_genes = source["genes"].astype(str).tolist()
            source_targets = source[tkey].astype(str).tolist()
            delta_shape = list(source[dkey].shape)
            finite = bool(np.isfinite(source[dkey]).all())
        source_genes_set = set(source_genes)
        all_source_targets = set(source_targets)
        for name, path in named_sources.items():
            tkey_i, _ = _npz_schema(path)
            with np.load(path, allow_pickle=False) as probe:
                if set(probe["genes"].astype(str).tolist()) != source_genes_set:
                    raise ValueError(
                        f"Source {name!r} has a different gene axis; all "
                        "sources in one run must share an axis"
                    )
                all_source_targets |= set(probe[tkey_i].astype(str).tolist())
        shared = sorted(set(counts.index) & all_source_targets - {"non-targeting"})
        selected = shared[:max_targets] if max_targets else shared
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
        underpowered = [t for t in selected if int(counts[t]) < 800]
        if int(counts.get("non-targeting", 0)) < 3200:
            blockers.append("need_3200_disjoint_control_cells")
        if len(selected) < 3 or any(t in underpowered for t in selected[:3]):
            blockers.append("need_800_cells_for_each_of_first_three_shared_targets")
        preflight = {
            "run_id": run_id,
            "status": "blocked" if blockers else "ready",
            "blockers": blockers,
            "sources": {name: str(path) for name, path in named_sources.items()},
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
            "targets_below_800_cells": underpowered,
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
        "--out-dir",
        str(out / "diagnostics"),
        "--cells",
        "400",
        "--controls",
        "1600",
        "--pool-k",
        "4",
        "--max-targets",
        str(max_targets),
        "--seed",
        "0",
        "--allow-large-input",
    ]
    for name, path in named_sources.items():
        command += ["--source-npz", f"{name}={path}"]
    if pairs_path is not None:
        command += ["--promoter-pairs", str(pairs_path)]
    if axis_drop:
        command += ["--allow-axis-drop"]
    # Each named source adds a full borrowed-transport pass per target, so the
    # diagnostic subprocess cost scales ~linearly in the number of arms.
    # The promoter prior adds one extra transport per sourced target plus a
    # standalone arm -- count it as +1 effective arm when present.
    n_arms = max(1, len(named_sources)) * (2 if pairs_path is not None else 1)
    n_arms += 1 if pairs_path is not None else 0
    subprocess_timeout = (780 if len(selected) <= 3 else 3300) * n_arms
    subprocess_timeout = min(subprocess_timeout, 13800)
    with (out / "run.log").open("w") as log:
        try:
            result = subprocess.run(
                command,
                cwd=REMOTE_ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=subprocess_timeout,
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
def main(run_id: str, max_targets: int = 3, source_npzs: str = "", promoter_pairs: str = ""):
    sources = [s for s in source_npzs.split(",") if s] or None
    print(json.dumps(run_pilot.remote(run_id, max_targets, sources, promoter_pairs), indent=2))
