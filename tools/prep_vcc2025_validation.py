"""Prepare VCC 2025 validation data for a Kytos run (run in .venv-science).

Reads the Arc public validation h5ad (raw counts), applies the standard
norm-log transform (normalize_total 1e4 + log1p), and writes:

  real_lognorm.h5ad    — full validation set, lognorm (cell-eval -ar)
  basal_lognorm.h5ad   — non-targeting cells only, lognorm (harness --basal)
  targets.txt          — perturbation targets (harness --targets)
  gene_order.txt       — var axis gene names (harness --gene-order)
  prep_manifest.json   — sha256 of every output + source hash prefix

Artifacts stay under gitignored data/raw — only their hashes are committed
to the run's meta.json (docs/release-infrastructure.md).

Disk discipline (docs/k002-retro.md §k003): pass --purge-source to delete the
6.9GB source once every output is written and verified. The source identity
is pinned in the manifest before deletion — the delete is rejected if the
on-disk source does not match the recorded hash prefix.

Usage:
    .venv-science/bin/python tools/prep_vcc2025_validation.py
    .venv-science/bin/python tools/prep_vcc2025_validation.py --purge-source \
        --expect-source-sha256 376f0bab27d9f22e
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = REPO_ROOT / "data" / "raw" / "vcc2025" / "adata_Validation.h5ad"

CONTROL_LABEL = "non-targeting"
PERT_COL = "target_gene"
DOWNLOAD_URL = (
    "https://storage.googleapis.com/arc-institute-virtual-cell-atlas/"
    "virtual-cell-challenge/2025/validation/adata_Validation.h5ad"
)


def sha256_of(path: Path, prefix: int | None = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    digest = h.hexdigest()
    return digest[:prefix] if prefix else digest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="raw counts h5ad")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="output dir (default: same dir as --src)",
    )
    ap.add_argument(
        "--purge-source",
        action="store_true",
        help="delete --src after outputs are written (frees ~6.9GB)",
    )
    ap.add_argument(
        "--expect-source-sha256",
        default=None,
        help="sha256 (or prefix) the source must match before --purge-source deletes it",
    )
    args = ap.parse_args(argv)

    src: Path = args.src
    out_dir: Path = args.out_dir or src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if not src.is_file():
        print(f"missing {src} — download from the public bucket first:", file=sys.stderr)
        print(f"  {DOWNLOAD_URL}", file=sys.stderr)
        return 1

    if args.purge_source and not args.expect_source_sha256:
        print(
            "refusing --purge-source without --expect-source-sha256: "
            "identify the exact file being deleted",
            file=sys.stderr,
        )
        return 2

    print("[prep] hashing source …", flush=True)
    src_full = sha256_of(src)
    print(f"[prep] source sha256 {src_full[:12]}…", flush=True)

    import anndata as ad
    import scanpy as sc

    print(f"[prep] loading {src} …", flush=True)
    adata = ad.read_h5ad(str(src))
    print(f"[prep] loaded {adata.shape[0]} cells × {adata.shape[1]} genes", flush=True)

    # VCC 2025 ships raw counts (verified: integer-valued CSR). cell-eval
    # expects norm-logged inputs unless --allow-discrete; normalize.
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    print("[prep] normalized (total 1e4) + log1p", flush=True)

    outputs: list[Path] = []

    real_out = out_dir / "real_lognorm.h5ad"
    adata.write_h5ad(str(real_out), compression="gzip")
    outputs.append(real_out)
    print(f"[prep] wrote {real_out}", flush=True)

    control = adata[adata.obs[PERT_COL] == CONTROL_LABEL].copy()
    basal_out = out_dir / "basal_lognorm.h5ad"
    control.write_h5ad(str(basal_out), compression="gzip")
    outputs.append(basal_out)
    print(f"[prep] wrote {basal_out} ({control.shape[0]} control cells)", flush=True)

    targets = sorted({str(t) for t in adata.obs[PERT_COL].unique()} - {CONTROL_LABEL})
    targets_path = out_dir / "targets.txt"
    targets_path.write_text("\n".join(targets) + "\n")
    outputs.append(targets_path)
    print(f"[prep] wrote targets.txt ({len(targets)} perturbations)", flush=True)

    gene_path = out_dir / "gene_order.txt"
    gene_path.write_text("\n".join(map(str, adata.var.index)) + "\n")
    outputs.append(gene_path)
    print(f"[prep] wrote gene_order.txt ({adata.shape[1]} genes)", flush=True)

    # Manifest first: every consumer of these files (or the purge guard below)
    # hashes against this record.
    manifest = {
        "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {"path": str(src), "sha256": src_full},
        "outputs": {p.name: {"sha256": sha256_of(p), "bytes": p.stat().st_size} for p in outputs},
    }
    manifest_path = out_dir / "prep_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[prep] wrote {manifest_path}", flush=True)

    if args.purge_source:
        expect = args.expect_source_sha256
        if not src_full.startswith(expect):
            print(
                f"refusing to purge: source sha256 {src_full[:12]}… does not "
                f"match --expect-source-sha256 {expect}",
                file=sys.stderr,
            )
            return 3
        src.unlink()
        print(f"[prep] purged {src} (hash matched; restore: {DOWNLOAD_URL})", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
