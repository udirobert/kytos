"""k201 — engine-v2 L0 evidence stores (phase 0) on Modal.

Why this job exists
-------------------
``docs/engine-v2-design.md`` §1 defines the evidence unit: per
(target, gene, dataset) -> lfc + se + p + q + z + n + kd_eff. Phase 0
re-expresses the sources we already own in that schema instead of the
v1 pooled-delta schema. Runs land on the volume under
``k201-evidence/<dataset_id>/``:

``stats.npz`` -- genes (G,), targets (T,), covered (T,bool),
  lfc/se/p/q/z (T,G) float32 (NaN where not estimable),
  n_voting (T,G) int16, kd_eff (T,) float32
``manifest.json`` -- provenance, estimation protocol, se_kind, units.

Stages
------
``hct116`` / ``hek293t`` -- Welch-t over the k036 per-sample vote
  stores (``k036-samplestats/<src>_samplestats.npz``). Per-sample deltas
  are already control-paired; a one-sample t over voting samples is the
  honest statistic. No rescan needed.
``k562`` -- Replogle GWPS raw h5ad streamed from Figshare. Per-sample =
  per-``gem_group``: packed per-shard records then per-shard bincount
  reduce (the k036 pattern), Welch-t over gem groups per target.
``cd4`` -- Marson 2025 publisher DE-stats h5ad (sha256-pinned). Harvest
  log_fc + whatever uncertainty layers the publisher ships;
  quality-filtered contrasts as in the k023 extract.
``h1`` -- 2025 VCC training h5ad from the volume. Per-batch column if
  present in obs, else deterministic pseudo-batches by barcode hash
  (flagged pseudorep in manifest -- L1 must downweight).

Run per source:
  modal run -d tools/modal_k201_evidence_l0.py --source hct116
  modal run -d tools/modal_k201_evidence_l0.py --source k562
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
OUT_DIR = VOLUME_ROOT / "k201-evidence"
PANEL_GENES = REMOTE_ROOT / "data/vcc2026/gene_names.csv"

REPLOGLE_URL = "https://ndownloader.figshare.com/files/35775507"
CD4_URL = (
    "https://genome-scale-tcell-perturb-seq.s3.amazonaws.com/marson2025_data/GWCD4i.DE_stats.h5ad"
)
CD4_SHA256 = "c355f535ff32cf7ba1edc49cf9c6039fe84f2c9ebe4d005515cba75790cfbb62"
H1_PATH = VOLUME_ROOT / "h1-2025-train/adata_Training.h5ad"
K036_ROOT = VOLUME_ROOT / "k036-samplestats"
NTC_LABEL = "non-targeting"

ROW_CHUNK = 20_000
SHARD_TARGETS = 128  # per-shard reduce stays < ~10 GB at n_gems~500
MIN_SAMPLES = 3  # Welch-t needs >=3 voting samples to emit se/p

app = modal.App("kytos-k201-evidence-l0")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "scipy==1.15.3",
        "pandas==2.2.3",
        "h5py==3.13.0",
        "anndata==0.11.4",
        "fsspec==2024.12.0",
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
)


def _check_source(source: str) -> None:
    if source not in {"hct116", "hek293t", "k562", "cd4", "h1"}:
        raise ValueError(f"unknown source {source!r}")


def _bh_q(p):
    """Benjamini-Hochberg q-values over finite entries of a (G,) p-array."""
    import numpy as np

    q = np.full(p.shape, np.nan, dtype=np.float64)
    idx = np.flatnonzero(np.isfinite(p))
    if not idx.size:
        return q
    order = idx[np.argsort(p[idx])]
    m = float(order.size)
    qv = p[order] * m / np.arange(1, order.size + 1)
    qv = np.minimum.accumulate(qv[::-1])[::-1]
    q[order] = np.minimum(qv, 1.0)
    return q


def _welch_from_moments(mean_d, e2_d, n_d, row_chunk=2048):
    """One-sample t over per-sample deltas -> (se, p, z) float32.

    mean_d/e2_d: (T,G) E[d], E[d^2]. n_d: (T,) or (T,G) sample counts.
    Chunked over targets so peak f64 scratch stays ~row_chunk x G.
    Returns se/p/z (T,G) float32, NaN where n < MIN_SAMPLES.
    """
    import numpy as np
    from scipy import stats

    T, G = mean_d.shape
    se = np.full((T, G), np.nan, dtype=np.float32)
    p = np.full((T, G), np.nan, dtype=np.float32)
    z = np.full((T, G), np.nan, dtype=np.float32)
    n_2d = n_d.ndim == 2
    for r0 in range(0, T, row_chunk):
        r1 = min(r0 + row_chunk, T)
        m = np.asarray(mean_d[r0:r1], dtype=np.float64)
        e2 = np.asarray(e2_d[r0:r1], dtype=np.float64)
        n = np.asarray(n_d[r0:r1] if n_2d else n_d[r0:r1, None], dtype=np.float64)
        if n.shape != m.shape:
            n = np.broadcast_to(n, m.shape)
        var = np.maximum(e2 - m * m, 0.0)
        var_unb = var * np.where(n > 1, n / np.maximum(n - 1, 1), 0.0)
        se_c = np.sqrt(var_unb / np.maximum(n, 1))
        ok = n >= MIN_SAMPLES
        t = np.divide(m, se_c, out=np.zeros_like(m), where=se_c > 0)
        p_c = np.full(m.shape, np.nan)
        df = np.maximum(n[ok] - 1, 1)
        p_c[ok] = 2.0 * stats.t.sf(np.abs(t[ok]), df)
        z_c = stats.norm.isf(np.clip(p_c / 2.0, 1e-300, 0.5)) * np.sign(m)
        z_c = np.where(np.isfinite(z_c), z_c, np.sign(m) * 40.0)
        se[r0:r1] = np.where(ok, se_c, np.nan)
        p[r0:r1] = np.where(ok, p_c, np.nan)
        z[r0:r1] = np.where(ok, z_c, np.nan)
    return se, p, z


def _emit(out, genes, targets, covered, lfc, se, p, z, n_voting, kd_eff, manifest):
    import numpy as np

    out.mkdir(parents=True, exist_ok=True)
    q = np.full(p.shape, np.nan, dtype=np.float32)
    for i in range(p.shape[0]):
        q[i] = _bh_q(p[i])
    np.savez_compressed(
        str(out / "stats.npz"),
        genes=np.asarray(genes),
        targets=np.asarray(targets),
        covered=np.asarray(covered, dtype=bool),
        lfc=lfc.astype(np.float32),
        se=se.astype(np.float32),
        p=p.astype(np.float32),
        q=q,
        z=z.astype(np.float32),
        n_voting=n_voting.astype(np.int16),
        kd_eff=kd_eff.astype(np.float32),
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    volume.commit()
    return {
        "status": "ok",
        "out": str(out),
        "targets": int(len(targets)),
        "covered": int(np.asarray(covered).sum()),
    }


def _kd_eff_from_self(targets, genes, lfc):
    """Negative self-gene lfc as KD-efficiency proxy (clip at 0)."""
    import numpy as np

    gpos = {g: i for i, g in enumerate(genes)}
    eff = np.full(len(targets), np.nan, dtype=np.float64)
    for i, t in enumerate(targets):
        j = gpos.get(str(t))
        if j is not None and np.isfinite(lfc[i, j]):
            eff[i] = max(-float(lfc[i, j]), 0.0)
    return eff


def _group_delta_welch(sums, cnts, ntc_sums, ntc_cnts, n_targets, n_genes, keep_cols_mask):
    """Shared reduce: per-(target,sample) group means -> moments -> Welch-t.

    sums/cnts: (T+1, n_samples) sums over log1p and cell counts, panel cols
    already mapped into ``keep_cols`` order... NO — sums is (T+1, S, K) over
    the kept panel cols; we emit into the full n_genes axis via
    keep_cols_mask (K,) bool over n_genes.
    """
    import numpy as np

    k_kept = sums.shape[2]
    ntc_mean = ntc_sums / np.maximum(ntc_cnts, 1)[:, None]  # (S, K)
    mean_d = np.zeros((n_targets, k_kept))
    e2_d = np.zeros((n_targets, k_kept))
    n_v = np.zeros((n_targets, k_kept), dtype=np.int16)
    covered = np.zeros(n_targets, dtype=bool)
    for t_i in range(n_targets):
        valid = (cnts[t_i] > 0) & (ntc_cnts > 0)
        nv = int(valid.sum())
        if nv == 0:
            continue
        covered[t_i] = True
        group_mean = sums[t_i, valid] / cnts[t_i, valid][:, None]
        d = group_mean - ntc_mean[valid]
        n_v[t_i, :] = nv
        mean_d[t_i] = d.mean(axis=0)
        e2_d[t_i] = (d * d).mean(axis=0)
    # expand kept-cols -> full axis
    mean_full = np.full((n_targets, n_genes), np.nan)
    e2_full = np.zeros((n_targets, n_genes))
    n_full = np.zeros((n_targets, n_genes), dtype=np.int16)
    mean_full[:, keep_cols_mask] = mean_d
    e2_full[:, keep_cols_mask] = e2_d
    n_full[:, keep_cols_mask] = n_v
    se, p, z = _welch_from_moments(
        np.where(np.isfinite(mean_full), mean_full, 0.0), e2_full, n_full
    )
    return mean_full, se, p, z, n_full, covered


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(24576, 24576),  # several (T,G) float64 arrays at once
    timeout=3600,
    volumes={"/kytos-vol": volume},
)
def extract_xatlas(source: str, run_id: str) -> dict:
    """Welch-t over k036 per-sample stores -> L0 for hct116/hek293t."""
    import numpy as np

    out = OUT_DIR / source / run_id
    if (out / "stats.npz").exists():
        return {"status": "exists", "out": str(out)}

    npz_path = K036_ROOT / f"{source}_samplestats.npz"
    with np.load(npz_path, allow_pickle=False) as d:
        genes = d["genes"].astype(str).tolist()
        targets = d["targets"].astype(str).tolist()
        covered = d["covered"].astype(bool)
        # float32 stores: keep f32 in memory, chunk up to f64 in welch
        mean_d = d["mean_sample_delta"]
        e2_d = d["e2_sample_delta"]
        n_t = d["n_samples_voting"].astype(np.int64)

    se, p, z = _welch_from_moments(mean_d, e2_d, n_t)
    lfc = np.asarray(mean_d)
    covered &= n_t >= 1
    kd_eff = _kd_eff_from_self(targets, genes, lfc)

    manifest = {
        "dataset_id": f"xatlas-{source}",
        "run_id": run_id,
        "lfc_kind": "log1p-sc",
        "se_kind": "welch-per-sample",
        "estimation": (
            "one-sample Welch t over per-sample control-paired log1p "
            "deltas; stats from k036-samplestats vote stores"
        ),
        "sample_unit": "xatlas replicate sample",
        "assay": "sc-crnispri",
        "context": source,
        "median_n_voting": float(np.median(n_t)),
        "emit_stats_rows": int((n_t >= MIN_SAMPLES).sum()),
        "source_store": str(npz_path),
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    n_voting = np.broadcast_to(n_t[:, None], lfc.shape).astype(np.int16)
    return _emit(out, genes, targets, covered, lfc, se, p, z, n_voting, kd_eff, manifest)


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=21600,
    volumes={"/kytos-vol": volume},
    ephemeral_disk=524288,  # Modal floor is 512 GiB; shard files ~tens of GiB
    retries=modal.Retries(max_retries=2, backoff_coefficient=1.0),
)
def extract_k562(run_id: str) -> dict:
    """Replogle GWPS per-gem_group Welch-t -> L0 (packed-shard scan)."""
    import sys

    import fsspec
    import h5py
    import numpy as np
    import pandas as pd

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd

    out = OUT_DIR / "k562" / run_id
    if (out / "stats.npz").exists():
        return {"status": "exists", "out": str(out)}
    out.mkdir(parents=True, exist_ok=True)
    work = Path("/tmp/k201-shards")
    work.mkdir(exist_ok=True)

    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    n_genes = len(panel_genes)

    t0 = time.time()
    with fsspec.open(REPLOGLE_URL, "rb") as fh:
        h5 = h5py.File(fh, "r")
        gene_cats = h5["obs/__categories/gene"].asstr()[:]
        gene_codes = h5["obs/gene"][:]
        gems = h5["obs/gem_group"][:].astype(np.int64)
        n_gems = int(gems.max()) + 1

        # bucket 0..T-1 = source targets (sorted), T = NTC; -1 = unmapped
        target_cats = sorted(g for g in gene_cats if g != NTC_LABEL)
        n_targets = len(target_cats)
        t_index = {str(g): b for b, g in enumerate(target_cats)}
        cat_to_bucket = np.full(len(gene_cats), -1, dtype=np.int32)
        for i, g in enumerate(gene_cats):
            cat_to_bucket[i] = t_index.get(str(g), n_targets)
        targets = target_cats
        ntc_bucket = n_targets

        var_genes = h5["var/__categories/gene_name"].asstr()[:][h5["var/gene_name"][:]]
        pos_arr, _missing = cd.map_gene_axis(var_genes.tolist(), panel_genes)
        gene_to_panel = np.full(len(var_genes), -1, dtype=np.int32)
        gene_to_panel[pos_arr[pos_arr >= 0]] = np.flatnonzero(pos_arr >= 0)
        panel_cols = np.flatnonzero(gene_to_panel >= 0)
        col_panel_pos = gene_to_panel[panel_cols].astype(np.int64)

        n_shards = (n_targets + 1 + SHARD_TARGETS - 1) // SHARD_TARGETS
        shard_fh = [open(work / f"shard_{i:04d}.bin", "wb") for i in range(n_shards)]
        # cell counts per (bucket, gem) — small dense
        cnts = np.zeros((n_targets + 1, n_gems), dtype=np.int64)

        bucket = cat_to_bucket[gene_codes]
        keep = bucket >= 0
        X = h5["X"]
        n_cells = X.shape[0]
        n_kept = int(keep.sum())
        rec_dtype = np.dtype([("lb", "<u2"), ("gem", "<u2"), ("col", "<u2"), ("val", "<f4")])
        print(
            f"cells={n_cells} kept={n_kept} targets={n_targets} gems={n_gems} shards={n_shards}",
            flush=True,
        )
        for r0 in range(0, n_cells, ROW_CHUNK):
            r1 = min(r0 + ROW_CHUNK, n_cells)
            sel = np.flatnonzero(keep[r0:r1])
            if not sel.size:
                continue
            block = np.asarray(X[r0:r1][sel][:, panel_cols])
            block = np.log1p(np.clip(block, 0, None))
            b = bucket[r0:r1][sel].astype(np.int64)
            g = gems[r0:r1][sel]
            np.add.at(cnts, (b, g), 1)
            shard_ids = b // SHARD_TARGETS
            for sid in np.unique(shard_ids):
                m = shard_ids == sid
                sub_blk = block[m]
                nz_r, nz_c = np.nonzero(sub_blk)
                if not nz_r.size:
                    continue
                recs = np.empty(nz_r.size, dtype=rec_dtype)
                recs["lb"] = (b[m] % SHARD_TARGETS)[nz_r].astype(np.uint16)
                recs["gem"] = g[m][nz_r].astype(np.uint16)
                recs["col"] = col_panel_pos[nz_c].astype(np.uint16)
                recs["val"] = sub_blk[nz_r, nz_c].astype(np.float32)
                recs.tofile(shard_fh[int(sid)])
            if (r0 // ROW_CHUNK) % 50 == 49:
                print(f"scan rows {r1}/{n_cells} ({time.time() - t0:.0f}s)", flush=True)
        for fh_ in shard_fh:
            fh_.close()

    # --- reduce: last shard first (contains NTC bucket), then targets ---
    print("scan done, reducing shards", flush=True)
    mean_full = np.full((n_targets, n_genes), np.nan)
    e2_full = np.zeros((n_targets, n_genes))
    n_full = np.zeros((n_targets, n_genes), dtype=np.int16)
    covered = np.zeros(n_targets, dtype=bool)
    ntc_sums = ntc_cnts = None

    order = sorted(
        range(n_shards), key=lambda s: (0 if (s + 1) * SHARD_TARGETS > n_targets else 1, s)
    )
    for sid in order:
        lo = sid * SHARD_TARGETS
        hi = min(lo + SHARD_TARGETS, n_targets + 1)
        nb = hi - lo
        recs = np.fromfile(work / f"shard_{sid:04d}.bin", dtype=rec_dtype)
        keys = (recs["lb"].astype(np.int64) * n_gems + recs["gem"]) * n_genes + recs["col"].astype(
            np.int64
        )
        sums = np.bincount(
            keys, weights=recs["val"].astype(np.float64), minlength=nb * n_gems * n_genes
        ).reshape(nb, n_gems, n_genes)
        del recs, keys
        for j, b in enumerate(range(lo, hi)):
            if b == ntc_bucket:
                ntc_sums = sums[j]
                ntc_cnts = cnts[b]
                break
        if ntc_sums is None:
            # NTC lives in the last shard; it is processed first in `order`
            continue
        ntc_mean = ntc_sums / np.maximum(ntc_cnts, 1)[:, None]
        for j, b in enumerate(range(lo, hi)):
            if b == ntc_bucket:
                continue
            grp_cnt = cnts[b]
            valid = (grp_cnt > 0) & (ntc_cnts > 0)
            nv = int(valid.sum())
            if nv == 0:
                continue
            covered[b] = True
            group_mean = sums[j, valid] / grp_cnt[valid][:, None]
            d = group_mean - ntc_mean[valid]
            n_full[b] = nv
            mean_full[b] = d.mean(axis=0)
            e2_full[b] = (d * d).mean(axis=0)
        del sums
        print(f"shard {sid} reduced ({time.time() - t0:.0f}s)", flush=True)

    se, p, z = _welch_from_moments(
        np.where(np.isfinite(mean_full), mean_full, 0.0), e2_full, n_full
    )
    lfc = mean_full
    kd_eff = _kd_eff_from_self(targets, panel_genes, lfc)
    manifest = {
        "dataset_id": "replogle-k562-gwps",
        "run_id": run_id,
        "lfc_kind": "log1p-sc",
        "se_kind": "welch-per-gemgroup",
        "estimation": (
            "per-(target,gem_group) group-mean log1p deltas vs same-gem "
            "NTC controls; one-sample Welch t over gem groups"
        ),
        "sample_unit": "gem_group",
        "n_gem_groups": int(n_gems),
        "assay": "sc-crnispri",
        "context": "k562",
        "dataset_url": REPLOGLE_URL,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return _emit(out, panel_genes, targets, covered, lfc, se, p, z, n_full, kd_eff, manifest)


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=21600,
    volumes={"/kytos-vol": volume},
)
def extract_cd4(run_id: str) -> dict:
    """Marson 2025 publisher DE stats -> L0."""
    import hashlib
    import sys

    import numpy as np
    import pandas as pd
    import requests

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd

    out = OUT_DIR / "cd4" / run_id
    if (out / "stats.npz").exists():
        return {"status": "exists", "out": str(out)}

    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    local = Path("/tmp/GWCD4i.DE_stats.h5ad")
    if not local.exists():
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
    layer_keys = list(adata.layers.keys())
    obs = adata.obs
    var_names = (
        adata.var["gene_name"].astype(str).to_numpy()
        if "gene_name" in adata.var.columns
        else adata.var_names.astype(str).to_numpy()
    )
    obs_target = obs["target_contrast_gene_name"].astype(str)
    targets = sorted(t for t in obs_target.unique() if t and t != "nan")
    sel = np.flatnonzero(obs_target.isin(targets).to_numpy())
    chosen = obs.iloc[sel]

    quality = (
        (chosen["n_guides"] >= 2)
        & ~chosen["single_guide_estimate"].astype(bool)
        & chosen["ontarget_significant"].astype(bool)
        & ~chosen["distal_offtarget_flag"].astype(bool)
        & ~chosen["low_target_gex"].astype(bool)
    ).to_numpy()

    positions, _missing = cd.map_gene_axis(list(var_names), panel_genes)
    keep_cols = positions >= 0
    pos_keep = positions[keep_cols]
    # h5py fancy indexing needs increasing indices: sort var cols, remap
    order = np.argsort(pos_keep)
    pos_sorted = pos_keep[order]
    inv_order = np.empty_like(order)
    inv_order[order] = np.arange(order.size)
    n_targets = len(targets)
    n_genes = len(panel_genes)

    lfc = np.full((n_targets, n_genes), np.nan)
    se = np.full_like(lfc, np.nan)
    p = np.full_like(lfc, np.nan)
    z = np.full_like(lfc, np.nan)
    n_voting = np.zeros((n_targets, n_genes), dtype=np.int16)
    covered = np.zeros(n_targets, dtype=bool)

    chosen_targets = chosen["target_contrast_gene_name"].astype(str).to_numpy()
    t_rows = {}
    for i, t in enumerate(targets):
        rows = np.flatnonzero((chosen_targets == t) & quality)
        if len(rows):
            covered[i] = True
            t_rows[i] = rows
            n_voting[i, keep_cols] = len(rows)

    se_layer_map = {
        "se": se,
        "std_error": se,
        "lfc_se": se,
        "pval": p,
        "p_value": p,
        "p": p,
        "zscore": z,
        "z": z,
    }
    wanted = ["log_fc"] + [k for k in se_layer_map if k in layer_keys]
    found = {}
    try:
        for key in wanted:
            dst = lfc if key == "log_fc" else se_layer_map[key]
            # slice (sel, mapped var cols) only -- bounded memory per layer
            mat = np.asarray(
                adata.layers[key][sel, :][:, pos_sorted],
                dtype=np.float32,
            )[:, inv_order]
            if key != "log_fc":
                found[key] = dst
            for i, rows in t_rows.items():
                vals = np.nanmean(mat[rows], axis=0)
                dst[i, keep_cols] = vals
            del mat
    finally:
        adata.file.close()
    se_kind = "publisher:" + ",".join(sorted(found)) if found else "none"
    # publisher file ships zscore + sparse p_value but no se layer; recover
    # Wald identities where absent: se = |lfc/z|, p = 2*sf(|z|)
    from scipy import stats as _st

    z_ok = np.isfinite(z) & (np.abs(z) > 0)
    se_der = np.abs(lfc / np.where(z_ok, z, np.nan))
    se = np.where(np.isfinite(se), se, np.where(np.isfinite(lfc) & z_ok, se_der, np.nan))
    p_der = 2.0 * _st.norm.sf(np.abs(z))
    p = np.where(np.isfinite(p), p, np.where(z_ok, p_der, np.nan))
    se_kind += ";se=|lfc/z|,p=2sf(|z|) where publisher sparse"
    kd_eff = _kd_eff_from_self(targets, panel_genes, lfc)
    manifest = {
        "dataset_id": "cd4-marson2025",
        "run_id": run_id,
        "lfc_kind": "log2fc-publisher",
        "se_kind": se_kind,
        "estimation": "publisher DE stats harvested; quality-filtered contrasts",
        "sample_unit": "publisher contrast (n_guides>=2, ontarget significant)",
        "assay": "sc-crnispri",
        "context": "cd4-tcell",
        "quality_filter": (
            "n_guides>=2 & !single_guide & ontarget_significant & "
            "!distal_offtarget & !low_target_gex"
        ),
        "layers_present": layer_keys,
        "dataset_url": CD4_URL,
        "sha256": CD4_SHA256,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return _emit(out, panel_genes, targets, covered, lfc, se, p, z, n_voting, kd_eff, manifest)


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(24576, 24576),
    timeout=14400,
    volumes={"/kytos-vol": volume},
)
def extract_h1(run_id: str) -> dict:
    """2025 VCC H1 -> L0 via per-batch (or pseudo-batch) Welch-t."""
    import sys

    import anndata as ad
    import numpy as np
    import pandas as pd

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd

    out = OUT_DIR / "h1" / run_id
    if (out / "stats.npz").exists():
        return {"status": "exists", "out": str(out)}

    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    n_genes = len(panel_genes)
    adata = ad.read_h5ad(H1_PATH, backed="r")
    try:
        obs = adata.obs
        var_names = adata.var_names.astype(str).to_numpy()
        obs_cols = list(obs.columns)
        batch_col = next(
            (
                c
                for c in ("gem_group", "batch", "replicate", "sample", "lane", "lane_id", "well")
                if c in obs_cols
            ),
            None,
        )
        pert_col = next(
            (
                c
                for c in (
                    "perturbation",
                    "gene",
                    "target",
                    "guide_target",
                    "target_gene",
                    "condition",
                )
                if c in obs_cols
            ),
            None,
        )
        if pert_col is None:
            raise ValueError(f"no perturbation column in obs: {obs_cols}")
        pert = obs[pert_col].astype(str).to_numpy()
        if batch_col is not None:
            batches = obs[batch_col].astype("category").cat.codes.to_numpy()
            se_kind = f"welch-per-{batch_col}"
        else:
            names = adata.obs_names.astype(str).to_numpy()
            batches = (pd.util.hash_array(names.to_numpy()) % 8).astype(np.int64)
            se_kind = "welch-pseudobatch8 (PSEUDOREP -- L1 downweight)"
        n_batches = int(batches.max()) + 1
        ntc_mask = np.array(
            [("non-target" in t.lower()) or t.lower() in {"control", "ntc"} for t in pert]
        )
        targets = sorted(
            t
            for t in pd.unique(pert)
            if not (("non-target" in t.lower()) or t.lower() in {"control", "ntc"})
        )
        t_pos = {t: i for i, t in enumerate(targets)}
        positions, _missing = cd.map_gene_axis(list(var_names), panel_genes)
        keep_mask = positions >= 0
        pos_keep = positions[keep_mask]
        n_targets = len(targets)
        k_kept = int(keep_mask.sum())

        X = adata.X
        sums = np.zeros((n_targets + 1, n_batches, k_kept))
        cnts = np.zeros((n_targets + 1, n_batches), dtype=np.int64)
        bucket = np.full(len(pert), -1, dtype=np.int64)
        bucket[ntc_mask] = n_targets
        for t, i in t_pos.items():
            bucket[pert == t] = i
        # accumulate in row chunks (X may be csr or dense h5)
        flat = sums.reshape((n_targets + 1) * n_batches, k_kept)
        for r0 in range(0, X.shape[0], ROW_CHUNK):
            r1 = min(r0 + ROW_CHUNK, X.shape[0])
            block = X[r0:r1][:, pos_keep]
            if hasattr(block, "toarray"):
                block = block.toarray()
            block = np.log1p(np.clip(np.asarray(block), 0, None))
            b_c = bucket[r0:r1]
            g_c = batches[r0:r1]
            keep_c = b_c >= 0
            np.add.at(flat, b_c[keep_c] * n_batches + g_c[keep_c], block[keep_c])
            np.add.at(cnts, (b_c[keep_c], g_c[keep_c]), 1)
    finally:
        adata.file.close()

    mean_full, se, p, z, n_full, covered = _group_delta_welch(
        sums, cnts, sums[n_targets], cnts[n_targets], n_targets, n_genes, keep_mask
    )
    # ntc slices passed separately; sums includes ntc row so subtract is
    # handled inside _group_delta_welch via ntc arrays
    lfc = mean_full
    kd_eff = _kd_eff_from_self(targets, panel_genes, lfc)
    manifest = {
        "dataset_id": "vcc2025-h1",
        "run_id": run_id,
        "lfc_kind": "log1p-sc",
        "se_kind": se_kind,
        "estimation": (
            "per-batch group-mean deltas vs same-batch NTC controls; "
            "one-sample Welch t over batches"
        ),
        "sample_unit": batch_col or "pseudobatch-by-barcode-hash (8)",
        "assay": "sc-crnispri",
        "context": "h1-hesc",
        "n_batches": int(n_batches),
        "obs_columns": obs_cols,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return _emit(out, panel_genes, targets, covered, lfc, se, p, z, n_full, kd_eff, manifest)


@app.local_entrypoint()
def main(source: str = "hct116", run_id: str = "", wait: bool = False) -> None:
    _check_source(source)
    rid = run_id or time.strftime("l0-%Y%m%d-01", time.gmtime())
    fn, args = {
        "hct116": (extract_xatlas, (source, rid)),
        "hek293t": (extract_xatlas, (source, rid)),
        "k562": (extract_k562, (rid,)),
        "cd4": (extract_cd4, (rid,)),
        "h1": (extract_h1, (rid,)),
    }[source]
    if wait:
        print(json.dumps(fn.remote(*args), indent=2))
        return
    # spawn detaches the remote work from this client entirely -- the job
    # survives local network drops; poll volume + app logs for completion
    call = fn.spawn(*args)
    print(json.dumps({"spawned": call.object_id, "run_id": rid, "source": source}))
