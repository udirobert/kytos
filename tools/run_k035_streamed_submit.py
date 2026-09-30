"""Kytos k035 — memory-lean streamed dual-moment submission builder.

Drop-in replacement for run_k027_dual_moment_submit.py for hosts that cannot
hold the full prediction matrix. The k027 tool vstacks three context CSR
blocks (~2.43B nnz combined for the 300-target panel — past the int32 limit,
so scipy promotes indices/indptr to int64; X alone is ~29 GB) plus an
in-place astype copy, which OOM-killed the 31 GB VPS during the final write.

Here X is written incrementally to HDF5 instead: each per-target
(cells_per_pert x n_genes) count block is appended to resizable chunked
datasets in prediction.h5ad as soon as it is generated, so the assembled
matrix is never materialized in memory. Peak RSS is dominated by one
context's control CSR (~1.3 GB) plus per-target temporaries (<1 GB).

Output contract is identical to run_k027_dual_moment_submit.py:
  - X: csr_matrix (n_targets*cells_per_pert*len(contexts), n_genes),
    row order = context-major then target order then cells_per_pert rows;
  - obs: target_gene (categorical), context (categorical), str RangeIndex;
  - var: gene_name index;
  - meta.json: same schema (mode string notes the streamed writer).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

RUN_ID = "k035-streamed-dm"


def _read_csr_x(h5ad_path: Path):
    """Load only the /X csr_matrix of an h5ad (skips obs/var)."""
    import h5py
    import numpy as np
    from scipy import sparse

    with h5py.File(str(h5ad_path)) as f:
        g = f["X"]
        shape = tuple(int(s) for s in g.attrs["shape"])
        data = np.asarray(g["data"])
        indices = np.asarray(g["indices"])
        indptr = np.asarray(g["indptr"])
    return sparse.csr_matrix((data, indices, indptr), shape=shape)


class _CsrStream:
    """Append-only csr_matrix writer into an h5ad-style X group.

    Creates group ``X`` with the anndata csr_matrix encoding and resizable
    chunked ``data``/``indices``/``indptr`` datasets; each ``append`` writes
    one CSR block whose rows extend the matrix. indptr is stored int64
    (combined nnz exceeds int32); indices stays int32 (column ids < n_genes).
    """

    def __init__(self, h5_group, n_cols: int):
        import numpy as np

        self._np = np
        g = h5_group
        g.attrs["encoding-type"] = "csr_matrix"
        g.attrs["encoding-version"] = "0.1.0"
        g.attrs["shape"] = np.array([0, n_cols], dtype=np.int64)
        self._data = g.create_dataset(
            "data",
            shape=(0,),
            maxshape=(None,),
            dtype="int32",
            chunks=(1 << 20,),
            compression="gzip",
        )
        self._indices = g.create_dataset(
            "indices",
            shape=(0,),
            maxshape=(None,),
            dtype="int32",
            chunks=(1 << 20,),
            compression="gzip",
        )
        self._indptr = g.create_dataset(
            "indptr",
            shape=(1,),
            maxshape=(None,),
            dtype="int64",
            chunks=(1 << 16,),
            compression="gzip",
        )
        self._indptr[0] = 0
        self._g = g
        self._n_rows = 0
        self._n_cols = n_cols
        self._nnz = 0

    @property
    def nnz(self) -> int:
        return self._nnz

    @property
    def n_rows(self) -> int:
        return self._n_rows

    def append(self, blk) -> None:
        np = self._np
        blk = blk.tocsr()
        if blk.shape[1] != self._n_cols:
            raise ValueError("block column count does not match stream")
        nnz0 = self._nnz
        data = np.asarray(blk.data, dtype=np.int32)
        indices = np.asarray(blk.indices, dtype=np.int32)
        indptr = np.asarray(blk.indptr, dtype=np.int64) + nnz0

        self._data.resize(nnz0 + blk.nnz, axis=0)
        self._data[nnz0:] = data
        self._indices.resize(nnz0 + blk.nnz, axis=0)
        self._indices[nnz0:] = indices
        p0 = self._indptr.shape[0]
        self._indptr.resize(p0 + blk.shape[0], axis=0)
        self._indptr[p0:] = indptr[1:]

        self._n_rows += blk.shape[0]
        self._nnz += blk.nnz
        self._g.attrs["shape"] = np.array([self._n_rows, self._n_cols], dtype=np.int64)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=REPO / "data" / "raw" / "vcc2026")
    ap.add_argument("--deltas-npz", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=REPO / "experiments" / RUN_ID)
    ap.add_argument("--contexts", default="A,B,C")
    ap.add_argument("--cells-per-pert", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-targets", type=int, default=0)
    ap.add_argument("--amplitude", type=float, default=1.0)
    ap.add_argument("--bulk-amplitude", type=float, default=0.5)
    ap.add_argument("--pool-k", type=int, default=4)
    ap.add_argument("--run-id", default=RUN_ID)
    args = ap.parse_args(argv)

    import gc
    import hashlib
    import json
    import time

    import h5py
    import numpy as np
    import pandas as pd
    from anndata.io import write_elem
    from scipy import sparse

    from kytos.models.dual_moment import (
        desired_mean_from_effects,
        dual_moment_counts,
    )
    from run_k005_atlas_prior import CONTEXT_COL, PERT_COL

    raw_dir: Path = args.raw_dir
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_order = pd.read_csv(raw_dir / "gene_names.csv", header=None, skiprows=1)[0].tolist()
    all_targets = pd.read_csv(raw_dir / "pert_counts.csv", header=None, skiprows=1)[0].tolist()
    targets = all_targets[: args.max_targets] if args.max_targets else all_targets
    contexts = [c.strip() for c in args.contexts.split(",") if c.strip()]

    if not args.deltas_npz.exists():
        print(f"missing deltas npz {args.deltas_npz}", file=sys.stderr)
        return 2

    npz_bytes = args.deltas_npz.read_bytes()
    npz_sha = hashlib.sha256(npz_bytes).hexdigest()
    with np.load(args.deltas_npz, allow_pickle=False) as data:
        src_genes = [str(g) for g in data["genes"]]
        src_targets = [str(t) for t in data["targets"]]
        mat = data["deltas"].astype(np.float32)
    if src_genes != [str(g) for g in gene_order]:
        print("npz gene axis does not match gene_names.csv order", file=sys.stderr)
        return 5
    real_deltas = {t: mat[i] for i, t in enumerate(src_targets)}
    uncovered = [t for t in targets if t not in real_deltas]
    print(
        f"[deltas] {args.deltas_npz.name}: {len(real_deltas)} targets x "
        f"{mat.shape[1]} genes, sha256 {npz_sha[:12]}; "
        f"panel uncovered: {len(uncovered)} {uncovered[:10]}",
        flush=True,
    )

    n_genes = len(gene_order)
    cells_per_target = args.cells_per_pert
    pool_k = args.pool_k
    space = "bulk_delta"

    pred_path = out_dir / "prediction.h5ad"
    t0 = time.time()

    ctx_obs: list[pd.DataFrame] = []
    with h5py.File(str(pred_path), "w") as h5:
        h5.attrs["encoding-type"] = "anndata"
        h5.attrs["encoding-version"] = "0.1.0"
        xg = h5.create_group("X")
        stream = _CsrStream(xg, n_genes)

        for ctx in contexts:
            ctrl_path = raw_dir / f"context_{ctx}.h5ad"
            if not ctrl_path.exists():
                print(f"missing {ctrl_path}", file=sys.stderr)
                return 3
            print(f"[{ctx}] loading {ctrl_path.name} ...", flush=True)
            raw = sparse.csr_matrix(_read_csr_x(ctrl_path), dtype=np.float64)
            library = np.asarray(raw.sum(axis=1)).ravel()
            if (library <= 0).any():
                print(f"[{ctx}] control has zero-depth cells", file=sys.stderr)
                return 4
            if len(library) < cells_per_target * pool_k:
                print(f"[{ctx}] not enough control cells for pooling", file=sys.stderr)
                return 4

            # Control mean CPM and bulk probability (identical math to
            # build_prediction_dual_moment).
            mean_cpm = np.zeros(n_genes)
            for left in range(0, len(library), 256):
                block = raw[left : left + 256].toarray() / library[left : left + 256, None]
                mean_cpm += block.sum(axis=0)
            mean_cpm /= len(library)
            bulk_prob = np.asarray(raw.sum(axis=0)).ravel()
            bulk_prob /= bulk_prob.sum()

            for ti, target in enumerate(targets):
                delta = real_deltas.get(target)
                if delta is None:
                    delta = np.zeros(n_genes, dtype=np.float32)

                rng = np.random.default_rng(args.seed + ti)
                selected = rng.choice(len(library), cells_per_target * pool_k, replace=False)
                selected = selected[np.argsort(library[selected], kind="stable")]
                template = raw[selected].toarray() / library[selected, None]
                template = template.reshape(cells_per_target, pool_k, n_genes).mean(axis=1)
                depths = np.rint(
                    library[selected].reshape(cells_per_target, pool_k).mean(axis=1)
                ).astype(np.int64)
                depths = np.clip(depths, 1, 1_000_000)

                prob_cell = desired_mean_from_effects(
                    mean_cpm, delta, space=space, amplitude=args.amplitude
                )
                prob_bulk = desired_mean_from_effects(
                    bulk_prob, delta, space=space, amplitude=args.bulk_amplitude
                )

                counts = dual_moment_counts(
                    template,
                    prob_cell,
                    prob_bulk,
                    depths=depths,
                    seed=args.seed + ti,
                )
                stream.append(sparse.csr_matrix(counts))
                ctx_obs.append(
                    pd.DataFrame(
                        {
                            PERT_COL: [target] * cells_per_target,
                            CONTEXT_COL: [ctx] * cells_per_target,
                        }
                    )
                )
                del counts, template
                if (ti + 1) % 25 == 0 or ti + 1 == len(targets):
                    print(
                        f"[{ctx}] {ti + 1}/{len(targets)} targets, "
                        f"{stream._n_rows} rows, {stream.nnz / 1e6:.1f}M nnz, "
                        f"{time.time() - t0:.0f}s",
                        flush=True,
                    )

            del raw, library, mean_cpm, bulk_prob
            gc.collect()
            print(
                f"[{ctx}] done; cumulative {stream._n_rows} cells x {n_genes} genes",
                flush=True,
            )

        # obs/var written through anndata's own element writer so the file is
        # byte-schema identical to adata.write_h5ad output.
        obs = pd.concat(ctx_obs, ignore_index=True)
        obs.index = obs.index.astype(str)
        obs[PERT_COL] = obs[PERT_COL].astype("category")
        obs[CONTEXT_COL] = obs[CONTEXT_COL].astype("category")
        var = pd.DataFrame(index=pd.Index(gene_order, name="gene_name"))
        var.index = var.index.astype(str)
        write_elem(h5, "obs", obs)
        write_elem(h5, "var", var)

    total_cells = int(stream._n_rows)
    nnz = int(stream.nnz)

    meta = {
        "run_id": args.run_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "consensus_w_ctr deltas + dual-moment count generation "
        "(streamed HDF5 writer — X appended per-target, never materialized)",
        "evidence": "selected via Gate B gate-20260922-02; metrics "
        "embargoed (experiments/_embargoed/k025-eval2-gate/)",
        "contexts": contexts,
        "n_targets": len(targets),
        "cells_per_pert": args.cells_per_pert,
        "total_cells": total_cells,
        "n_genes": n_genes,
        "nnz": nnz,
        "seed": args.seed,
        "deltas_npz": str(args.deltas_npz),
        "deltas_npz_sha256": npz_sha,
        "generator": {
            "type": "dual_moment",
            "amplitude": args.amplitude,
            "bulk_amplitude": args.bulk_amplitude,
            "pool_k": args.pool_k,
            "space": space,
        },
        "dispatch": {"real": len(targets) * len(contexts) - len(uncovered) * len(contexts)},
        "uncovered_targets": uncovered,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    print(
        f"[done] wrote {pred_path} ({total_cells} x {n_genes}, "
        f"{nnz / 1e6:.1f}M nnz) in {time.time() - t0:.1f}s",
        flush=True,
    )
    print(
        "[note] next: vcc prep -g "
        f"{raw_dir / 'gene_names.csv'} --perts {raw_dir / 'pert_counts.csv'} {pred_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
