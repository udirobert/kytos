"""k025 — Gate B closure: production-equivalent scoring on 2025 validation.

Runs the pinned ``cell-eval2`` (vcc2026 preset, rev 5e64833, pdex CPU)
``run → baseline → prep-real-bundle → score`` chain on REAL 2025-validation
data (``atlas/adata_Validation.h5ad``, hESC) against candidate predictions
generated through the actual production transport path
(``build_context_predictions``: HeterogeneousTransportSampler kd_std=2.0,
library_cap="median", 400 cells/pert).

Purpose: the k022 diagnostic optimizes a delta-cosine proxy that has
repeatedly diverged from leaderboard outcomes (k017→k018, k020). This gate
measures the six official metrics directly, offline, without spending a
submission slot.

Variants (identical control substrate + seeds):
  null                 zero deltas — transport floor
  k562_ds1p7           honest Replogle K562 deltas, champion scale 1.7
  k562_ds1p0           same deltas at scale 1.0 (amplitude sensitivity)
  consensus_w_ctr      2:1:1:1 consensus + common-response centering, ds 1.7
  k562_ds1p7_pncap     k562 scaled then capped at the promoter-neighbor
                       ceiling (k024 prior, neighbor positions only)
  cons_w_ctr_pncap     same cap on the consensus arm
  oracle_hesc          in-context measured hESC delta, ds 1.0 — pseudo-
                       ceiling anchor; LEAKED BY CONSTRUCTION, recorded for
                       interpretation only, never a promotion candidate

Outputs under ``/kytos-vol/k025-eval2-gate/<run_id>/``:
  ``real_eval2.h5ad``, ``controls_eval2.h5ad``, per-variant ``pred_<v>.h5ad``,
  ``run_<v>/`` results, ``bundle/``, ``scored_<v>.csv``, ``results.json``.

Run:
  modal run tools/modal_k025_eval2_gate.py --run-id gate-YYYYMMDD-NN
"""

from __future__ import annotations

import re
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
ATLAS_PATH = VOLUME_ROOT / "atlas/adata_Validation.h5ad"
PAIRED_PATH = VOLUME_ROOT / "paired-transfer/paired_transfer_train.npz"
VARIANTS_DIR = VOLUME_ROOT / "k023-consensus/extract-20260921-02-honest/variants"
PAIRS_PATH = VOLUME_ROOT / "k024-promoter-prior/pairs-20260921-01/promoter_pairs.csv"
OUT_ROOT = VOLUME_ROOT / "k025-eval2-gate"

CELL_EVAL2_GIT = (
    "cell-eval2 @ git+https://github.com/ArcInstitute/cell-eval2"
    "@5e64833518a6603a0301cbe28185d49c30f4a986"
)

app = modal.App("kytos-k025-eval2-gate")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .pip_install(
        # Let pip resolve the scientific stack against cell-eval2's deps --
        # strict pins conflicted. Mirrors .venv-eval2 resolution.
        CELL_EVAL2_GIT,
        "pdex==0.3.0",
        "anndata",
        "numpy",
        "scipy",
        "pandas",
        "h5py",
    )
    .add_local_dir(LOCAL_ROOT / "src/kytos", str(REMOTE_ROOT / "src/kytos"), copy=True)
)
for filename in (
    "run_k005_atlas_prior.py",
    "run_k006_replogle_prior.py",
    "run_k007_neighbor_prior.py",
    "perturbation_priors.py",
    "promoter_neighbor.py",
):
    image = image.add_local_file(
        LOCAL_ROOT / "tools" / filename,
        str(REMOTE_ROOT / "tools" / filename),
        copy=True,
    )


def _clean(o):
    """NaN -> None so payloads serialize (json allow_nan=False)."""
    import math

    if isinstance(o, float) and math.isnan(o):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def _load_variant_deltas(npz_path, axis_symbols):
    """Return {target: delta} reindexed onto ``axis_symbols`` (0-fill miss)."""
    import numpy as np

    with np.load(npz_path, allow_pickle=False) as data:
        genes = data["genes"].astype(str).tolist()
        targets = data["targets"].astype(str).tolist()
        deltas = data["deltas"] if "deltas" in data.files else data["delta_k562"]
        tkey = targets
    pos = {g: i for i, g in enumerate(genes)}
    col = np.array([pos.get(g, -1) for g in axis_symbols])
    out = {}
    for i, t in enumerate(tkey):
        row = np.zeros(len(axis_symbols), dtype=np.float32)
        keep = col >= 0
        row[keep] = deltas[i, col[keep]]
        out[t] = row
    return out


