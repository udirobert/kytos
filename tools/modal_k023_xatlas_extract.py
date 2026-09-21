"""Extract per-target perturbation deltas from X-Atlas Orion and CD4 (k023).

Why this job exists
-------------------
The paired47 k022 diagnostic showed borrowed K562 signatures are the
bottleneck (median cosine 0.268 vs 0.514 measured). This job extracts the
same delta quantity -- ``mean(log1p(raw))`` perturbed minus control -- from
additional public lineages so a multi-source consensus can be evaluated on
the identical diagnostic.

Sources
-------
- ``hct116`` / ``hek293t``: X-Atlas Orion genome-wide CRISPRi Perturb-seq
  (SLAF format on Hugging Face, CC-BY-NC-SA-4.0). Read REMOTELY via raw
  Lance streaming over ``hf://`` -- the ~50/83 GB expression tables are
  scanned once, filtered to needed cells, never downloaded.
  Note: the published ``cells.cell_start_index`` offsets do NOT align with
  ``expression.lance`` rows (verified drift), so cells are matched by
  ``cell_integer_id`` membership during the scan -- not by offsets.
- ``cd4``: Marson 2025 genome-wide CD4 T-cell screen. Publisher DE
  statistics h5ad (16.8 GB, sha256-pinned) downloaded to ephemeral disk;
  per-target ``log_fc`` is a log2 fold-change, NOT a mean-log1p shift --
  units differ and are recorded in the manifest.

Outputs (per source, on the Modal volume under ``k023-consensus/``)
------------------------------------------------------------------
``deltas_<source>.npz`` with:
  ``genes``         (18533,) panel axis symbols
  ``targets``       (T,) requested target symbols
  ``delta``         (T, 18533) float32 pooled delta
  ``delta_batch``   (T, 18533) float32 batch-paired delta (X-Atlas only)
  ``covered``       (T,) bool -- target present in source
  ``n_cells``       (T,) int64 perturbed cells (CD4: summed n_cells_target)
plus ``manifest_<source>.json`` with coverage, units, hashes, versions.

Run:
  modal run tools/modal_k023_xatlas_extract.py --source hct116 \
      --run-id extract-YYYYMMDD-NN
  modal run tools/modal_k023_xatlas_extract.py --source cd4 ...
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
OUT_DIR = VOLUME_ROOT / "k023-consensus"
PAIRED_PATH = VOLUME_ROOT / "paired-transfer/paired_transfer_train.npz"
PANEL_COUNTS = REMOTE_ROOT / "data/vcc2026/pert_counts.csv"
PANEL_GENES = REMOTE_ROOT / "data/vcc2026/gene_names.csv"

HF_XATLAS = "hf://datasets/slaf-project/X-Atlas-Orion/data/{}"
XATLAS_ARMS = {"hct116": "HCT116", "hek293t": "HEK293T"}
XATLAS_CONTROL = "Non-Targeting"
CONTROL_CAP_PER_SAMPLE = 150
SCAN_BATCH_ROWS = 2_000_000
SCAN_MAX_RETRIES = 20

CD4_URL = (
    "https://genome-scale-tcell-perturb-seq.s3.amazonaws.com/marson2025_data/GWCD4i.DE_stats.h5ad"
)
CD4_SHA256 = "c355f535ff32cf7ba1edc49cf9c6039fe84f2c9ebe4d005515cba75790cfbb62"
CD4_QUALITY_COLS = (
    "n_guides",
    "single_guide_estimate",
    "ontarget_significant",
    "distal_offtarget_flag",
    "low_target_gex",
)

app = modal.App("kytos-k023-consensus-extract")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "scipy==1.15.3",
        "pandas==2.2.3",
        "pylance==12.0.0",
        "h5py==3.13.0",
        "anndata==0.11.4",
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


def _hf_secret():
    """Scoped secret containing only HF_TOKEN (not the whole .env)."""
    env_path = LOCAL_ROOT / ".env"
    if not env_path.exists():
        return []
    wanted = "HF" + "_TOKEN"
    for line in env_path.read_text().splitlines():
        key, sep, val = line.partition("=")
        if sep and key.strip() == wanted and val.strip():
            return [modal.Secret.from_dict({wanted: val.strip().strip('"').strip("'")})]
    return []


def _load_request_targets():
    """Union of the 300-target 2026 panel and the 47 Atlas-eval targets."""
    import numpy as np
    import pandas as pd

    panel = sorted(pd.read_csv(PANEL_COUNTS).iloc[:, 0].astype(str).unique())
    with np.load(PAIRED_PATH, allow_pickle=False) as paired:
        eval_targets = paired["paired_targets"].astype(str).tolist()
    return sorted(set(panel) | set(eval_targets)), panel, eval_targets


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
    # HF_TOKEN lives in the repo .env; attached so anonymous resolver
    # rate limits (HTTP 429) do not stall the 17B-row expression scan.
    secrets=_hf_secret(),
)
def extract_xatlas(source: str, run_id: str) -> dict:
    import sys
    import time

    import numpy as np
    import pandas as pd
    from scipy import sparse

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd

    _check_run_id(run_id)
    if source not in XATLAS_ARMS:
        raise ValueError(f"source must be one of {sorted(XATLAS_ARMS)}")
    out = OUT_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"deltas_{source}"
    if (stem.parent / (stem.name + ".npz")).exists():
        raise FileExistsError(f"{stem}.npz already exists -- use a new run ID")

    targets_requested, panel_targets, eval_targets = _load_request_targets()
    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()

    import lance

    t0 = time.time()
    base = HF_XATLAS.format(XATLAS_ARMS[source])
    expression = lance.dataset(f"{base}/expression.lance")
    total_rows = expression.count_rows()

    genes_tbl = (
        lance.dataset(f"{base}/genes.lance")
        .scanner(columns=["gene_id", "gene_integer_id"])
        .to_table()
        .to_pandas()
        .sort_values("gene_integer_id")
    )
    positions, missing_genes = cd.map_gene_axis(
        genes_tbl["gene_id"].astype(str).tolist(), panel_genes
    )
    # positions maps panel -> source gene_integer_id row; invert it so
    # gene_to_panel[source_gene_integer_id] = panel column (or -1)
    gene_to_panel = np.full(len(genes_tbl), -1, dtype=np.int32)
    gene_to_panel[positions[positions >= 0]] = np.flatnonzero(positions >= 0)

    all_cells = (
        lance.dataset(f"{base}/cells.lance")
        .scanner(columns=["cell_integer_id", "sample", "gene_target"])
        .to_table()
        .to_pandas()
    )
    wanted = all_cells["gene_target"].isin(set(targets_requested))
    ctrl = all_cells[all_cells["gene_target"] == XATLAS_CONTROL]
    ctrl = ctrl.groupby("sample", sort=False).head(CONTROL_CAP_PER_SAMPLE)
    cells = pd.concat([all_cells[wanted], ctrl])

    group_keys = sorted(set(zip(cells["sample"], cells["gene_target"])))
    group_index = {key: i for i, key in enumerate(group_keys)}
    cell_group = np.full(int(all_cells["cell_integer_id"].max()) + 1, -1, dtype=np.int64)
    for cid, sample, label in zip(cells["cell_integer_id"], cells["sample"], cells["gene_target"]):
        cell_group[int(cid)] = group_index[(sample, label)]
    group_cells = np.zeros(len(group_keys), dtype=np.int64)
    for g in cell_group[cell_group >= 0]:
        group_cells[g] += 1

    rows_buf, cols_buf, vals_buf = [], [], []
    scanned = kept = 0
    retries = 0
    while True:
        # Recreate the scanner at `scanned` so transient HF read errors resume
        # rather than restarting the 17B-row scan from zero.
        scanner = expression.scanner(batch_size=SCAN_BATCH_ROWS, offset=scanned)
        try:
            for batch in scanner.to_batches():
                if not batch.num_rows:
                    continue
                cid = batch.column("cell_integer_id").to_numpy()
                gid = batch.column("gene_integer_id").to_numpy()
                val = batch.column("value").to_numpy()
                in_range = cid < len(cell_group)
                grp = np.where(in_range, cell_group[np.clip(cid, 0, len(cell_group) - 1)], -1)
                pos = np.where(
                    gid < len(gene_to_panel),
                    gene_to_panel[np.clip(gid, 0, len(gene_to_panel) - 1)],
                    -1,
                )
                keep = (grp >= 0) & (pos >= 0)
                if keep.any():
                    rows_buf.append(grp[keep])
                    cols_buf.append(pos[keep].astype(np.int64))
                    vals_buf.append(np.log1p(val[keep].astype(np.float64)))
                kept += int(keep.sum())
                scanned += batch.num_rows
                if scanned % (SCAN_BATCH_ROWS * 50) < SCAN_BATCH_ROWS:
                    print(
                        f"[{source}] scanned {scanned}/{total_rows} kept {kept}",
                        flush=True,
                    )
            break
        except Exception as exc:
            retries += 1
            if retries > SCAN_MAX_RETRIES:
                raise
            wait = min(60, 5 * retries)
            print(
                f"[{source}] scan error at row {scanned} "
                f"(retry {retries}/{SCAN_MAX_RETRIES} in {wait}s): {exc}",
                flush=True,
            )
            time.sleep(wait)

    row = np.concatenate(rows_buf) if rows_buf else np.zeros(0, dtype=np.int64)
    col = np.concatenate(cols_buf) if cols_buf else np.zeros(0, dtype=np.int64)
    dat = np.concatenate(vals_buf) if vals_buf else np.zeros(0)
    group_sums = sparse.csr_matrix(
        (dat, (row, col)), shape=(len(group_keys), len(panel_genes))
    ).toarray()

    deltas = cd.deltas_from_group_sums(group_sums, group_cells, group_keys, XATLAS_CONTROL)
    order = targets_requested
    covered = np.array([t in deltas for t in order])
    delta_pool = np.zeros((len(order), len(panel_genes)), dtype=np.float32)
    delta_batch = np.zeros_like(delta_pool)
    n_cells = np.zeros(len(order), dtype=np.int64)
    n_samples = np.zeros(len(order), dtype=np.int64)
    for i, t in enumerate(order):
        if t in deltas:
            delta_pool[i] = deltas[t]["pooled"]
            delta_batch[i] = deltas[t]["batch"]
            n_cells[i] = deltas[t]["n_cells"]
            n_samples[i] = deltas[t]["n_samples"]

    stem = out / f"deltas_{source}"
    np.savez_compressed(
        str(stem) + ".npz",
        genes=np.asarray(panel_genes),
        targets=np.asarray(order),
        delta=delta_pool,
        delta_batch=delta_batch,
        covered=covered,
        n_cells=n_cells,
        n_samples=n_samples,
    )
    manifest = {
        "source": source,
        "dataset": HF_XATLAS.format(XATLAS_ARMS[source]),
        "run_id": run_id,
        "control_label": XATLAS_CONTROL,
        "control_cap_per_sample": CONTROL_CAP_PER_SAMPLE,
        "expression_rows_scanned": int(scanned),
        "expression_rows_kept": int(kept),
        "expression_table_rows": int(total_rows),
        "scan_retries": retries,
        "selected_cells": int(len(cells)),
        "targets_requested": len(order),
        "targets_covered": int(covered.sum()),
        "panel_genes": len(panel_genes),
        "panel_genes_missing_from_source": missing_genes,
        "units": "mean log1p(raw counts) perturbed minus control",
        "delta_columns": {"delta": "pooled controls", "delta_batch": "per-sample paired"},
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    (out / f"manifest_{source}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    volume.commit()
    return {"status": "completed", "npz": str(stem) + ".npz", "manifest": manifest}


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=7200,
    startup_timeout=300,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
    ephemeral_disk=524288,
)
def extract_cd4(run_id: str) -> dict:
    import hashlib
    import time

    import numpy as np
    import pandas as pd
    import requests

    import sys

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd

    _check_run_id(run_id)
    out = OUT_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    stem = out / "deltas_cd4"
    if (stem.parent / (stem.name + ".npz")).exists():
        raise FileExistsError(f"{stem}.npz already exists -- use a new run ID")
    targets_requested, _, _ = _load_request_targets()
    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()

    t0 = time.time()
    local = Path("/tmp/GWCD4i.DE_stats.h5ad")
    digest = hashlib.sha256()
    with requests.get(CD4_URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with local.open("wb") as fh:
            for chunk in r.iter_content(1024 * 1024 * 8):
                fh.write(chunk)
                digest.update(chunk)
    if digest.hexdigest() != CD4_SHA256:
        raise ValueError("CD4 download sha256 mismatch")

    import anndata as ad

    adata = ad.read_h5ad(local, backed="r")
    try:
        obs = adata.obs
        var_names = (
            adata.var["gene_name"].astype(str).to_numpy()
            if "gene_name" in adata.var.columns
            else adata.var_names.astype(str).to_numpy()
        )
        obs_target = obs["target_contrast_gene_name"].astype(str)
        selected = np.flatnonzero(obs_target.isin(targets_requested).to_numpy())
        chosen = obs.iloc[selected]
        log_fc = np.asarray(adata.layers["log_fc"][selected, :], dtype=np.float64)
    finally:
        adata.file.close()

    quality = (
        (chosen["n_guides"] >= 2)
        & ~chosen["single_guide_estimate"].astype(bool)
        & chosen["ontarget_significant"].astype(bool)
        & ~chosen["distal_offtarget_flag"].astype(bool)
        & ~chosen["low_target_gex"].astype(bool)
    ).to_numpy()

    positions, missing_genes = cd.map_gene_axis(list(var_names), panel_genes)
    keep_cols = positions >= 0
    delta = np.zeros((len(targets_requested), len(panel_genes)), dtype=np.float32)
    covered = np.zeros(len(targets_requested), dtype=bool)
    n_cells = np.zeros(len(targets_requested), dtype=np.int64)
    n_rows = np.zeros(len(targets_requested), dtype=np.int64)
    for i, t in enumerate(targets_requested):
        rows = np.flatnonzero(
            (chosen["target_contrast_gene_name"].astype(str).to_numpy() == t) & quality
        )
        if not len(rows):
            continue
        covered[i] = True
        n_rows[i] = len(rows)
        if "n_cells_target" in chosen:
            n_cells[i] = int(chosen["n_cells_target"].iloc[rows].min())
        mean_fc = log_fc[rows].mean(axis=0)
        delta[i, keep_cols] = mean_fc[positions[keep_cols]]

    stem = out / "deltas_cd4"
    np.savez_compressed(
        str(stem) + ".npz",
        genes=np.asarray(panel_genes),
        targets=np.asarray(targets_requested),
        delta=delta,
        covered=covered,
        n_cells=n_cells,
        n_quality_rows=n_rows,
    )
    manifest = {
        "source": "cd4",
        "dataset_url": CD4_URL,
        "sha256": CD4_SHA256,
        "run_id": run_id,
        "units": "publisher log2 fold-change (NOT mean-log1p shift)",
        "quality_filter": "n_guides>=2 & !single_guide & ontarget_significant "
        "& !distal_offtarget & !low_target_gex",
        "targets_requested": len(targets_requested),
        "targets_covered": int(covered.sum()),
        "panel_genes_missing_from_source": missing_genes,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    (out / "manifest_cd4.json").write_text(json.dumps(manifest, indent=2) + "\n")
    volume.commit()
    return {"status": "completed", "npz": str(stem) + ".npz", "manifest": manifest}


@app.function(
    image=image,
    cpu=(2.0, 2.0),
    memory=(16384, 16384),
    timeout=1800,
    startup_timeout=300,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
)
def extract_k562(run_id: str) -> dict:
    """Subset the existing K562 deltas to the requested targets.

    ``delta_matrix_src.npz`` ships no explicit ``genes`` array; its column
    order is implicitly the paired_transfer genes axis (established by the
    axis audit). This subsets by target name and re-emits on the explicit
    panel axis so downstream consumers never rely on the implicit axis.
    """
    import sys
    import time

    import numpy as np
    import pandas as pd

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))

    _check_run_id(run_id)
    out = OUT_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    stem = out / "deltas_k562"
    if (stem.parent / (stem.name + ".npz")).exists():
        raise FileExistsError(f"{stem}.npz already exists -- use a new run ID")
    targets_requested, _, _ = _load_request_targets()
    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()

    t0 = time.time()
    src_matrix = VOLUME_ROOT / "paired-transfer/delta_matrix_src.npz"
    with np.load(PAIRED_PATH, allow_pickle=False) as paired:
        paired_genes = paired["genes"].astype(str).tolist()
        paired_targets = paired["paired_targets"].astype(str).tolist()
        paired_delta = paired["delta_k562"]
        if paired_genes != panel_genes:
            raise ValueError("paired_transfer genes axis differs from the panel axis")
    with np.load(src_matrix, allow_pickle=False) as src:
        src_targets = src["targets"].astype(str).tolist()
        src_deltas = src["deltas"]
        if src_deltas.shape[1] != len(panel_genes):
            raise ValueError("delta_matrix_src column count does not match the panel axis")

    delta = np.zeros((len(targets_requested), len(panel_genes)), dtype=np.float32)
    covered = np.zeros(len(targets_requested), dtype=bool)
    src_pos = {t: i for i, t in enumerate(src_targets)}
    paired_pos = {t: i for i, t in enumerate(paired_targets)}
    for i, t in enumerate(targets_requested):
        if t in src_pos:
            delta[i] = src_deltas[src_pos[t]]
            covered[i] = True
        elif t in paired_pos:
            delta[i] = paired_delta[paired_pos[t]]
            covered[i] = True

    stem = out / "deltas_k562"
    np.savez_compressed(
        str(stem) + ".npz",
        genes=np.asarray(panel_genes),
        targets=np.asarray(targets_requested),
        delta=delta,
        covered=covered,
    )
    manifest = {
        "source": "k562",
        "datasets": [str(src_matrix), str(PAIRED_PATH)],
        "run_id": run_id,
        "units": "mean log1p(raw counts) perturbed minus control",
        "note": "delta_matrix_src.npz has an implicit axis assumed equal to "
        "the paired_transfer/panel axis; verified by column count only",
        "targets_requested": len(targets_requested),
        "targets_covered": int(covered.sum()),
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    (out / "manifest_k562.json").write_text(json.dumps(manifest, indent=2) + "\n")
    volume.commit()
    return {"status": "completed", "npz": str(stem) + ".npz", "manifest": manifest}


@app.local_entrypoint()
def main(source: str, run_id: str):
    if source in XATLAS_ARMS:
        result = extract_xatlas.remote(source, run_id)
    elif source == "cd4":
        result = extract_cd4.remote(run_id)
    elif source == "k562":
        result = extract_k562.remote(run_id)
    else:
        raise ValueError("source must be hct116, hek293t, cd4, or k562")
    print(json.dumps(result, indent=2))
