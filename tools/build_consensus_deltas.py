"""Combine per-lineage source deltas into consensus variant NPZs (k023).

Inputs: ``deltas_<source>.npz`` files produced by
``tools/modal_k023_xatlas_extract.py`` (one per lineage: k562, hct116,
hek293t, cd4). Each carries ``genes`` (panel axis), ``targets``, ``delta``
[T,G], ``covered`` [T] -- and optionally ``delta_batch`` for X-Atlas arms.

Outputs: one ``variant_<name>.npz`` per variant, in the generic audit
schema (``genes``, ``targets``, ``deltas``), plus ``build_manifest.json``.

Consensus semantics (documented choices, all recorded in the manifest):
- each source delta is unit-normalized before mixing, so differing units
  (mean-log1p shift vs publisher log2FC) do not set the scale;
- the weighted mean of unit vectors has norm in [0,1] proportional to
  directional agreement -- disagreement shrinks amplitude, which is the
  intended conservative behavior;
- consensus amplitude is restored by multiplying by the target's own
  K562 delta L2 norm (fallback: median K562 norm) so ``delta_scale=1.7``
  stays calibrated to the champion's units;
- ``*_ctr`` variants subtract the per-gene median across targets
  (common-response centering).

Run:
  python tools/build_consensus_deltas.py --src-dir <dir> --out-dir <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import consensus_deltas as cd

WEIGHTED = {"k562": 2.0, "hct116": 1.0, "hek293t": 1.0, "cd4": 1.0}
NCELL_FULL_WEIGHT = 100.0


def load_source_npz(path):
    with np.load(path, allow_pickle=False) as d:
        out = {
            "genes": d["genes"].astype(str).tolist(),
            "targets": d["targets"].astype(str).tolist(),
            "delta": d["delta"],
            "covered": d["covered"].astype(bool) if "covered" in d.files else None,
        }
        if "delta_batch" in d.files:
            out["delta_batch"] = d["delta_batch"]
        if "n_cells" in d.files:
            out["n_cells"] = d["n_cells"]
    if out["delta"].shape != (len(out["targets"]), len(out["genes"])):
        raise ValueError(f"{path}: delta shape mismatch")
    return out


def build_variants(sources):
    """sources: {name: load_source_npz dict}. Returns {variant: deltas[T,G]}."""
    ref = next(iter(sources.values()))
    genes, targets = ref["genes"], ref["targets"]
    tpos = {t: i for i, t in enumerate(targets)}
    for name, s in sources.items():
        if s["genes"] != genes or s["targets"] != targets:
            raise ValueError(f"{name}: axis or target order differs from reference")

    variants = {}
    per_target = {}
    for name, s in sources.items():
        covered = s["covered"] if s["covered"] is not None else np.ones(len(targets), bool)
        variants[name] = np.where(covered[:, None], s["delta"], 0.0).astype(np.float32)
        if "delta_batch" in s:
            variants[f"{name}_batch"] = np.where(covered[:, None], s["delta_batch"], 0.0).astype(
                np.float32
            )
        per_target[name] = {
            tpos[t]: s["delta"][tpos[t]] if covered[tpos[t]] else None for t in targets
        }

    k562_norm = np.linalg.norm(sources["k562"]["delta"], axis=1)
    median_norm = float(np.median(k562_norm[k562_norm > 0])) if (k562_norm > 0).any() else 1.0

    def consensus_matrix(weights, ncell_weight=False):
        matrix = np.zeros((len(targets), len(genes)), dtype=np.float64)
        for i, t in enumerate(targets):
            src = {n: per_target[n][i] for n in sources}
            w = weights
            if ncell_weight:
                # Down-weight sources with few perturbed cells: delta noise
                # scales ~1/sqrt(n), so a 2-cell arm should not vote equally.
                # Sources without n_cells metadata keep their base weight.
                base = weights or {}
                w = {}
                for n in sources:
                    b = float(base.get(n, 1.0))
                    nc = sources[n].get("n_cells")
                    w[n] = b * min(1.0, float(nc[i]) / NCELL_FULL_WEIGHT) if nc is not None else b
            cons, _ = cd.consensus_delta(src, w)
            if cons is None:
                continue
            norm = k562_norm[i] if k562_norm[i] > 0 else median_norm
            matrix[i] = cons * norm
        return matrix

    mean = consensus_matrix(None)
    variants["consensus_mean"] = mean.astype(np.float32)
    variants["consensus_mean_ctr"] = cd.center_common_response(mean).astype(np.float32)
    weighted = consensus_matrix(WEIGHTED)
    variants["consensus_w"] = weighted.astype(np.float32)
    variants["consensus_w_ctr"] = cd.center_common_response(weighted).astype(np.float32)
    ncell = consensus_matrix(WEIGHTED, ncell_weight=True)
    variants["consensus_w_ncell"] = ncell.astype(np.float32)
    variants["consensus_w_ncell_ctr"] = cd.center_common_response(ncell).astype(np.float32)
    return variants


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--src-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args(argv)

    sources = {}
    for path in sorted(args.src_dir.glob("deltas_*.npz")):
        sources[path.stem.removeprefix("deltas_")] = load_source_npz(path)
    if "k562" not in sources:
        raise ValueError("deltas_k562.npz is required as the reference source")

    args.out_dir.mkdir(parents=True, exist_ok=False)
    variants = build_variants(sources)
    ref = sources["k562"]
    for name, matrix in variants.items():
        np.savez_compressed(
            args.out_dir / f"variant_{name}.npz",
            genes=np.asarray(ref["genes"]),
            targets=np.asarray(ref["targets"]),
            deltas=matrix,
        )
    manifest = {
        "sources": {
            n: {
                "targets": (
                    int(np.sum(s["covered"])) if s["covered"] is not None else len(s["targets"])
                ),
                "has_batch_delta": "delta_batch" in s,
            }
            for n, s in sources.items()
        },
        "variants": sorted(variants),
        "weights": WEIGHTED,
        "ncell_full_weight": NCELL_FULL_WEIGHT,
        "semantics": [
            "source deltas unit-normalized before mixing",
            "consensus norm scales with cross-source directional agreement",
            "amplitude restored to the target's K562 delta norm",
            "*_ctr subtracts the per-gene median across targets",
            "*_ncell down-weights a source by min(1, n_cells/100) per target",
        ],
    }
    (args.out_dir / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"variants": sorted(variants), "out": str(args.out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
