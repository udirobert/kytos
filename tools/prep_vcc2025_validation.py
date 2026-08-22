"""Prepare VCC 2025 validation data for a Kytos run (run in .venv-science).

Reads the Arc public validation h5ad (raw counts), applies the standard
norm-log transform (normalize_total 1e4 + log1p), and writes:

  data/raw/vcc2025/real_lognorm.h5ad    — full validation set, lognorm (cell-eval -ar)
  data/raw/vcc2025/basal_lognorm.h5ad   — non-targeting cells only, lognorm (harness --basal)
  data/raw/vcc2025/targets.txt          — 50 perturbation targets (harness --targets)
  data/raw/vcc2025/gene_order.txt       — var axis gene names (harness --gene-order)

Artifacts stay under gitignored data/raw — only their hashes are committed
to the run's meta.json (docs/release-infrastructure.md).

Usage:
    .venv-science/bin/python tools/prep_vcc2025_validation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "data" / "raw" / "vcc2025" / "adata_Validation.h5ad"
OUT_DIR = REPO_ROOT / "data" / "raw" / "vcc2025"

CONTROL_LABEL = "non-targeting"
PERT_COL = "target_gene"


def main() -> int:
    import anndata as ad
    import scanpy as sc

    if not SRC.is_file():
        print(f"missing {SRC} — download from the public bucket first:", file=sys.stderr)
        print(
            "  https://storage.googleapis.com/arc-institute-virtual-cell-atlas/"
            "virtual-cell-challenge/2025/validation/adata_Validation.h5ad",
            file=sys.stderr,
        )
        return 1

    print(f"[prep] loading {SRC} …", flush=True)
    adata = ad.read_h5ad(str(SRC))
    print(f"[prep] loaded {adata.shape[0]} cells × {adata.shape[1]} genes", flush=True)

    # VCC 2025 ships raw counts (verified: integer-valued CSR). cell-eval
    # expects norm-logged inputs unless --allow-discrete; normalize.
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    print("[prep] normalized (total 1e4) + log1p", flush=True)

    real_out = OUT_DIR / "real_lognorm.h5ad"
    adata.write_h5ad(str(real_out), compression="gzip")
    print(f"[prep] wrote {real_out}", flush=True)

    control = adata[adata.obs[PERT_COL] == CONTROL_LABEL].copy()
    basal_out = OUT_DIR / "basal_lognorm.h5ad"
    control.write_h5ad(str(basal_out), compression="gzip")
    print(f"[prep] wrote {basal_out} ({control.shape[0]} control cells)", flush=True)

    targets = sorted({str(t) for t in adata.obs[PERT_COL].unique()} - {CONTROL_LABEL})
    (OUT_DIR / "targets.txt").write_text("\n".join(targets) + "\n")
    print(f"[prep] wrote targets.txt ({len(targets)} perturbations)", flush=True)

    (OUT_DIR / "gene_order.txt").write_text("\n".join(map(str, adata.var.index)) + "\n")
    print(f"[prep] wrote gene_order.txt ({adata.shape[1]} genes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
