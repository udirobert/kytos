"""Subset a source-delta NPZ to a requested target list (k034).

The genome-wide extracts under ``/kytos-vol/k034-final-prep/`` carry every
target in each source. When the Oct-22 final panel drops, subsetting rows
to the new ``pert_counts.csv`` avoids re-scanning the raw corpora: the
output keeps the ``deltas_<source>.npz`` schema so
``tools/build_consensus_deltas.py --src-dir`` consumes it unchanged.

Rows for requested targets absent from the source are emitted as zeros
with ``covered=False`` -- same convention as the extractors, so downstream
fallback logic sees them as uncovered.

Usage (local or inside a Modal function -- files are small, ~1-2 GB):

  python tools/subset_deltas_npz.py \
      --in deltas_hct116.npz --targets-file pert_counts.csv \
      --out deltas_hct116.npz --out-dir <src-dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def read_targets_file(path: Path) -> list[str]:
    targets = []
    for line in path.read_text().splitlines():
        sym = line.split(",")[0].strip()
        if sym and sym != "target_gene":
            targets.append(sym)
    if len(set(targets)) != len(targets):
        raise ValueError(f"{path}: duplicate target symbols")
    return targets


def subset(in_path: Path, targets: list[str], out_path: Path) -> dict:
    with np.load(in_path, allow_pickle=False) as d:
        genes = d["genes"].astype(str)
        src_targets = d["targets"].astype(str).tolist()
        delta = d["delta"]
        covered_src = (
            d["covered"].astype(bool) if "covered" in d.files else np.ones(len(src_targets), bool)
        )
        n_cells = (
            d["n_cells"].astype(np.int64)
            if "n_cells" in d.files
            else np.zeros(len(src_targets), np.int64)
        )
        extras = {
            k: d[k] for k in d.files if k not in {"genes", "targets", "delta", "covered", "n_cells"}
        }
    pos = {t: i for i, t in enumerate(src_targets)}
    out_delta = np.zeros((len(targets), len(genes)), dtype=np.float32)
    out_cov = np.zeros(len(targets), dtype=bool)
    out_ncells = np.zeros(len(targets), dtype=np.int64)
    n_hit = 0
    sel = []
    for i, t in enumerate(targets):
        j = pos.get(t)
        if j is None:
            continue
        sel.append((i, j))
        n_hit += 1
        if covered_src[j]:
            out_delta[i] = delta[j]
            out_cov[i] = True
            out_ncells[i] = n_cells[j]
    # Subset any other per-target arrays (n_samples, n_quality_rows,
    # delta_batch); drop non-per-target extras.
    out_extras = {}
    for k, v in extras.items():
        v = np.asarray(v)
        if v.ndim >= 1 and v.shape[0] == len(src_targets):
            sub = np.zeros((len(targets),) + v.shape[1:], dtype=v.dtype)
            for i, j in sel:
                sub[i] = v[j]
            out_extras[k] = sub
    np.savez_compressed(
        str(out_path),
        genes=np.asarray(genes),
        targets=np.asarray(targets),
        delta=out_delta,
        covered=out_cov,
        n_cells=out_ncells,
        **out_extras,
    )
    return {
        "in": str(in_path),
        "out": str(out_path),
        "requested": len(targets),
        "present_in_source": n_hit,
        "covered": int(out_cov.sum()),
        "genes": len(genes),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--in", dest="in_paths", type=Path, nargs="+", required=True)
    p.add_argument("--targets-file", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args(argv)

    targets = read_targets_file(args.targets_file)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = [subset(inp, targets, args.out_dir / inp.name) for inp in args.in_paths]
    (args.out_dir / "subset_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
