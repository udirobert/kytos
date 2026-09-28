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

Outputs (per source, on the Modal volume under ``k023-consensus/`` by
default; ``--out-subdir`` redirects, e.g. ``k034-final-prep``)
------------------------------------------------------------------
``deltas_<source>.npz`` with:
  ``genes``         (18533,) panel axis symbols
  ``targets``       (T,) requested target symbols
  ``delta``         (T, 18533) float32 pooled delta
  ``delta_batch``   (T, 18533) float32 batch-paired delta (X-Atlas only;
                    omitted in ``--all-source-targets`` mode -- a
                    (target, sample) pairing at genome scale is ~1.5M
                    sparse group rows, so only pooled deltas are kept)
  ``covered``       (T,) bool -- target present in source
  ``n_cells``       (T,) int64 perturbed cells (CD4: summed n_cells_target)
plus ``manifest_<source>.json`` with coverage, units, hashes, versions.

Target selection (default behavior unchanged):
  - no flags        -> union of the 300-target 2026 panel + 47 Atlas-eval
                       targets (``_load_request_targets``)
  - --targets-file  -> newline/CSV list of symbols, first column used
  - --all-source-targets -> every target present in the source (genome-wide)

Run:
  modal run tools/modal_k023_xatlas_extract.py --source hct116 \
      --run-id extract-YYYYMMDD-NN
  modal run tools/modal_k023_xatlas_extract.py --source cd4 ...
  modal run tools/modal_k023_xatlas_extract.py --source hct116 \
      --run-id k034-hct116-all --all-source-targets \
      --out-subdir k034-final-prep
  modal run tools/modal_k023_xatlas_extract.py --source hct116 --probe
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
# In --all-source-targets mode kept rows are ~half the 17-29B-row scan, so
# they cannot be buffered: triplets are flushed into a sparse accumulator
# every SEGMENT_FLUSH_NNZ kept values.
SEGMENT_FLUSH_NNZ = 256_000_000
# Checkpoint the accumulator to the volume every CKPT_SCAN_ROWS scanned
# rows: Modal preempted a hek293t runner at ~68% (SIGTERM) and the input
# restarted from zero -- a checkpointed resume loses only the tail segment.
CKPT_SCAN_ROWS = 4_000_000_000
# Dense (groups x panel_genes) accumulation is only safe for panel-scale
# target lists; beyond this product callers must use --all-source-targets.
MAX_DENSE_GROUP_CELLS = 500_000_000

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
    """Scoped named secret containing only HF_TOKEN (not the whole .env).

    Created once via `modal secret create kytos-hf HF_TOKEN=...` — referenced
    by name so function serialization is identical locally and remotely.
    """
    return [modal.Secret.from_name("kytos-hf")]


def _load_request_targets():
    """Union of the 300-target 2026 panel and the 47 Atlas-eval targets."""
    import numpy as np
    import pandas as pd

    panel = sorted(pd.read_csv(PANEL_COUNTS).iloc[:, 0].astype(str).unique())
    with np.load(PAIRED_PATH, allow_pickle=False) as paired:
        eval_targets = paired["paired_targets"].astype(str).tolist()
    return sorted(set(panel) | set(eval_targets)), panel, eval_targets


def _resolve_out_dir(out_subdir, run_id):
    out = (VOLUME_ROOT / out_subdir if out_subdir else OUT_DIR) / run_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def _read_targets_file(path: str) -> list[str]:
    """Local-side targets list: one symbol per line or CSV first column."""
    targets = []
    for line in Path(path).read_text().splitlines():
        sym = line.split(",")[0].strip()
        if sym and sym != "target_gene":
            targets.append(sym)
    return sorted(set(targets))