def _oracle_deltas(paired_path, axis_symbols):
    """In-context hESC deltas (LEAKED — anchor only) on the real axis."""
    import numpy as np

    with np.load(paired_path, allow_pickle=False) as data:
        genes = data["genes"].astype(str).tolist()
        targets = data["paired_targets"].astype(str).tolist()
        deltas = data["delta_hesc"]
    pos = {g: i for i, g in enumerate(genes)}
    col = np.array([pos.get(g, -1) for g in axis_symbols])
    out = {}
    for i, t in enumerate(targets):
        row = np.zeros(len(axis_symbols), dtype=np.float32)
        keep = col >= 0
        row[keep] = deltas[i, col[keep]]
        out[t] = row
    return out


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(65536, 65536),
    timeout=21600,
    startup_timeout=300,
    retries=1,
    max_containers=1,
    volumes={str(VOLUME_ROOT): volume},
)
def run_gate(run_id: str, cells_per_pert: int = 400, seed: int = 0, bundle_src: str = "") -> dict:
    import json
    import subprocess
    import sys
    import tempfile
    import time

    import anndata as ad
    import numpy as np
    import pandas as pd
    from scipy import sparse

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    sys.path.insert(0, str(REMOTE_ROOT / "src"))
    import run_k007_neighbor_prior as k007
    from kytos.models.dual_moment import build_prediction_dual_moment
    from kytos.models.layer_a import ContextConditionedTransfer
    from kytos.models.layer_b import HeterogeneousTransportSampler

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Use a new alphanumeric run ID (hyphens/underscores allowed)")
    out = OUT_ROOT / run_id
    done = out / "results.json"
    if done.exists():
        return {"status": "completed", "results": str(done), "resumed": True}
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    real = ad.read_h5ad(ATLAS_PATH, backed="r")
    axis_symbols = real.var_names.astype(str).tolist()
    with np.load(PAIRED_PATH, allow_pickle=False) as paired:
        eval_targets = paired["paired_targets"].astype(str).tolist()
    labels = real.obs["target_gene"].astype(str)
    keep_mask = labels.isin(set(eval_targets) | {"non-targeting"})
    keep_idx = np.flatnonzero(keep_mask.to_numpy())
    print(f"real subset: {len(keep_idx)} cells on {len(axis_symbols)} genes", flush=True)

    work = Path(tempfile.mkdtemp(prefix="k025-"))
    real_path = work / "real_eval2.h5ad"
    real_sub = real[keep_idx].to_memory()
    real_sub.write_h5ad(real_path, compression="gzip")

    ctrl_idx = np.flatnonzero((labels == "non-targeting").to_numpy())
    controls = real[ctrl_idx].to_memory()
    ctrl_path = work / "controls_eval2.h5ad"
    controls.write_h5ad(ctrl_path, compression="gzip")
    real.file.close()
    del real

    cons_eb2 = _load_variant_deltas(VARIANTS_DIR / "variant_consensus_eb2_ctr.npz", axis_symbols)

    # arm spec: deltas -> gen "transport" (kd_std, delta_scale) or "dm"
    # (dual_moment amplitude, bulk_amplitude, pool_k, space).
    # gate-20260921-01 covered null/k562_ds1p{0,7}/consensus_w_ctr/*_pncap/
    # oracle at kd_std=2.0. gate-20260922-02 swept kd_std, dual-moment
    # amplitude {0.6,1.0}, and the consensus recipe axis.
    # Round 4 (Track 2b stage 0): CollecTRI signed regulon overlay on
    # consensus deltas, through dual-moment a1.0/b0.5. reg3/reg8 add the
    # regulon row scaled to w*||delta_cons||; regonly replaces the delta on
    # TF targets entirely. Only TF targets with CollecTRI edges change.
    # Round 6: consensus_eb (gamma=1) scored 0.1969 vs ref 0.1913.
    # Round 7: LOLO showed harder shrinkage monotone-better through gamma=4;
    # gate eb2 and eb4 at the same dm config.
    variants = {
        # round 8: compose the two independent winners — eb2 deltas with
        # the pk12/b0.3 generation config (round-5 best arm).
        "cons_eb2_dm_pk12": {
            "deltas": cons_eb2,
            "gen": "dm",
            "dm_amp": 1.0,
            "dm_bulk_amp": 0.3,
            "dm_pool_k": 12,
        },
    }

    rng = np.random.default_rng(seed)
    pred_paths = {}
    for name, spec in variants.items():
        pred_path = out / f"pred_{name}.h5ad"
        if not pred_path.exists():
            if spec.get("gen") == "dm":
                x = build_prediction_dual_moment(
                    controls,
                    spec["deltas"],
                    eval_targets,
                    axis_symbols,
                    cells_per_pert,
                    amplitude=spec["dm_amp"],
                    bulk_amplitude=spec["dm_bulk_amp"],
                    pool_k=spec.get("dm_pool_k", 4),
                    seed=seed,
                    space=spec.get("dm_space", "bulk_delta"),
                )
                obs = pd.DataFrame(
                    {
                        "target_gene": np.repeat(eval_targets, cells_per_pert),
                        "context": "eval",
                    }
                )
                used = {"real": len(eval_targets)}
            else:
                x, obs, used = k007.build_context_predictions(
                    "eval",
                    ctrl_path,
                    eval_targets,
                    axis_symbols,
                    cells_per_pert,
                    rng,
                    spec["deltas"],
                    {},
                    ContextConditionedTransfer(),
                    HeterogeneousTransportSampler(noise_scale=0.05, kd_std=spec["kd_std"]),
                    library_cap="median",
                    delta_scale=spec["scale"],
                )
            # append unperturbed control cells so the pred file carries the
            # non-targeting reference the scorer expects
            n_ctrl = min(800, controls.n_obs)
            cidx = rng.choice(controls.n_obs, size=n_ctrl, replace=False)
            x = sparse.vstack([x, controls.X[cidx]], format="csr").astype(np.int32)
            obs = pd.concat(
                [
                    obs,
                    pd.DataFrame(
                        {
                            "target_gene": ["non-targeting"] * n_ctrl,
                            "context": ["eval"] * n_ctrl,
                        }
                    ),
                ],
                ignore_index=True,
            )
            pred = ad.AnnData(x, obs=obs, var=real_sub.var)
            pred.write_h5ad(pred_path, compression="gzip")
            print(f"[{name}] pred written: {x.shape}, dispatch {used}", flush=True)
        pred_paths[name] = pred_path
        volume.commit()

    def cell_eval2(*args):
        cmd = ["cell-eval2", *[str(a) for a in args]]
        print("$ " + " ".join(cmd), flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"cell-eval2 failed: {result.stderr[-2000:]}")
        return result

    baseline_dir = out / "baseline"
    bundle_dir = out / "bundle"
    anchor_dir = out / "anchors"
    if bundle_src:
        # Reuse a previously built real bundle (same real subset
        # construction is deterministic). Skips the ~3h prep-real-bundle.
        bundle_dir = Path(bundle_src)
        print(f"[bundle] reusing {bundle_dir}", flush=True)
        src_anchors = bundle_dir.parent / "anchors"
        if not anchor_dir.exists() and src_anchors.exists():
            anchor_dir.mkdir(parents=True, exist_ok=True)
            for f in src_anchors.glob("*_agg.csv"):
                (anchor_dir / f.name).write_bytes(f.read_bytes())
    else:
        if not (baseline_dir / "baseline_pred.h5ad").exists():
            cell_eval2(
                "baseline",
                "-ar",
                real_path,
                "--save-pred",
                baseline_dir / "baseline_pred.h5ad",
                "--preset",
                "vcc2026",
                "--pert-col",
                "target_gene",
                "-o",
                baseline_dir,
            )
            volume.commit()
        if not bundle_dir.exists() or not list(bundle_dir.glob("*")):
            cell_eval2(
                "prep-real-bundle",
                "--real",
                real_path,
                "--baseline",
                baseline_dir / "baseline_pred.h5ad",
                "--preset",
                "vcc2026",
                "--pert-col",
                "target_gene",
                "--anchor-splits",
                "5",
                "-o",
                bundle_dir,
            )
            volume.commit()

        # Real-data anchors: disjoint self-split ceiling + split-half
        # LFC-NMAE reference. Real-only mode (no -ap), computed once.
        if not (anchor_dir / "ceiling_agg.csv").exists():
            cell_eval2(
                "run",
                "-ar",
                real_path,
                "--preset",
                "vcc2026",
                "--pert-col",
                "target_gene",
                "--ceiling",
                "--lfc-nmae-ref",
                "-o",
                anchor_dir,
            )
            volume.commit()

    results = {}
    for name in variants:
        run_dir = out / f"run_{name}"
        if not (run_dir / "agg_results.csv").exists():
            cell_eval2(
                "run",
                "-ap",
                pred_paths[name],
                "-ar",
                real_path,
                "--preset",
                "vcc2026",
                "--pert-col",
                "target_gene",
                "-o",
                run_dir,
            )
            volume.commit()
        scored = out / f"scored_{name}.csv"
        if not scored.exists():
            cell_eval2(
                "score",
                "--user-agg",
                run_dir / "agg_results.csv",
                "--real-bundle",
                bundle_dir,
                "-o",
                scored,
            )
            volume.commit()
        agg = pd.read_csv(run_dir / "agg_results.csv")
        score_df = pd.read_csv(scored)
        results[name] = {
            "agg": _clean(agg.to_dict("records")),
            "scored": _clean(score_df.to_dict("records")),
        }
        print(f"[{name}] scored", flush=True)

    payload = {
        "run_id": run_id,
        "status": "completed",
        "elapsed_s": time.time() - t0,
        "eval_targets": len(eval_targets),
        "cells_per_pert": cells_per_pert,
        "seed": seed,
        "bundle_src": bundle_src or None,
        "real_cells": int(real_sub.n_obs),
        "control_cells": int(controls.n_obs),
        "variants": list(variants),
        "oracle_note": "oracle_hesc uses in-context measured deltas -- leaked "
        "by construction, interpretation anchor only",
        "real_data_anchors": {
            f.name: _clean(pd.read_csv(f).to_dict("records"))
            for f in sorted(anchor_dir.glob("*_agg.csv"))
        },
        "results": results,
    }
    payload = _clean(payload)
    done.write_text(json.dumps(payload, indent=2, allow_nan=False, default=str) + "\n")
    volume.commit()
    return payload


@app.local_entrypoint()
def main(run_id: str, cells_per_pert: int = 400, bundle_src: str = ""):
    import json

    print(
        json.dumps(
            run_gate.remote(run_id, cells_per_pert, bundle_src=bundle_src),
            indent=2,
            default=str,
        )
    )
