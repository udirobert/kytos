"""Shared L0 evidence-store helpers (engine v2).

Pure-python helpers used by the Modal extractors (k201 phase-0 stores,
k202 harvest). No modal imports here -- the jobs mount this file and do
volume commits themselves.

Schema (docs/engine-v2-design.md §1): per-dataset ``stats.npz`` with
(T,G) float32 arrays lfc/se/p/q/z, (T,G) i16 n_voting, (T,) bool covered,
(T,) f32 kd_eff, plus ``manifest.json``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

MIN_SAMPLES = 3  # Welch-t needs >=3 voting samples to emit se/p


def bh_q(p):
    """Benjamini-Hochberg q-values over finite entries of a (G,) p-array."""
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


def welch_from_moments(mean_d, e2_d, n_d, row_chunk=2048, min_samples=MIN_SAMPLES):
    """One-sample t over per-sample deltas -> (se, p, z) float32.

    mean_d/e2_d: (T,G) E[d], E[d^2]. n_d: (T,) or (T,G) sample counts.
    Chunked over targets so peak f64 scratch stays ~row_chunk x G.
    """
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
        ok = n >= min_samples
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


def kd_eff_from_self(targets, genes, lfc):
    """Negative self-gene lfc as KD-efficiency proxy (clip at 0)."""
    gpos = {g: i for i, g in enumerate(genes)}
    eff = np.full(len(targets), np.nan, dtype=np.float64)
    for i, t in enumerate(targets):
        j = gpos.get(str(t))
        if j is not None and np.isfinite(lfc[i, j]):
            eff[i] = max(-float(lfc[i, j]), 0.0)
    return eff


def group_delta_welch(sums, cnts, ntc_sums, ntc_cnts, n_targets, n_genes, keep_cols_mask):
    """Per-(target,sample) group means -> moments -> Welch-t.

    sums: (T+1, S, K) log1p sums over kept panel cols (last bucket = NTC).
    cnts: (T+1, S) cell counts. ntc_*: same shape's NTC slice.
    keep_cols_mask: (n_genes,) bool -- kept cols are scattered into the
    full panel axis.
    """
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
    mean_full = np.full((n_targets, n_genes), np.nan)
    e2_full = np.zeros((n_targets, n_genes))
    n_full = np.zeros((n_targets, n_genes), dtype=np.int16)
    mean_full[:, keep_cols_mask] = mean_d
    e2_full[:, keep_cols_mask] = e2_d
    n_full[:, keep_cols_mask] = n_v
    se, p, z = welch_from_moments(np.where(np.isfinite(mean_full), mean_full, 0.0), e2_full, n_full)
    return mean_full, se, p, z, n_full, covered


def emit_store(out_dir, genes, targets, covered, lfc, se, p, z, n_voting, kd_eff, manifest):
    """Write stats.npz + manifest.json; caller commits the volume."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    q = np.full(p.shape, np.nan, dtype=np.float32)
    for i in range(p.shape[0]):
        q[i] = bh_q(p[i])
    np.savez_compressed(
        str(out_dir / "stats.npz"),
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
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {
        "status": "ok",
        "out": str(out_dir),
        "targets": int(len(targets)),
        "covered": int(np.asarray(covered).sum()),
    }


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- obs/var column detection (shared with extract_scperteval_source.py) ---

CONTROL_LABELS = {
    "control",
    "non-targeting",
    "non_targeting",
    "nontargeting",
    "nt",
    "ctrl",
    "scramble",
    "scrambled",
    "ntc",
}
PERT_COL_CANDIDATES = (
    "perturbation",
    "pert_name",
    "gene",
    "target",
    "gene_target",
    "condition",
    "perturbed_gene",
    "target_gene",
    "knockdown",
)
VAR_COL_CANDIDATES = (
    "gene_name",
    "gene_symbol",
    "symbol",
    "feature_name",
    "gene_id",
    "name",
)
BATCH_COL_CANDIDATES = (
    "gem_group",
    "batch",
    "sample",
    "replicate",
    "donor",
    "lane",
    "lane_id",
    "well",
    "plate",
    "library",
    "prep_batch",
    "batch_id",
)


def pick_pert_column(obs):
    """Return (column_name, control_label) for the perturbation column."""
    for col in PERT_COL_CANDIDATES:
        if col not in obs.columns:
            continue
        vals = obs[col].astype(str).str.lower().unique()
        hit = [v for v in vals if v in CONTROL_LABELS]
        if hit:
            return col, hit[0]
    for col in obs.columns:
        if obs[col].dtype.name not in ("category", "object", "str"):
            continue
        vals = obs[col].astype(str).str.lower().unique()
        if len(vals) > 1e6:
            continue
        hit = [v for v in vals if v in CONTROL_LABELS]
        if hit and len(vals) < len(obs) // 2:
            return col, hit[0]
    raise ValueError(
        f"no perturbation column with a control label; obs columns: {list(obs.columns)[:30]}"
    )


def pick_batch_column(obs, forced=None):
    """Return (column_name, codes) or (None, None).

    forced: explicit column name from the catalog spec. Codes are int64
    categorical codes 0..S-1.
    """
    col = forced if (forced and forced in obs.columns) else None
    col = col or next((c for c in BATCH_COL_CANDIDATES if c in obs.columns), None)
    if col is None:
        return None, None
    return col, obs[col].astype("category").cat.codes.to_numpy()


def pick_gene_axis(adata):
    """Return (symbols, axis_label)."""
    names = [str(v) for v in adata.var_names]
    joined = ",".join(names[:200])
    if joined.count("ENSG") < 50:
        return names, "var_names"
    for col in VAR_COL_CANDIDATES:
        if col in adata.var.columns:
            return [str(v) for v in adata.var[col]], f"var.{col}"
    return names, "var_names(ensembl-unresolved)"
