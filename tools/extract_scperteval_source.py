"""Extract per-target perturbation deltas from a scPertEval processed h5ad (k039).

Why this job exists
-------------------
Spec: ``docs/k039-new-lineage-sources.md``. The scPertEval processed bucket
serves trimmed single-cell perturbation h5ads (``X`` log-normalized, ``obs``
carrying one perturbation label, ``var`` gene symbols) over plain HTTPS --
including two RPE1 screens, a lineage absent from the current consensus
sources. This tool turns one into the standard ``deltas_<source>.npz``
contract used by ``tools/consensus_deltas.py`` consumers.

Units caveat (recorded in the manifest)
---------------------------------------
scPertEval ``X`` is ``log1p(normalize_total(1e4))``, not raw counts, so the
delta emitted is a *log-normalized-mean difference*, not the
``mean(log1p(raw))`` shift used by the K562/X-Atlas extractors. Consumers
must honor ``manifest["units"]`` before mixing sources (the same caveat the
CD4 log2-FC source already carries). The processed files also lack a
per-sample/batch column -- only pooled deltas are produced.

Runs on snapflip-vultr (essential-gene h5ads are <=6 GB; block-wise backed
reads keep RSS in the low GBs).

Outputs (under ``--out-dir``)
-----------------------------
``deltas_<source>.npz``:
  ``genes``      (18533,) panel axis symbols
  ``targets``    (T,) perturbation labels minus controls
  ``delta``      (T, 18533) float32 pooled log-normalized mean difference
  ``covered``    (T,) bool -- target has >=1 perturbed cell
  ``n_cells``    (T,) int64 perturbed cells
  ``ctrl_mean``  (18533,) float32 control-cell mean on the panel axis
                 (kept for the ctxlineage-style basal-match audit)
``manifest_<source>.json``: units, hashes, coverage vs the 2026 panel.

Run (VPS):
  /opt/kytos/.venv/bin/python tools/extract_scperteval_source.py \
      --h5ad data/raw/scperteval/replogle22rpe1_processed_complete.h5ad \
      --source replogle22rpe1 --out-dir /kytos-vol-or-local/out
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL_GENES = REPO_ROOT / "data/raw/vcc2026/gene_names.csv"
PANEL_COUNTS = REPO_ROOT / "data/raw/vcc2026/pert_counts.csv"

CONTROL_LABELS = {
    "control",
    "non-targeting",
    "non_targeting",
    "nontargeting",
    "nt",
    "ctrl",
    "scramble",
    "scrambled",
}
PERT_COL_CANDIDATES = (
    "perturbation",
    "pert_name",
    "gene",
    "target",
    "gene_target",
    "condition",
    "perturbed_gene",
)
VAR_COL_CANDIDATES = ("gene_name", "gene_symbol", "symbol", "feature_name", "gene_id", "name")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 26), b""):
            h.update(chunk)
    return h.hexdigest()


def _pick_pert_column(obs: pd.DataFrame) -> tuple[str, str]:
    """Return (column_name, control_label)."""
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
        f"no perturbation column with a control label found; obs columns: {list(obs.columns)[:30]}"
    )


def _pick_gene_axis(adata) -> tuple[list[str], str]:
    names = [str(v) for v in adata.var_names]
    joined = ",".join(names[:200])
    if joined.count("ENSG") < 50:
        return names, "var_names"
    for col in VAR_COL_CANDIDATES:
        if col in adata.var.columns:
            return [str(v) for v in adata.var[col]], f"var.{col}"
    return names, "var_names(ensembl-unresolved)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--h5ad", required=True, type=Path)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument(
        "--targets-file",
        type=Path,
        default=None,
        help="optional symbol list; default = every perturbation",
    )
    ap.add_argument("--block", type=int, default=20000)
    ap.add_argument("--hash", action="store_true", help="sha256 the input file")
    args = ap.parse_args()

    import anndata as ad
    from scipy import sparse

    import sys

    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import consensus_deltas as cd

    t0 = time.time()
    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    G = len(panel_genes)
    panel_targets = sorted(pd.read_csv(PANEL_COUNTS).iloc[:, 0].astype(str).unique())

    adata = ad.read_h5ad(args.h5ad, backed="r")
    n_obs, n_src_genes = adata.n_obs, adata.n_vars
    obs = adata.obs
    pert_col, ctrl_label = _pick_pert_column(obs)
    labels = obs[pert_col].astype(str).to_numpy()
    labels_lower = obs[pert_col].astype(str).str.lower().to_numpy()

    src_genes, gene_axis_used = _pick_gene_axis(adata)
    positions, missing_genes = cd.map_gene_axis(src_genes, panel_genes)
    # (source_genes x panel_genes) selector: X_panel = X @ S
    mapped_src = positions[positions >= 0]
    mapped_panel = np.flatnonzero(positions >= 0)
    S = sparse.csr_matrix(
        (np.ones(len(mapped_src)), (mapped_src, mapped_panel)),
        shape=(n_src_genes, G),
    )

    if args.targets_file:
        keep_targets = sorted(
            {
                ln.split(",")[0].strip()
                for ln in args.targets_file.read_text().splitlines()
                if ln.split(",")[0].strip() and ln.split(",")[0].strip() != "target_gene"
            }
        )
    else:
        keep_targets = sorted(set(labels) - {x for x in set(labels) if x.lower() in CONTROL_LABELS})
    t_pos = {t: i for i, t in enumerate(keep_targets)}
    T = len(keep_targets)
    ctrl_bucket = T

    is_ctrl = np.array([x in CONTROL_LABELS for x in labels_lower])
    cell_group = np.full(n_obs, -1, dtype=np.int64)
    lab_pos = np.array([t_pos.get(x, -1) for x in labels], dtype=np.int64)
    cell_group[~is_ctrl & (lab_pos >= 0)] = lab_pos[~is_ctrl & (lab_pos >= 0)]
    cell_group[is_ctrl] = ctrl_bucket
    n_groups = T + 1

    group_sums = np.zeros((n_groups, G), dtype=np.float64)
    group_cells = np.bincount(cell_group[cell_group >= 0], minlength=n_groups)

    X = adata.X
    for lo in range(0, n_obs, args.block):
        hi = min(lo + args.block, n_obs)
        xb = X[lo:hi]
        if not sparse.issparse(xb):
            xb = sparse.csr_matrix(np.asarray(xb))
        else:
            xb = xb.tocsr()
        grp = cell_group[lo:hi]
        keep = grp >= 0
        if not keep.any():
            continue
        gsel = sparse.csr_matrix(
            (np.ones(int(keep.sum())), (np.flatnonzero(keep), grp[keep])),
            shape=(hi - lo, n_groups),
        )
        group_sums += (gsel.T @ (xb @ S)).toarray()
        if (hi // args.block) % 10 == 0:
            print(f"[{args.source}] rows {hi}/{n_obs}", flush=True)

    ctrl_mean = group_sums[ctrl_bucket] / max(int(group_cells[ctrl_bucket]), 1)
    n_cells = group_cells[:T]
    covered = n_cells > 0
    delta = np.zeros((T, G), dtype=np.float32)
    delta[covered] = (group_sums[:T][covered] / n_cells[covered, None] - ctrl_mean[None, :]).astype(
        np.float32
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.out_dir / f"deltas_{args.source}"
    np.savez_compressed(
        str(stem) + ".npz",
        genes=np.asarray(panel_genes),
        targets=np.asarray(keep_targets),
        delta=delta,
        covered=covered,
        n_cells=n_cells,
        ctrl_mean=ctrl_mean.astype(np.float32),
    )

    covered_set = set(np.asarray(keep_targets)[covered].tolist())
    manifest = {
        "source": args.source,
        "h5ad": str(args.h5ad),
        "sha256": _sha256(args.h5ad) if args.hash else None,
        "units": "lognorm_mean_diff (X = log1p(normalize_total(1e4)); "
        "NOT mean(log1p(raw)) -- normalize before mixing sources)",
        "pert_column": pert_col,
        "control_label": ctrl_label,
        "gene_axis": gene_axis_used,
        "n_obs": int(n_obs),
        "n_source_genes": int(n_src_genes),
        "n_targets": T,
        "n_covered": int(covered.sum()),
        "panel_genes_mapped": int((positions >= 0).sum()),
        "panel_genes_missing": len(missing_genes),
        "panel_targets_covered": len(covered_set & set(panel_targets)),
        "panel_targets_total": len(panel_targets),
        "control_cells": int(group_cells[ctrl_bucket]),
        "elapsed_s": round(time.time() - t0, 1),
        "tool": "tools/extract_scperteval_source.py",
    }
    (args.out_dir / f"manifest_{args.source}.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
