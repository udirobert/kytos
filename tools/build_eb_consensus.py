"""Build an agreement-shrunk consensus variant NPZ (k029 candidate).

Same contract as ``tools/build_consensus_deltas.py``: per source, deltas are
unit-normalized before mixing; the combined direction is rescaled to the
target's own K562 delta norm; ``*_ctr`` subtracts the per-gene median
across targets.

The ``consensus_eb`` variant adds per-gene reliability shrinkage on top of
the (unweighted) mean of unit-normalized source deltas:

    lam[g] = snr[g] / (snr[g] + 1),   snr[g] = mu[g]^2 / var[g]

where ``var`` is the cross-source variance of the unit-normalized deltas.
Genes where lineages disagree are shrunk harder than uniform averaging;
replicated genes pass through. Sources missing a target are skipped for
that target (variance over present sources; needs >=2 to shrink).

Run:
  python tools/build_eb_consensus.py --src-dir <dir> --out-dir <dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import consensus_deltas as cd
from build_consensus_deltas import load_source_npz


def build_eb_variants(sources, gamma=1.0):
    """sources: {name: load_source_npz dict}. Returns {variant: deltas[T,G]}."""
    ref = next(iter(sources.values()))
    genes, targets = ref["genes"], ref["targets"]
    for name, s in sources.items():
        if s["genes"] != genes or s["targets"] != targets:
            raise ValueError(f"{name}: axis or target order differs from reference")

    k562_norm = np.linalg.norm(sources["k562"]["delta"], axis=1)
    median_norm = float(np.median(k562_norm[k562_norm > 0])) if (k562_norm > 0).any() else 1.0

    order = sorted(sources)
    covered = np.stack(
        [
            s["covered"] if s["covered"] is not None else np.ones(len(targets), bool)
            for s in (sources[o] for o in order)
        ]
    )  # (S, T)
    raw = np.stack([sources[o]["delta"].astype(np.float64) for o in order])  # (S,T,G)

    # unit-normalize each source delta row
    norms = np.linalg.norm(raw, axis=2, keepdims=True)
    unit = np.where(norms > 0, raw / np.where(norms == 0, 1.0, norms), 0.0)

    eb = np.zeros((len(targets), len(genes)), dtype=np.float64)
    for i in range(len(targets)):
        mask = covered[:, i]
        if not mask.any():
            continue
        stack = unit[mask, i]  # (s,G) over present sources
        mu = stack.mean(0)
        if stack.shape[0] >= 2:
            var = stack.var(0, ddof=0)
            snr = (mu * mu) / (var + 1e-12)
            sg = snr**gamma
            mu = mu * (sg / (sg + 1.0))
        norm = k562_norm[i] if k562_norm[i] > 0 else median_norm
        eb[i] = mu * norm

    tag = "eb" if gamma == 1.0 else f"eb{gamma:g}"
    variants = {
        f"consensus_{tag}": eb.astype(np.float32),
        f"consensus_{tag}_ctr": cd.center_common_response(eb).astype(np.float32),
    }
    return variants


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--src-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--gamma", type=float, default=1.0)
    args = p.parse_args(argv)

    sources = {}
    for path in sorted(args.src_dir.glob("deltas_*.npz")):
        sources[path.stem.removeprefix("deltas_")] = load_source_npz(path)
    if "k562" not in sources:
        raise ValueError("deltas_k562.npz is required as the reference source")

    args.out_dir.mkdir(parents=True, exist_ok=False)
    variants = build_eb_variants(sources, gamma=args.gamma)
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
            }
            for n, s in sources.items()
        },
        "variants": sorted(variants),
        "semantics": [
            "source deltas unit-normalized before mixing",
            f"per-gene reliability shrinkage lam = snr^g/(snr^g+1), "
            f"g={args.gamma}, snr = mean^2/var over present sources",
            "amplitude restored to the target's K562 delta norm",
            "*_ctr subtracts the per-gene median across targets",
        ],
    }
    (args.out_dir / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"variants": sorted(variants), "out": str(args.out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
