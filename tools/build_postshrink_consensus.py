"""Build post-shrinkage additive-source consensus variant NPZs (k030).

Motivation: ``cons_eb2_j`` showed that putting Jurkat (near-orthogonal to
K562, cosine ~0.003) INSIDE the eb2 agreement computation destroys its
signal -- cross-source variance reads it as disagreement and shrinks it.
But ``cons_mean_j`` showed the Jurkat delta carries real signal
(pds_cosine +0.041 as a plain mean component).

This builder computes the champion eb2 consensus on the ORIGINAL source
set only (shrinkage unchanged, identical to ``cons_eb2_ref``), then adds
the orthogonal source's unit delta post-shrinkage at fixed weight alpha:

    dir[i] = (1 - a) * lam_i * mu4_i + a * unit(post_delta_i)
    out[i] = dir[i] * k562_norm_i           (targets covered by post-src)
    out[i] = lam_i * mu4_i * k562_norm_i    (otherwise)

``*_ctr`` subtracts the per-gene median across targets.

Run:
  python tools/build_postshrink_consensus.py --src-dir <4-src dir> \
      --post-src deltas_jurkat_stim.npz --alphas 0.2,0.4 --out-dir <dir>
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


def build_postshrink_variants(sources, post, alpha, gamma=2.0):
    """sources: {name: load_source_npz dict} (agreement set).
    post: load_source_npz dict for the post-shrinkage additive source.
    Returns {variant: deltas[T,G]}."""
    ref = next(iter(sources.values()))
    genes, targets = ref["genes"], ref["targets"]
    for name, s in list(sources.items()) + [("post", post)]:
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
    norms = np.linalg.norm(raw, axis=2, keepdims=True)
    unit = np.where(norms > 0, raw / np.where(norms == 0, 1.0, norms), 0.0)

    post_raw = post["delta"].astype(np.float64)
    post_norm = np.linalg.norm(post_raw, axis=1, keepdims=True)
    post_unit = np.where(post_norm > 0, post_raw / np.where(post_norm == 0, 1.0, post_norm), 0.0)
    post_cov = post["covered"] if post["covered"] is not None else np.ones(len(targets), bool)

    out = np.zeros((len(targets), len(genes)), dtype=np.float64)
    for i in range(len(targets)):
        mask = covered[:, i]
        if not mask.any():
            continue
        stack = unit[mask, i]  # (s,G) agreement sources
        mu = stack.mean(0)
        lam = np.ones(stack.shape[1])
        if stack.shape[0] >= 2:
            var = stack.var(0, ddof=0)
            snr = (mu * mu) / (var + 1e-12)
            sg = snr**gamma
            lam = sg / (sg + 1.0)
        base = lam * mu
        if post_cov[i]:
            base = (1.0 - alpha) * base + alpha * post_unit[i]
        norm = k562_norm[i] if k562_norm[i] > 0 else median_norm
        out[i] = base * norm

    a_tag = f"{alpha:g}".replace(".", "p")
    variants = {
        f"cons_eb2post_j{a_tag}": out.astype(np.float32),
        f"cons_eb2post_j{a_tag}_ctr": cd.center_common_response(out).astype(np.float32),
    }
    return variants


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--src-dir", type=Path, required=True)
    p.add_argument("--post-src", type=Path, required=True)
    p.add_argument("--alphas", type=str, default="0.2")
    p.add_argument("--gamma", type=float, default=2.0)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args(argv)

    sources = {}
    for path in sorted(args.src_dir.glob("deltas_*.npz")):
        sources[path.stem.removeprefix("deltas_")] = load_source_npz(path)
    if "k562" not in sources:
        raise ValueError("deltas_k562.npz is required as the reference source")
    post = load_source_npz(args.post_src)

    args.out_dir.mkdir(parents=True, exist_ok=False)
    all_variants = {}
    for a in [float(x) for x in args.alphas.split(",") if x.strip()]:
        all_variants.update(build_postshrink_variants(sources, post, a, args.gamma))
    ref = sources["k562"]
    for name, matrix in all_variants.items():
        np.savez_compressed(
            args.out_dir / f"variant_{name}.npz",
            genes=np.asarray(ref["genes"]),
            targets=np.asarray(ref["targets"]),
            deltas=matrix,
        )
    manifest = {
        "agreement_sources": {
            n: {
                "targets": (
                    int(np.sum(s["covered"])) if s["covered"] is not None else len(s["targets"])
                ),
            }
            for n, s in sources.items()
        },
        "post_source": str(args.post_src),
        "alphas": [float(x) for x in args.alphas.split(",") if x.strip()],
        "gamma": args.gamma,
        "variants": sorted(all_variants),
        "semantics": [
            "eb2 agreement shrinkage computed on src-dir sources ONLY",
            "post source added post-shrinkage: dir = (1-a)*lam*mu + a*unit(post)",
            "amplitude restored to the target's K562 delta norm",
            "*_ctr subtracts the per-gene median across targets",
        ],
    }
    (args.out_dir / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"variants": sorted(all_variants), "out": str(args.out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
