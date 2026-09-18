#!/usr/bin/env python3
"""Prepare Kaggle dataset bundle for VCC 2026 controls.

Creates a Kaggle dataset directory with:
  - context_A/B/C.h5ad (sparse, ~632MB total)
  - gene_names.csv, pert_counts.csv, manifest.json
  - dataset-metadata.json for `kaggle datasets create`

Also supports Hugging Face mirror (same files, no metadata).

Usage:
  python tools/kaggle_bundle.py --out /tmp/kaggle-vcc2026-controls
  # then:
  kaggle datasets create -p /tmp/kaggle-vcc2026-controls
  kaggle datasets version -p /tmp/kaggle-vcc2026-controls -m "v1"

GitHub -> HF canonical, Kaggle mirror per docs/release-infrastructure.md §2-3.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RAW = REPO / "data" / "raw" / "vcc2026"


def build_kaggle_dataset(raw_dir: Path, out_dir: Path, username: str | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    needed = [
        "context_A.h5ad",
        "context_B.h5ad",
        "context_C.h5ad",
        "gene_names.csv",
        "pert_counts.csv",
        "manifest.json",
    ]
    for fn in needed:
        src = raw_dir / fn
        if not src.exists():
            raise FileNotFoundError(f"missing {src} — run `vcc datasets download controls` first")
        dst = out_dir / fn
        if dst.exists():
            print(f"skip {fn} (exists)")
        else:
            print(f"copy {fn} ({src.stat().st_size / 1e6:.1f} MB) ...")
            shutil.copy2(src, dst)

    # Kaggle dataset metadata
    dataset_slug = "vcc2026-controls"
    user = username or "YOUR_KAGGLE_USERNAME"
    meta = {
        "title": "Kytos VCC 2026 Controls - 3 contexts x 18k genes",
        "id": f"{user}/{dataset_slug}",
        "licenses": [{"name": "other"}],
        "resources": [{"path": fn, "description": fn} for fn in needed],
        "description": (
            "Arc VCC 2026 validation controls (A/B/C, 18.5k genes, "
            "18.4k cells each). Mirror of data/raw/vcc2026/. See kytos "
            "docs/release-infrastructure.md. Source: vcc datasets download "
            "controls. License: check Arc Atlas/VCC terms before "
            "publishing; gate if competition-only."
        ),
    }
    (out_dir / "dataset-metadata.json").write_text(json.dumps(meta, indent=2))
    print(f"\nwrote {out_dir / 'dataset-metadata.json'}")
    print(f"dataset id: {meta['id']}")
    print("\nNext:")
    print(f"  kaggle datasets create -p {out_dir}")
    print("  # or version bump:")
    print(f"  kaggle datasets version -p {out_dir} -m 'update controls'")
    if user == "YOUR_KAGGLE_USERNAME":
        print(
            "\nEdit dataset-metadata.json -> replace YOUR_KAGGLE_USERNAME "
            "with your Kaggle username first."
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--out", type=Path, default=Path("/tmp/kaggle-vcc2026-controls"))
    ap.add_argument("--username", type=str, default=None, help="Kaggle username for dataset id")
    args = ap.parse_args()
    build_kaggle_dataset(args.raw_dir, args.out, args.username)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
