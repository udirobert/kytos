"""Extract PER-SAMPLE delta statistics from X-Atlas Orion (k036).

Why this job exists
-------------------
The Atlas oracle (experiments/_embargoed/k025-eval2-gate/
gate-local-20260930-03/analysis.md) showed per-batch sign agreement
predicts replication: genes where >=0.85 of a target's batches agree on
the delta sign replicate at high split-half cosine (measured value
embargoed with the oracle round). This job emits the
ingredients for the same within-source sign-agreement gate on the two
X-Atlas Orion lines (hct116 S=109 samples, hek293t S=223 samples;
median n_samples/target 78 / 116), genome-wide so it also serves the
final phase's all-source consensus.

Per (target, gene) emitted (panel 18,533-gene axis):
  ``n_samples_voting``   (T,) int32 -- samples where the target has >=1
                         perturbed cell AND that sample has >=1 control
                         cell (after the 150/sample cap)
  ``pos_count``          (T,G) int16 -- voting samples with d > 0
  ``neg_count``          (T,G) int16 -- voting samples with d < 0
  ``mean_sample_delta``  (T,G) float32 -- mean over voting samples of
                         d(t,s,g) = mean(log1p) of target t in sample s
                         minus mean(log1p) of sample s's controls
  ``e2_sample_delta``    (T,G) float32 -- E[d^2] over voting samples
                         (var = e2 - mean^2)
plus ``genes``, ``targets``, ``n_cells`` (perturbed cells), ``covered``.

Why shards on disk
------------------
The quantities are functions of the per-(sample,target) group MEAN, which
cannot be decomposed into per-row updates (sign and d^2 both need the
finished group sum). A dense (groups x genes) accumulator is ~1.5M x 18.5k
-- far too big. Instead the proven sequential expression.lance scan
(identical filtering to modal_k023_xatlas_extract --all-source-targets)
appends kept rows as packed 8-byte records (group u4, panel-col u2,
log1p(value) f16) to per-shard binary files on the volume, partitioned by
contiguous 256-target ranges. Each shard is then reduced independently:
np.bincount over (local_group * G + col) yields dense group sums, each
group is paired with its own sample's control mean, and the emitted
per-target statistics are final (all groups of a target live in one
shard). Shard files are the only large intermediate (~118 GB hct116,
~197 GB hek293t on the volume) and are deleted after a successful merge;
the per-256-target ``shardstats_*.npz`` slices are kept as the documented
per-target-shard fallback.

Resume
------
``state.json`` in the work dir records scan progress (rows scanned, kept,
per-shard record counts) at every buffer flush and postprocess progress
per shard. On restart, shard files are truncated back to the recorded
record counts (a crash mid-flush may have appended uncommitted tail
bytes) and the scan resumes at the recorded row offset; finished shards
and a finished merge are never redone. ``{source}_samplestats.npz``
existing => the run is complete.

Run:
  modal run --detach tools/modal_k036_xatlas_samplestats.py --source hct116
  modal run --detach tools/modal_k036_xatlas_samplestats.py --source hek293t
  modal run tools/modal_k036_xatlas_samplestats.py --source hct116 --probe
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
OUT_DIR = VOLUME_ROOT / "k036-samplestats"
PANEL_COUNTS = REMOTE_ROOT / "data/vcc2026/pert_counts.csv"
PANEL_GENES = REMOTE_ROOT / "data/vcc2026/gene_names.csv"

HF_XATLAS = "hf://datasets/slaf-project/X-Atlas-Orion/data/{}"
XATLAS_ARMS = {"hct116": "HCT116", "hek293t": "HEK293T"}
XATLAS_CONTROL = "Non-Targeting"
CONTROL_CAP_PER_SAMPLE = 150
SCAN_BATCH_ROWS = 2_000_000
SCAN_MAX_RETRIES = 20
# Flush buffered scan records to the volume shard files when total buffered
# records exceed this (1e9 records x 8B = 8 GB per flush round). Larger
# flushes mean fewer volume.commit() calls -- the commit stall is what
# throttles the scan loop (observed ~3x slowdown at 256M).
FLUSH_RECORDS = 1_000_000_000
# Targets per postprocess shard. The per-shard dense group-sum bincount is
# (SHARD_TARGETS x n_samples x panel_genes) float64: 256x223x18533x8 =
# ~8.5 GB worst case (hek293t) -- safe in 48 GB.
SHARD_TARGETS = 256

# Coverage depth thresholds reported in the manifest.
COVERAGE_DEPTHS = (1, 2, 3, 5, 10, 20, 50, 100, 200)

app = modal.App("kytos-k036-samplestats")
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
    return [modal.Secret.from_name("kytos-hf")]


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
    """Cardinality + contiguity probe for the samplestats design.

    Reports n_samples / n_gene_targets (sizes the group encoding) and how
    clustered (sample, gene_target) groups are in cell_integer_id order
    (runs_per_group = 1.0 would mean a streaming single pass without
    shard files were possible; informational only).
    """
    if source not in XATLAS_ARMS:
        raise ValueError(f"source must be one of {sorted(XATLAS_ARMS)}")
    import numpy as np
    import lance

    base = HF_XATLAS.format(XATLAS_ARMS[source])
    cells = (
        lance.dataset(f"{base}/cells.lance")
        .scanner(columns=["cell_integer_id", "sample", "gene_target"])
        .to_table()
        .to_pandas()
        .sort_values("cell_integer_id")
    )
    targets = sorted(set(cells["gene_target"].astype(str)) - {XATLAS_CONTROL})
    pair = list(zip(cells["sample"].astype(str), cells["gene_target"].astype(str)))
    runs = 1 + sum(1 for a, b in zip(pair, pair[1:]) if a != b)
    n_groups = len(set(pair))
    per_target_samples = (
        cells[cells["gene_target"] != XATLAS_CONTROL].groupby("gene_target")["sample"].nunique()
    )
    return {
        "source": source,
        "n_cells": int(len(cells)),
        "n_samples": int(cells["sample"].nunique()),
        "n_gene_targets": len(targets),
        "n_sample_target_groups": n_groups,
        "contiguous_runs": runs,
        "runs_per_group": round(runs / max(n_groups, 1), 3),
        "median_samples_per_target": float(per_target_samples.median()),
        "median_cells_per_group": float(
            np.median(
                cells[cells["gene_target"] != XATLAS_CONTROL]
                .groupby(["gene_target", "sample"])
                .size()
            )
        ),
    }


def _load_cells_meta(source: str):
    """Cells table -> group encoding + per-group cell counts.

    group_id = target_idx * S + sample_idx for perturbed cells;
    CTRL_BASE + sample_idx for (capped) control cells.
    """
    import numpy as np
    import lance

    base = HF_XATLAS.format(XATLAS_ARMS[source])
    cells = (
        lance.dataset(f"{base}/cells.lance")
        .scanner(columns=["cell_integer_id", "sample", "gene_target"])
        .to_table()
        .to_pandas()
    )
    samples = sorted(cells["sample"].astype(str).unique())
    s_pos = {s: i for i, s in enumerate(samples)}
    S = len(samples)
    targets = sorted(set(cells["gene_target"].astype(str)) - {XATLAS_CONTROL})
    t_pos = {t: i for i, t in enumerate(targets)}
    T = len(targets)
    ctrl_base = T * S

    is_ctrl = cells["gene_target"] == XATLAS_CONTROL
    pert = cells[~is_ctrl]
    # Same control cap as the k023 extractor: first 150 controls/sample.
    ctrl = cells[is_ctrl].groupby("sample", sort=False).head(CONTROL_CAP_PER_SAMPLE)

    cell_group = np.full(int(cells["cell_integer_id"].max()) + 1, -1, dtype=np.int64)
    cell_group[pert["cell_integer_id"].to_numpy()] = pert["gene_target"].map(t_pos).to_numpy(
        dtype=np.int64
    ) * S + pert["sample"].map(s_pos).to_numpy(dtype=np.int64)
    cell_group[ctrl["cell_integer_id"].to_numpy()] = ctrl_base + ctrl["sample"].map(s_pos).to_numpy(
        dtype=np.int64
    )

    group_cells = np.bincount(cell_group[cell_group >= 0], minlength=ctrl_base + S).astype(np.int64)
    return {
        "cells": cells,
        "samples": samples,
        "targets": targets,
        "S": S,
        "T": T,
        "ctrl_base": ctrl_base,
        "cell_group": cell_group,
        "group_cells": group_cells,
        "ctrl_cells": group_cells[ctrl_base : ctrl_base + S],
    }


def _rec_dtype():
    import numpy as np

    return np.dtype([("grp", "<u4"), ("col", "<u2"), ("val", "<f2")])


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=21600,
    startup_timeout=300,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
    secrets=_hf_secret(),
)
def samplestats_xatlas(
    source: str,
    shard_targets: int = SHARD_TARGETS,
    panel_targets_vol_path: str = "",
) -> dict:
    """Scan -> shard files -> per-shard stats -> merged npz + manifest."""
    import hashlib
    import sys
    import time

    import numpy as np
    import pandas as pd

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd

    if source not in XATLAS_ARMS:
        raise ValueError(f"source must be one of {sorted(XATLAS_ARMS)}")

    REC = _rec_dtype()
    rec_bytes = REC.itemsize
    out = OUT_DIR
    work = out / f"{source}_work"
    shards_dir = work / "shards"
    stats_dir = work / "shardstats"
    final_npz = out / f"{source}_samplestats.npz"
    manifest_path = out / f"manifest_{source}.json"
    state_path = work / "state.json"
    out.mkdir(parents=True, exist_ok=True)

    if final_npz.exists() and manifest_path.exists():
        return {"status": "completed", "npz": str(final_npz), "resumed_done": True}

    shards_dir.mkdir(parents=True, exist_ok=True)
    stats_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    base = HF_XATLAS.format(XATLAS_ARMS[source])
    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    G = len(panel_genes)

    meta = _load_cells_meta(source)
    S, T, ctrl_base = meta["S"], meta["T"], meta["ctrl_base"]
    cell_group = meta["cell_group"]
    group_cells = meta["group_cells"]
    targets_requested = meta["targets"]
    n_shards = (T + shard_targets - 1) // shard_targets
    shard_span = shard_targets * S  # group ids per pert shard
    ctrl_shard = n_shards  # last file index holds capped control rows
    print(
        f"[{source}] T={T} S={S} shards={n_shards} ctrl_base={ctrl_base}",
        flush=True,
    )

    import lance

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
    gene_to_panel = np.full(len(genes_tbl), -1, dtype=np.int32)
    gene_to_panel[positions[positions >= 0]] = np.flatnonzero(positions >= 0)

    shard_paths = [shards_dir / f"shard_{i:04d}.bin" for i in range(n_shards + 1)]

    # ---- state / resume ------------------------------------------------
    state = {
        "phase": "scan",
        "scanned": 0,
        "kept": 0,
        "retries": 0,
        "shard_records": [0] * (n_shards + 1),
        "shards_done": [],
        "ctrl_done": False,
    }
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            pass
    if len(state.get("shard_records", [])) != n_shards + 1:
        raise ValueError("state shard layout does not match shard_targets")

    def _write_state():
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.rename(state_path)

    scanned = int(state.get("scanned", 0))
    kept = int(state.get("kept", 0))
    retries = int(state.get("retries", 0))
    # Truncate shard files back to the committed record counts -- a crash
    # mid-flush may have left extra bytes the state does not know about.
    for i, p in enumerate(shard_paths):
        want = int(state["shard_records"][i]) * rec_bytes
        if p.exists():
            if p.stat().st_size != want:
                with p.open("r+b") as fh:
                    fh.truncate(want)
        else:
            p.touch()

    # ---- phase: scan ---------------------------------------------------
    if state["phase"] == "scan":
        buffers = [[] for _ in range(n_shards + 1)]
        buffered = 0

        def _flush():
            nonlocal buffered
            for i, bufs in enumerate(buffers):
                if not bufs:
                    continue
                arr = np.concatenate(bufs) if len(bufs) > 1 else bufs[0]
                with shard_paths[i].open("ab") as fh:
                    arr.tofile(fh)
                state["shard_records"][i] += int(arr.size)
                bufs.clear()
            state["scanned"] = scanned
            state["kept"] = kept
            state["retries"] = retries
            _write_state()
            volume.commit()
            buffered = 0
            print(f"[{source}] flush at {scanned} rows (kept {kept})", flush=True)

        while True:
            scanner = expression.scanner(batch_size=SCAN_BATCH_ROWS, offset=scanned)
            try:
                for batch in scanner.to_batches():
                    if not batch.num_rows:
                        continue
                    cid = batch.column("cell_integer_id").to_numpy()
                    gid = batch.column("gene_integer_id").to_numpy()
                    val = batch.column("value").to_numpy()
                    grp = np.where(
                        cid < len(cell_group),
                        cell_group[np.clip(cid, 0, len(cell_group) - 1)],
                        -1,
                    )
                    pos = np.where(
                        gid < len(gene_to_panel),
                        gene_to_panel[np.clip(gid, 0, len(gene_to_panel) - 1)],
                        -1,
                    )
                    keep = (grp >= 0) & (pos >= 0)
                    n_keep = int(keep.sum())
                    if n_keep:
                        g = grp[keep]
                        is_ctrl = g >= ctrl_base
                        shard_idx = np.where(is_ctrl, ctrl_shard, g // shard_span)
                        rec = np.empty(n_keep, dtype=REC)
                        rec["grp"] = np.where(is_ctrl, g - ctrl_base, g).astype(np.uint32)
                        rec["col"] = pos[keep].astype(np.uint16)
                        rec["val"] = np.log1p(val[keep].astype(np.float32)).astype(np.float16)
                        order = np.argsort(shard_idx, kind="stable")
                        s_sorted = shard_idx[order]
                        rec_sorted = rec[order]
                        bounds = np.flatnonzero(
                            np.diff(np.concatenate([[-1], s_sorted, [n_shards + 1]]))
                        )
                        for k in range(len(bounds) - 1):
                            lo, hi = int(bounds[k]), int(bounds[k + 1])
                            buffers[int(s_sorted[lo])].append(rec_sorted[lo:hi])
                        buffered += n_keep
                    kept += n_keep
                    scanned += batch.num_rows
                    if buffered >= FLUSH_RECORDS:
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
        state["phase"] = "post"
        _write_state()
        volume.commit()
        print(f"[{source}] scan done: {scanned} rows, kept {kept}", flush=True)
        del buffers

    # ---- phase: per-sample control means -------------------------------
    ctrl_means_path = work / "ctrl_means.npy"
    if not state.get("ctrl_done"):
        ctrl_rec = np.fromfile(shard_paths[ctrl_shard], dtype=REC)
        flat = ctrl_rec["grp"].astype(np.int64) * G + ctrl_rec["col"].astype(np.int64)
        sums = np.bincount(
            flat, weights=ctrl_rec["val"].astype(np.float64), minlength=S * G
        ).reshape(S, G)
        ctrl_n = meta["ctrl_cells"]
        ctrl_means_w = np.zeros((S, G), dtype=np.float32)
        ok = ctrl_n > 0
        ctrl_means_w[ok] = (sums[ok] / ctrl_n[ok, None]).astype(np.float32)
        tmp_cm = work / "ctrl_means.tmp.npy"
        np.save(tmp_cm, ctrl_means_w)
        tmp_cm.rename(ctrl_means_path)
        state["ctrl_done"] = True
        _write_state()
        volume.commit()
        del ctrl_rec, flat, sums
        print(f"[{source}] ctrl means done ({int(ok.sum())}/{S} samples)", flush=True)

    ctrl_means = np.load(ctrl_means_path)
    ctrl_ok = meta["ctrl_cells"] > 0

    # ---- phase: per-shard statistics -----------------------------------
    done_shards = set(int(i) for i in state.get("shards_done", []))
    s_arange = np.arange(S)
    for shard in range(n_shards):
        if shard in done_shards:
            continue
        t_lo = shard * shard_targets
        t_hi = min(t_lo + shard_targets, T)
        rec = np.fromfile(shard_paths[shard], dtype=REC)
        n_t = t_hi - t_lo
        n_local = n_t * S
        loc = rec["grp"].astype(np.int64) - np.int64(t_lo) * S
        flat = loc * G + rec["col"].astype(np.int64)
        gsums = np.bincount(
            flat, weights=rec["val"].astype(np.float64), minlength=n_local * G
        ).reshape(n_t, S, G)
        del rec, flat, loc

        gcells = group_cells[t_lo * S : t_hi * S].reshape(n_t, S)
        voting = (gcells > 0) & ctrl_ok[None, :]

        n_voting = np.zeros(n_t, dtype=np.int32)
        pos_count = np.zeros((n_t, G), dtype=np.int16)
        neg_count = np.zeros((n_t, G), dtype=np.int16)
        mean_d = np.zeros((n_t, G), dtype=np.float32)
        e2_d = np.zeros((n_t, G), dtype=np.float32)
        for i in range(n_t):
            v = voting[i]
            m = int(v.sum())
            n_voting[i] = m
            if m == 0:
                continue
            d = gsums[i][v] / gcells[i][v, None] - ctrl_means[s_arange[v]]
            pos_count[i] = (d > 0).sum(axis=0).astype(np.int16)
            neg_count[i] = (d < 0).sum(axis=0).astype(np.int16)
            mean_d[i] = (d.sum(axis=0) / m).astype(np.float32)
            e2_d[i] = ((d * d).sum(axis=0) / m).astype(np.float32)
        del gsums

        tmp_sz = stats_dir / f"shardstats_{shard:04d}.tmp.npz"
        np.savez_compressed(
            str(tmp_sz),
            targets=np.asarray(targets_requested[t_lo:t_hi]),
            n_samples_voting=n_voting,
            pos_count=pos_count,
            neg_count=neg_count,
            mean_sample_delta=mean_d,
            e2_sample_delta=e2_d,
        )
        tmp_sz.rename(stats_dir / f"shardstats_{shard:04d}.npz")
        done_shards.add(shard)
        state["shards_done"] = sorted(done_shards)
        _write_state()
        volume.commit()
        print(f"[{source}] shard {shard + 1}/{n_shards} done", flush=True)

    # ---- phase: merge --------------------------------------------------
    n_voting = np.zeros(T, dtype=np.int32)
    pos_all = np.zeros((T, G), dtype=np.int16)
    neg_all = np.zeros((T, G), dtype=np.int16)
    mean_all = np.zeros((T, G), dtype=np.float32)
    e2_all = np.zeros((T, G), dtype=np.float32)
    for shard in range(n_shards):
        t_lo = shard * shard_targets
        t_hi = min(t_lo + shard_targets, T)
        with np.load(stats_dir / f"shardstats_{shard:04d}.npz") as z:
            n_voting[t_lo:t_hi] = z["n_samples_voting"]
            pos_all[t_lo:t_hi] = z["pos_count"]
            neg_all[t_lo:t_hi] = z["neg_count"]
            mean_all[t_lo:t_hi] = z["mean_sample_delta"]
            e2_all[t_lo:t_hi] = z["e2_sample_delta"]

    pert_cells = meta["cells"][meta["cells"]["gene_target"] != XATLAS_CONTROL]
    n_cells = (
        pert_cells.groupby("gene_target")
        .size()
        .reindex(targets_requested, fill_value=0)
        .to_numpy(dtype=np.int64)
    )
    covered = n_voting > 0

    tmp_npz = out / f"{source}_samplestats.tmp.npz"
    np.savez_compressed(
        str(tmp_npz),
        genes=np.asarray(panel_genes),
        targets=np.asarray(targets_requested),
        n_samples_voting=n_voting,
        n_cells=n_cells,
        covered=covered,
        pos_count=pos_all,
        neg_count=neg_all,
        mean_sample_delta=mean_all,
        e2_sample_delta=e2_all,
    )
    tmp_npz.rename(final_npz)
    volume.commit()

    digest = hashlib.sha256()
    with final_npz.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            digest.update(chunk)

    def _cov(mask):
        nv = n_voting[mask]
        return {
            "n_targets": int(mask.sum()),
            "covered": int((nv > 0).sum()),
            "median_voting_samples": float(np.median(nv)) if len(nv) else 0.0,
            "mean_voting_samples": round(float(nv.mean()), 2) if len(nv) else 0.0,
            "targets_with_at_least_N_voting": {
                str(d): int((nv >= d).sum()) for d in COVERAGE_DEPTHS
            },
        }

    coverage = {"all_targets": _cov(np.ones(T, dtype=bool))}
    if panel_targets_vol_path:
        p = VOLUME_ROOT / panel_targets_vol_path
        if p.exists():
            want = {ln.strip() for ln in p.read_text().splitlines() if ln.strip()}
            tpos = {t: i for i, t in enumerate(targets_requested)}
            idx = [tpos[t] for t in want if t in tpos]
            panel_mask = np.zeros(T, dtype=bool)
            panel_mask[np.asarray(idx, dtype=np.int64)] = True
            coverage["panel_subset"] = _cov(panel_mask)
            coverage["panel_subset"]["targets_requested_in_file"] = len(want)
            coverage["panel_subset"]["targets_matched"] = len(idx)
            coverage["panel_subset"]["targets_file"] = str(p)

    manifest = {
        "source": source,
        "dataset": HF_XATLAS.format(XATLAS_ARMS[source]),
        "control_label": XATLAS_CONTROL,
        "control_cap_per_sample": CONTROL_CAP_PER_SAMPLE,
        "target_selection": "all_source_targets",
        "shard_targets": shard_targets,
        "n_samples": S,
        "samples_with_controls": int(ctrl_ok.sum()),
        "expression_rows_scanned": int(scanned),
        "expression_rows_kept": int(kept),
        "expression_table_rows": int(total_rows),
        "scan_retries": retries,
        "targets_requested": T,
        "targets_covered": int(covered.sum()),
        "panel_genes": G,
        "panel_genes_missing_from_source": missing_genes,
        "units": {
            "per_sample_delta": "mean(log1p(raw)) of target in sample minus "
            "mean(log1p(raw)) of that sample's capped controls",
            "mean_sample_delta": "mean over voting samples of per_sample_delta",
            "e2_sample_delta": "mean over voting samples of "
            "per_sample_delta^2 (variance = e2 - mean^2)",
            "pos_count": "voting samples with per_sample_delta > 0 (int16)",
            "neg_count": "voting samples with per_sample_delta < 0 (int16)",
            "n_samples_voting": "samples where target has cells AND sample "
            "has >=1 capped control (int32, per-target)",
            "sign_agreement": "consumer-side: max(pos,neg)/n_samples_voting",
        },
        "record_format": "shard bins: (grp u4, panel-col u2, log1p f16) 8B",
        "npz": str(final_npz),
        "npz_sha256": digest.hexdigest(),
        "shardstats_dir": str(stats_dir),
        "coverage": coverage,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    tmp_man = out / f"manifest_{source}.json.tmp"
    tmp_man.write_text(json.dumps(manifest, indent=2) + "\n")
    tmp_man.rename(manifest_path)
    state["phase"] = "done"
    _write_state()
    # Reclaim the large intermediate shard bins; keep shardstats npz
    # slices (documented per-256-target fallback) and ctrl_means.
    for p in shard_paths:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    volume.commit()
    return {"status": "completed", "npz": str(final_npz), "manifest": manifest}


@app.local_entrypoint()
def main(
    source: str,
    probe: bool = False,
    shard_targets: int = SHARD_TARGETS,
    panel_targets_vol_path: str = "",
):
    if probe:
        print(json.dumps(probe_xatlas.remote(source), indent=2))
        return
    result = samplestats_xatlas.remote(source, shard_targets, panel_targets_vol_path)
    print(json.dumps(result, indent=2))