@app.function(
    image=image,
    cpu=(2.0, 2.0),
    memory=(8192, 8192),
    timeout=1800,
    startup_timeout=300,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
    secrets=_hf_secret(),
)
def probe_xatlas(source: str) -> dict:
    """Cardinality probe: distinct gene_target / sample counts per line.

    Cheap (scans only the small ``cells.lance`` table) -- run before an
    ``--all-source-targets`` extract to size the job.
    """
    if source not in XATLAS_ARMS:
        raise ValueError(f"source must be one of {sorted(XATLAS_ARMS)}")
    import lance

    base = HF_XATLAS.format(XATLAS_ARMS[source])
    cells = (
        lance.dataset(f"{base}/cells.lance")
        .scanner(columns=["cell_integer_id", "sample", "gene_target"])
        .to_table()
        .to_pandas()
    )
    targets = sorted(set(cells["gene_target"].astype(str)) - {XATLAS_CONTROL})
    return {
        "source": source,
        "n_cells": int(len(cells)),
        "n_samples": int(cells["sample"].nunique()),
        "n_gene_targets": len(targets),
        "expression_table": f"{base}/expression.lance",
    }


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
def extract_xatlas(
    source: str,
    run_id: str,
    targets: list | None = None,
    all_source_targets: bool = False,
    out_subdir: str = "",
) -> dict:
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
    out = _resolve_out_dir(out_subdir, run_id)
    stem = out / f"deltas_{source}"
    if (stem.parent / (stem.name + ".npz")).exists():
        raise FileExistsError(f"{stem}.npz already exists -- use a new run ID")

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

    if all_source_targets:
        targets_requested = sorted(set(all_cells["gene_target"].astype(str)) - {XATLAS_CONTROL})
        target_selection = "all_source_targets"
    elif targets is not None:
        targets_requested = sorted({str(t) for t in targets})
        target_selection = "targets_file"
    else:
        targets_requested, _, _ = _load_request_targets()
        target_selection = "panel_plus_eval"

    wanted = all_cells["gene_target"].isin(set(targets_requested))
    ctrl = all_cells[all_cells["gene_target"] == XATLAS_CONTROL]
    ctrl = ctrl.groupby("sample", sort=False).head(CONTROL_CAP_PER_SAMPLE)
    cells = pd.concat([all_cells[wanted], ctrl])

    rows_buf, cols_buf, vals_buf = [], [], []
    scanned = kept = 0
    retries = 0
    buf_nnz = 0

    if all_source_targets:
        # ---- pooled-only streaming accumulation ------------------------
        # Genome-scale: ~all cells are kept, so triplet buffering would
        # need ~100s of GB and a dense (sample, target) group matrix would
        # need ~1.5M x 18.5k rows. Instead accumulate per-target pooled
        # log1p sums into a CSR matrix flushed every SEGMENT_FLUSH_NNZ kept
        # values. Bucket index = target position; last bucket = pooled
        # controls (equivalent to the pooled control mean used by
        # deltas_from_group_sums). delta_batch is intentionally not
        # produced in this mode.
        target_pos = {t: i for i, t in enumerate(targets_requested)}
        n_buckets = len(targets_requested) + 1
        cell_bucket = np.full(int(all_cells["cell_integer_id"].max()) + 1, -1, dtype=np.int64)
        labels = cells["gene_target"].to_numpy()
        buckets = np.array([target_pos.get(t, n_buckets - 1) for t in labels], dtype=np.int64)
        cell_bucket[cells["cell_integer_id"].to_numpy()] = buckets
        group_cells = np.bincount(buckets, minlength=n_buckets).astype(np.int64)
        accum = sparse.csr_matrix((n_buckets, len(panel_genes)), dtype=np.float64)

        # Resume from a checkpointed scan if a previous attempt was killed
        # mid-run (SIGTERM preemption observed in k034).
        ckpt_path = out / "checkpoint_scan.npz"
        ckpt_next = CKPT_SCAN_ROWS
        if ckpt_path.exists():
            with np.load(ckpt_path) as ck:
                if not np.array_equal(ck["group_cells"], group_cells):
                    raise ValueError("checkpoint does not match this cell set")
                accum = sparse.csr_matrix(
                    (ck["accum_data"], ck["accum_indices"], ck["accum_indptr"]),
                    shape=(n_buckets, len(panel_genes)),
                )
                scanned = int(ck["scanned"])
                kept = int(ck["kept"])
                ckpt_next = scanned + CKPT_SCAN_ROWS
                print(
                    f"[{source}] resuming from checkpoint at {scanned} rows "
                    f"(accum nnz={accum.nnz})",
                    flush=True,
                )

        def _flush():
            nonlocal accum, buf_nnz, ckpt_next
            if not rows_buf:
                return
            r = np.concatenate(rows_buf)
            c = np.concatenate(cols_buf)
            v = np.concatenate(vals_buf)
            accum = accum + sparse.coo_matrix((v, (r, c)), shape=accum.shape).tocsr()
            rows_buf.clear()
            cols_buf.clear()
            vals_buf.clear()
            buf_nnz = 0
            if scanned >= ckpt_next:
                np.savez(
                    str(out / "checkpoint_scan.npz.tmp"),
                    scanned=np.int64(scanned),
                    kept=np.int64(kept),
                    group_cells=group_cells,
                    accum_data=accum.data,
                    accum_indices=accum.indices,
                    accum_indptr=accum.indptr,
                )
                (out / "checkpoint_scan.npz.tmp").rename(ckpt_path)
                volume.commit()
                ckpt_next = scanned + CKPT_SCAN_ROWS
                print(f"[{source}] checkpoint at {scanned}", flush=True)
            print(f"[{source}] flush: accum nnz={accum.nnz}", flush=True)
    else:
        # ---- (sample, target) group accumulation, original path --------
        group_keys = sorted(set(zip(cells["sample"], cells["gene_target"])))
        if len(group_keys) * len(panel_genes) > MAX_DENSE_GROUP_CELLS:
            raise ValueError(
                f"{len(group_keys)} (sample, target) groups x {len(panel_genes)} "
                "genes exceeds the dense accumulation bound; rerun with "
                "--all-source-targets (pooled deltas) or a smaller "
                "--targets-file"
            )
        group_index = {key: i for i, key in enumerate(group_keys)}
        cell_group = np.full(int(all_cells["cell_integer_id"].max()) + 1, -1, dtype=np.int64)
        for cid, sample, label in zip(
            cells["cell_integer_id"], cells["sample"], cells["gene_target"]
        ):
            cell_group[int(cid)] = group_index[(sample, label)]
        group_cells = np.zeros(len(group_keys), dtype=np.int64)
        for g in cell_group[cell_group >= 0]:
            group_cells[g] += 1
        accum = None

        def _flush():
            return

    cell_map = cell_bucket if all_source_targets else cell_group
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
                in_range = cid < len(cell_map)
                grp = np.where(in_range, cell_map[np.clip(cid, 0, len(cell_map) - 1)], -1)
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
                    buf_nnz += int(keep.sum())
                kept += int(keep.sum())
                scanned += batch.num_rows
                # Flush AFTER scanned/kept advance so a checkpoint's
                # (scanned, accum) pair is consistent -- resuming must not
                # re-scan rows the accumulator already contains.
                if buf_nnz >= SEGMENT_FLUSH_NNZ:
                    _flush()
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
    _flush()

    if all_source_targets:
        # Pooled delta: per-target mean log1p minus pooled control mean.
        sums = accum[:-1].toarray()  # (n_targets, n_genes) float64
        ctrl_mean = accum[-1].toarray().ravel() / max(int(group_cells[-1]), 1)
        order = targets_requested
        covered = group_cells[:-1] > 0
        n_cells = group_cells[:-1]
        delta_pool = np.zeros((len(order), len(panel_genes)), dtype=np.float32)
        nz = n_cells > 0
        delta_pool[nz] = (sums[nz] / n_cells[nz, None] - ctrl_mean[None, :]).astype(np.float32)
        pert_cells = cells[cells["gene_target"] != XATLAS_CONTROL]
        per_target_samples = pert_cells.groupby("gene_target")["sample"].nunique().to_dict()
        n_samples = np.array([per_target_samples.get(t, 0) for t in order], dtype=np.int64)
        extra = {}
        delta_columns = {"delta": "pooled controls"}
    else:
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
        extra = {"delta_batch": delta_batch}
        delta_columns = {"delta": "pooled controls", "delta_batch": "per-sample paired"}

    stem = out / f"deltas_{source}"
    # Member order matches the original layout in default mode (delta_batch
    # before covered); all-source mode simply omits delta_batch.
    np.savez_compressed(
        str(stem) + ".npz",
        genes=np.asarray(panel_genes),
        targets=np.asarray(order),
        delta=delta_pool,
        **extra,
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
        "target_selection": target_selection,
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
        "delta_columns": delta_columns,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    (out / f"manifest_{source}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if all_source_targets:
        ckpt = out / "checkpoint_scan.npz"
        if ckpt.exists():
            ckpt.unlink()
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
def extract_cd4(
    run_id: str,
    targets: list | None = None,
    all_source_targets: bool = False,
    out_subdir: str = "",
) -> dict:
    import hashlib
    import time

    import numpy as np
    import pandas as pd
    import requests

    import sys

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd

    _check_run_id(run_id)
    out = _resolve_out_dir(out_subdir, run_id)
    stem = out / "deltas_cd4"
    if (stem.parent / (stem.name + ".npz")).exists():
        raise FileExistsError(f"{stem}.npz already exists -- use a new run ID")
    if targets is None and not all_source_targets:
        targets_requested, _, _ = _load_request_targets()
        target_selection = "panel_plus_eval"
    elif targets is not None:
        targets_requested = sorted({str(t) for t in targets})
        target_selection = "targets_file"
    else:
        targets_requested = None  # resolved after the h5ad is opened
        target_selection = "all_source_targets"
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
        if targets_requested is None:
            # --all-source-targets: every contrast's target in the table.
            targets_requested = sorted(t for t in obs_target.unique() if t and t != "nan")
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
        "target_selection": target_selection,
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
def extract_k562(
    run_id: str,
    targets: list | None = None,
    all_source_targets: bool = False,
    out_subdir: str = "",
) -> dict:
    """Subset the existing K562 deltas to the requested targets.

    ``delta_matrix_src.npz`` ships no explicit ``genes`` array; its column
    order is implicitly the paired_transfer genes axis (established by the
    axis audit). This subsets by target name and re-emits on the explicit
    panel axis so downstream consumers never rely on the implicit axis.

    For the 47 paired targets the source matrix rows are the *hESC* deltas
    (``atlas_deltas`` preferred over ``replogle_deltas`` in
    ``extract_paired_transfer.py``), i.e. in-context measurements on the same
    file the k022 audit evaluates. Using them as the "k562" arm leaks the eval
    context. To keep the borrowed arm honest we therefore prefer
    ``paired_transfer.delta_k562`` (Replogle) for paired targets and fall back
    to the src matrix only for non-paired targets.
    """
    import sys
    import time

    import numpy as np
    import pandas as pd

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))

    _check_run_id(run_id)
    out = _resolve_out_dir(out_subdir, run_id)
    stem = out / "deltas_k562"
    if (stem.parent / (stem.name + ".npz")).exists():
        raise FileExistsError(f"{stem}.npz already exists -- use a new run ID")
    if targets is None and not all_source_targets:
        targets_requested, _, _ = _load_request_targets()
        target_selection = "panel_plus_eval"
    elif targets is not None:
        targets_requested = sorted({str(t) for t in targets})
        target_selection = "targets_file"
    else:
        targets_requested = None  # resolved after the source npz is opened
        target_selection = "all_source_targets"
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
    if targets_requested is None:
        # --all-source-targets: every target in the src matrix plus the
        # paired-eval targets (paired rows keep the honest Replogle swap).
        targets_requested = sorted(set(src_targets) | set(paired_targets))

    delta = np.zeros((len(targets_requested), len(panel_genes)), dtype=np.float32)
    covered = np.zeros(len(targets_requested), dtype=bool)
    src_pos = {t: i for i, t in enumerate(src_targets)}
    paired_pos = {t: i for i, t in enumerate(paired_targets)}
    n_paired_honest = 0
    for i, t in enumerate(targets_requested):
        if t in paired_pos:
            delta[i] = paired_delta[paired_pos[t]]
            covered[i] = True
            n_paired_honest += 1
        elif t in src_pos:
            delta[i] = src_deltas[src_pos[t]]
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
        "the paired_transfer/panel axis; verified by column count only. "
        "Paired targets use paired_transfer.delta_k562 (honest Replogle); "
        "src-matrix rows for those targets are in-context hESC deltas and "
        "would leak the k022 eval.",
        "paired_targets_from_replogle": n_paired_honest,
        "target_selection": target_selection,
        "targets_requested": len(targets_requested),
        "targets_covered": int(covered.sum()),
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    (out / "manifest_k562.json").write_text(json.dumps(manifest, indent=2) + "\n")
    volume.commit()
    return {"status": "completed", "npz": str(stem) + ".npz", "manifest": manifest}


@app.local_entrypoint()
def main(
    source: str,
    run_id: str = "",
    targets_file: str = "",
    all_source_targets: bool = False,
    out_subdir: str = "",
    probe: bool = False,
):
    if probe:
        print(json.dumps(probe_xatlas.remote(source), indent=2))
        return
    _check_run_id(run_id)
    targets = _read_targets_file(targets_file) if targets_file else None
    if source in XATLAS_ARMS:
        result = extract_xatlas.remote(source, run_id, targets, all_source_targets, out_subdir)
    elif source == "cd4":
        result = extract_cd4.remote(run_id, targets, all_source_targets, out_subdir)
    elif source == "k562":
        result = extract_k562.remote(run_id, targets, all_source_targets, out_subdir)
    else:
        raise ValueError("source must be hct116, hek293t, cd4, or k562")
    print(json.dumps(result, indent=2))
