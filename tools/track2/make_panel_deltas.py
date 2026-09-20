"""Build panel_deltas.npz -- the K562 GWPS deltas for the 300 2026 panel
targets, in gene_names order -- the input to train_gnn_crosslineage.py --predict.

Runs wherever delta_matrix_src.npz lives (Nebius VM /data/derived or Modal
volume /kytos-vol/paired-transfer). Only needs the ~731 MB src matrix.

Usage:
  python tools/track2/make_panel_deltas.py \
      --src-matrix /data/derived/delta_matrix_src.npz \
      --gene-names data/raw/vcc2026/gene_names.csv \
      --pert-counts data/raw/vcc2026/pert_counts.csv \
      --out /data/derived/panel_k562_deltas.npz
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src-matrix", type=Path, required=True)
    ap.add_argument("--gene-names", type=Path, required=True)
    ap.add_argument("--pert-counts", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    gene_names = pd.read_csv(args.gene_names, header=None, skiprows=1)[0].tolist()
    panel = pd.read_csv(args.pert_counts, header=None, skiprows=1)[0].tolist()
    panel = [str(t) for t in panel]

    src = np.load(args.src_matrix, allow_pickle=False)
    stargets = [str(t) for t in src["targets"].tolist()]
    sdeltas = np.asarray(src["deltas"], dtype=np.float32)  # (N, G) in gene_names order

    row_of = {t: i for i, t in enumerate(stargets)}
    rows, covered = [], []
    for t in panel:
        i = row_of.get(t)
        rows.append(i if i is not None else 0)
        covered.append(i is not None)
    deltas = sdeltas[rows]  # (T, G); uncovered rows are 0 + flagged out via covered
    covered = np.asarray(covered, dtype=bool)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        targets=np.array(panel),
        deltas=deltas,
        gene_names=np.array(gene_names),
        covered=covered,
    )
    print(
        f"[panel] {len(panel)} targets, {covered.sum()} K562-covered, "
        f"{(~covered).sum()} uncovered -> neighbour/fallback in builder",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
