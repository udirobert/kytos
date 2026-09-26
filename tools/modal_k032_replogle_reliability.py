"""Within-source replicate reliability for Replogle K562 GWPS (k032).

Why this job exists
-------------------
Every trust gate tried so far used CROSS-source agreement (falsified:
correlation r~0.22 with transfer). Untried: WITHIN-source consistency.
Targets whose K562 delta is stable across replicate batches are more
likely real signal worth trusting in the consensus; unstable targets are
candidates for shrinkage -- the per-target analog of the per-gene eb2
shrinkage already in k029.

Data
----
figshare 35775507 -- Replogle K562 genome-wide Perturb-seq single-cell
(65.8 GB): dense X (1,989,578 cells x 8,248 genes) float32, obs/gene =
target codes (9,867 categories incl "non-targeting"), obs/gem_group =
batch index. Cells are split into replicate halves by gem_group parity
(deterministic, no labels needed downstream).

Method
------
Single pass over X in row chunks via fsspec range reads:
  sums[bucket, half, panel_gene] += log1p(count)
bucket = request-target index (343-axis); last bucket = non-targeting.
half = gem_group % 2.

Outputs (volume ``k032-replogle-rel/<run_id>/``)
-----------------------------------------------
``deltas_k562_repA.npz`` / ``deltas_k562_repB.npz`` -- half-replicate
  deltas (343 x 18,533), same schema as k023 source deltas.
``reliability_k562.json`` -- per-target cosine(repA, repB), cell counts,
  plus pooled-vs-existing-delta cosine as a pipeline sanity check.
``manifest.json`` -- provenance, chunking, thresholds.

Run:
  modal run -d tools/modal_k032_replogle_reliability.py --run-id rel-YYYYMMDD-NN
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
OUT_DIR = VOLUME_ROOT / "k032-replogle-rel"
PANEL_GENES = REMOTE_ROOT / "data/vcc2026/gene_names.csv"
PANEL_COUNTS = REMOTE_ROOT / "data/vcc2026/pert_counts.csv"
PAIRED_PATH = VOLUME_ROOT / "paired-transfer/paired_transfer_train.npz"
K562_REF_NPZ = VOLUME_ROOT / "k023-consensus/extract-20260921-02-honest/deltas_k562.npz"

REPLOGLE_URL = "https://ndownloader.figshare.com/files/35775507"
NTC_LABEL = "non-targeting"
ROW_CHUNK = 20000
MIN_CELLS_PER_HALF = 30  # target covered only if BOTH halves >= this

app = modal.App("kytos-k032-replogle-rel")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "scipy==1.15.3",
        "pandas==2.2.3",
        "h5py==3.13.0",
        "fsspec",
        "requests==2.32.4",
    )
    .add_local_file(
        LOCAL_ROOT / "tools/consensus_deltas.py",
        str(REMOTE_ROOT / "tools/consensus_deltas.py"),
        copy=True,
    )
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/gene_names.csv",
        str(PANEL_GENES),
        copy=True,
    )
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/pert_counts.csv",
        str(PANEL_COUNTS),
        copy=True,
    )
)


def _check_run_id(run_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Use a new alphanumeric run ID (hyphens/underscores allowed)")


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=10800,
    startup_timeout=300,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
)
def scan(run_id: str) -> dict:
    import sys
    import time

    import fsspec
    import h5py
    import numpy as np
    import pandas as pd

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd

    _check_run_id(run_id)
    out = OUT_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    if (out / "reliability_k562.json").exists():
        return {"status": "exists"}

    t0 = time.time()
    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    n_genes = len(panel_genes)

    panel = sorted(pd.read_csv(PANEL_COUNTS).iloc[:, 0].astype(str).unique())
    with np.load(PAIRED_PATH, allow_pickle=False) as paired:
        eval_targets = paired["paired_targets"].astype(str).tolist()
    request_targets = sorted(set(panel) | set(eval_targets))
    n_targets = len(request_targets)
    target_pos = {t: i for i, t in enumerate(request_targets)}

    with fsspec.open(REPLOGLE_URL, "rb") as fh:
        h5 = h5py.File(fh, "r")
        gene_cats = h5["obs/__categories/gene"].asstr()[:]
        cat_to_bucket = np.full(len(gene_cats), -1, dtype=np.int32)
        for i, g in enumerate(gene_cats):
            if g == NTC_LABEL:
                cat_to_bucket[i] = n_targets
            elif g in target_pos:
                cat_to_bucket[i] = target_pos[g]
        gene_codes = h5["obs/gene"][:]
        gem = h5["obs/gem_group"][:]

        var_genes = h5["var/__categories/gene_name"].asstr()[:][h5["var/gene_name"][:]]
        pos_arr, missing = cd.map_gene_axis(var_genes.tolist(), panel_genes)
        gene_to_panel = np.full(len(var_genes), -1, dtype=np.int32)
        gene_to_panel[pos_arr[pos_arr >= 0]] = np.flatnonzero(pos_arr >= 0)
        panel_cols = np.flatnonzero(gene_to_panel >= 0)
        col_panel_pos = gene_to_panel[panel_cols]

        X = h5["X"]
        n_cells = X.shape[0]
        bucket = cat_to_bucket[gene_codes]
        half = (gem % 2).astype(np.int8)
        keep = bucket >= 0
        print(
            f"cells={n_cells} kept={int(keep.sum())} "
            f"ntc={int(((bucket == n_targets) & keep).sum())} "
            f"half1={int((half[keep] == 1).sum())}",
            flush=True,
        )

        # accumulators: (n_buckets, 2, n_genes)
        sums = np.zeros((n_targets + 1, 2, n_genes), dtype=np.float64)
        counts = np.zeros((n_targets + 1, 2), dtype=np.int64)
        ckpt = out / "scan.ckpt.npz"
        start_row = 0
        if ckpt.exists():
            with np.load(ckpt, allow_pickle=False) as d:
                sums = d["sums"]
                counts = d["counts"]
                start_row = int(d["row"])
            print(f"resuming checkpoint at row {start_row}", flush=True)

        # sequential pass over ALL rows; kept cells are only ~3-5% so
        # selection happens per chunk after the contiguous read.
        for i, r0 in enumerate(range(start_row, n_cells, ROW_CHUNK)):
            r1 = min(r0 + ROW_CHUNK, n_cells)
            sel = keep[r0:r1]
            if sel.any():
                block = np.log1p(np.clip(X[r0:r1][sel], 0, None))[:, panel_cols]
                b = bucket[r0:r1][sel]
                h = half[r0:r1][sel]
                np.add.at(
                    sums,
                    (b[:, None], h[:, None], col_panel_pos[None, :]),
                    block,
                )
                np.add.at(counts, (b, h), 1)
            if i % 25 == 24:
                np.savez_compressed(
                    str(ckpt),
                    sums=sums,
                    counts=counts,
                    row=np.int64(r1),
                )
                volume.commit()
                print(f"checkpoint rows {r1}/{n_cells}", flush=True)

    ntc_mean = {h: sums[n_targets, h] / max(int(counts[n_targets, h]), 1) for h in (0, 1)}
    deltas = {}
    for h, tag in ((0, "repA"), (1, "repB")):
        means = sums[:n_targets, h] / np.maximum(counts[:n_targets, h], 1)[:, None]
        d = means - ntc_mean[h][None, :]
        covered = counts[:n_targets, h] >= MIN_CELLS_PER_HALF
        d[~covered] = 0.0
        np.savez_compressed(
            str(out / f"deltas_k562_{tag}.npz"),
            genes=np.asarray(panel_genes),
            targets=np.asarray(request_targets),
            delta=d.astype(np.float32),
            covered=covered,
            n_cells=counts[:n_targets, h].astype(np.int64),
        )
        deltas[tag] = {"d": d, "covered": covered}

    # per-target reliability: cosine(repA, repB) where both covered
    both = deltas["repA"]["covered"] & deltas["repB"]["covered"]
    a = deltas["repA"]["d"][both]
    b = deltas["repB"]["d"][both]
    an = np.linalg.norm(a, axis=1)
    bn = np.linalg.norm(b, axis=1)
    cos = np.full(n_targets, np.nan)
    ok = (an > 0) & (bn > 0)
    idx = np.flatnonzero(both)[ok]
    cos[idx] = (a[ok] * b[ok]).sum(1) / (an[ok] * bn[ok])
    reliability = {
        t: {
            "cos_rep": float(cos[i]) if not np.isnan(cos[i]) else None,
            "n_repA": int(counts[i, 0]),
            "n_repB": int(counts[i, 1]),
        }
        for i, t in enumerate(request_targets)
    }

    # sanity: pooled delta vs existing k023 deltas_k562
    pooled = (sums[:n_targets].sum(1)) / np.maximum(counts[:n_targets].sum(1), 1)[:, None]
    pooled_d = pooled - ((sums[n_targets].sum(0)) / max(counts[n_targets].sum(), 1))
    sanity = None
    if K562_REF_NPZ.exists():
        with np.load(K562_REF_NPZ, allow_pickle=False) as ref:
            ref_t = ref["targets"].astype(str).tolist()
            ref_d = ref["delta"]
            ref_cov = ref["covered"] if "covered" in ref else np.ones(len(ref_t), bool)
        rpos = {t: i for i, t in enumerate(ref_t)}
        shared = [
            (i, rpos[t]) for i, t in enumerate(request_targets) if t in rpos and ref_cov[rpos[t]]
        ]
        if shared:
            ii = np.array([s[0] for s in shared])
            jj = np.array([s[1] for s in shared])
            u1 = pooled_d[ii]
            u2 = ref_d[jj]
            n1 = np.linalg.norm(u1, axis=1)
            n2 = np.linalg.norm(u2, axis=1)
            m = (n1 > 0) & (n2 > 0)
            cosines = (u1[m] * u2[m]).sum(1) / (n1[m] * n2[m])
            sanity = {
                "shared_targets": int(m.sum()),
                "median_cos_to_k023": float(np.median(cosines)),
            }
            print(f"[sanity] {sanity}", flush=True)

    rep_cos = cos[idx]
    summary = {
        "run_id": run_id,
        "dataset": "Replogle K562 GWPS single-cell (figshare 35775507)",
        "url": REPLOGLE_URL,
        "n_cells": int(n_cells),
        "n_kept": int(keep.sum()),
        "replicate_split": "gem_group % 2",
        "min_cells_per_half": MIN_CELLS_PER_HALF,
        "targets_both_halves_covered": int(both.sum()),
        "median_cos_rep": float(np.nanmedian(rep_cos)),
        "p10_cos_rep": float(np.nanpercentile(rep_cos, 10)),
        "p90_cos_rep": float(np.nanpercentile(rep_cos, 90)),
        "sanity_pooled_vs_k023": sanity,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (out / "reliability_k562.json").write_text(
        json.dumps({"summary": summary, "per_target": reliability}, indent=2) + "\n"
    )
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_url": REPLOGLE_URL,
                "x_shape": [int(n_cells), int(X.shape[1])],
                "panel_genes_missing": missing,
                "row_chunk": ROW_CHUNK,
                "units": "mean log1p(raw counts) per gem_group half - NTC half mean",
            },
            indent=2,
        )
        + "\n"
    )
    ckpt.unlink(missing_ok=True)
    volume.commit()
    return summary


@app.local_entrypoint()
def main(run_id: str):
    _check_run_id(run_id)
    print(json.dumps(scan.remote(run_id), indent=2, default=str))
