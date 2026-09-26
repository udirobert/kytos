"""Modal: Gate B (cell-eval2 vcc2026) for context-weighted consensus (k030).

Same harness as tools/modal_k025_eval2_gate.py: 47 paired hESC eval targets,
real Atlas validation subset, dual-moment generation at the champion config
(dm_amp=1.0, dm_bulk_amp=0.3, pool_k=12), scored against the reusable real
bundle from gate-20260921-01.

What's different: the delta variants are context-weighted consensuses built
by tools/build_ctxw_consensus.py from basal-similarity weights
(modal_ctxlineage_basal.py -> ctxlineage_report.json). The "eval" context
weight vector (hESC Atlas validation controls -> source basal similarity)
is what gets tested here -- the A/B/C weight vectors are validated only
indirectly by this mechanism test.

Arms:
  cons_ctxw2_eb2_ctr   p2-weighted mean + eb2 shrinkage + ctr (full stack)
  cons_ctxw1_eb2_ctr   p1-weighted mean + eb2 shrinkage + ctr (gentler tilt)
  cons_ctxw2_ctr       p2-weighted mean + ctr, NO eb (isolates weighting)
  cons_eb2_ref         champion cons_eb2_ctr rerun -- same-run anchor

Run:
  modal run -d tools/modal_k030_ctxw_gate.py --run-id gate-YYYYMMDD-NN \
      --bundle-src /kytos-vol/k025-eval2-gate/gate-20260921-01/bundle

Arm metrics are embargoed (experiments/_embargoed/k025-eval2-gate/).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
ATLAS_PATH = VOLUME_ROOT / "atlas/adata_Validation.h5ad"
PAIRED_PATH = VOLUME_ROOT / "paired-transfer/paired_transfer_train.npz"
VARIANTS_DIR = VOLUME_ROOT / "k023-consensus/extract-20260921-02-honest/variants"
CTXW_DIR = VOLUME_ROOT / "k030-ctxlineage/basal-20260924-01/variants"
NEWSRC_DIR = VOLUME_ROOT / "k030-ctxlineage/newsrc-5j"
NEWSRC6_DIR = VOLUME_ROOT / "k030-ctxlineage/newsrc-6jhip"
REL_DIR = VOLUME_ROOT / "k030-ctxlineage/build-rel"
POSTJ_DIR = VOLUME_ROOT / "k030-ctxlineage/build-postj"
OUT_ROOT = VOLUME_ROOT / "k025-eval2-gate"

CELL_EVAL2_GIT = (
    "cell-eval2 @ git+https://github.com/ArcInstitute/cell-eval2"
    "@5e64833518a6603a0301cbe28185d49c30f4a986"
)

app = modal.App("kytos-k030-ctxw-gate")
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


def _clean(obj):
    import math

    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


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
def run_gate(
    run_id: str,
    cells_per_pert: int = 400,
    seed: int = 0,
    bundle_src: str = "",
    arms: str = "",
) -> dict:
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

    work = Path(tempfile.mkdtemp(prefix="k030-"))
    real_path = work / "real_eval2.h5ad"
    real_sub = real[keep_idx].to_memory()
    real_sub.write_h5ad(real_path, compression="gzip")

    ctrl_idx = np.flatnonzero((labels == "non-targeting").to_numpy())
    controls = real[ctrl_idx].to_memory()
    ctrl_path = work / "controls_eval2.h5ad"
    controls.write_h5ad(ctrl_path, compression="gzip")
    real.file.close()
    del real

    def dm(npz):
        return {
            "npz": Path(npz),
            "gen": "dm",
            "dm_amp": 1.0,
            "dm_bulk_amp": 0.3,
            "dm_pool_k": 12,
        }

    variants = {
        "cons_ctxw2_eb2_ctr": dm(CTXW_DIR / "variant_p2_cons_ctxw_eval_eb2_ctr.npz"),
        "cons_ctxw1_eb2_ctr": dm(CTXW_DIR / "variant_p1_cons_ctxw_eval_eb2_ctr.npz"),
        "cons_ctxw2_ctr": dm(CTXW_DIR / "variant_p2_cons_ctxw_eval_ctr.npz"),
        "cons_eb2_ref": dm(VARIANTS_DIR / "variant_consensus_eb2_ctr.npz"),
        "cons_mean_j": dm(NEWSRC_DIR / "variant_consensus_mean.npz"),
        "cons_eb2_j": dm(NEWSRC_DIR / "variant_consensus_eb2.npz"),
        "cons_eb2_jhip": dm(NEWSRC6_DIR / "variant_consensus_eb2.npz"),
        "cons_eb2_rel": dm(REL_DIR / "variant_cons_eb2_ctr_rel.npz"),
        "cons_eb2_relsqrt": dm(REL_DIR / "variant_cons_eb2_ctr_relsqrt.npz"),
        "cons_eb2post_j2_ctr": dm(POSTJ_DIR / "variant_cons_eb2post_j0p2_ctr.npz"),
        "cons_eb2post_j2": dm(POSTJ_DIR / "variant_cons_eb2post_j0p2.npz"),
        "cons_eb2post_j4_ctr": dm(POSTJ_DIR / "variant_cons_eb2post_j0p4_ctr.npz"),
        "cons_mean_ref": dm(
            VOLUME_ROOT / "k030-ctxlineage/build-src4-mean/variant_consensus_mean.npz"
        ),
        "cons_mean_ctr_ref": dm(
            VOLUME_ROOT / "k030-ctxlineage/build-src4-mean/variant_consensus_mean_ctr.npz"
        ),
        "cons_w_ctr_ref": dm(VARIANTS_DIR / "variant_consensus_w_ctr.npz"),
        "cons_w_ref": dm(VARIANTS_DIR / "variant_consensus_w.npz"),
    }
    variants = {k: v for k, v in variants.items() if v["npz"].exists()}
    if arms:
        wanted = {a.strip() for a in arms.split(",") if a.strip()}
        variants = {k: v for k, v in variants.items() if k in wanted}
    print(f"[arms] {sorted(variants)}", flush=True)

    rng = np.random.default_rng(seed)
    pred_paths = {}
    for name, spec in variants.items():
        spec["deltas"] = _load_variant_deltas(spec["npz"], axis_symbols)
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
def main(run_id: str, cells_per_pert: int = 400, bundle_src: str = "", arms: str = ""):
    print(
        json.dumps(
            run_gate.remote(run_id, cells_per_pert, bundle_src=bundle_src, arms=arms),
            indent=2,
            default=str,
        )
    )
