"""Build context-weighted consensus variant NPZs (k030).

Same contract as ``tools/build_eb_consensus.py``: per source, deltas are
unit-normalized before mixing; the combined direction is rescaled to the
target's own K562 delta norm; ``*_ctr`` subtracts the per-gene median
across targets.

The ``ctxw`` variants replace the static consensus weights with
per-context weights from ``modal_ctxlineage_basal.py``'s
``ctxlineage_report.json`` (basal-similarity-derived, leak-free: computed
only from control-cell expression). For each context ``c`` and weighting
rule (``p1``, ``p2``, ``top``):

    mu_ctx = sum_s w_c[s] * unit(delta_s) / sum_s w_c[s]     (present sources)

Variants emitted per (rule, context):
- ``cons_ctxw{rule}_{ctx}``        -- weighted mean, rescaled to K562 norm
- ``cons_ctxw{rule}_{ctx}_ctr``    -- + common-response centering
- ``cons_ctxw{rule}_{ctx}_eb2``    -- weighted mean shrunk by the eb2
                                    reliability factor computed from the
                                    UNWEIGHTED cross-source moments
                                    (lam = snr^2/(snr^2+1), snr = mu^2/var)
                                    so shrinkage stays identical to the
                                    champion and only the mixing weights
                                    change -- clean attribution.
- ``cons_ctxw{rule}_{ctx}_eb2_ctr``

Sources missing a target are skipped for that target. Contexts are the
report keys (A, B, C, eval); the ``eval`` context is what Gate B tests.

Run:
  python tools/build_ctxw_consensus.py --src-dir <dir> \
      --report <ctxlineage_report.json> --out-dir <dir>
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


def build_ctxw_variants(sources, weights_by_ctx):
    """sources: {name: load_source_npz dict}.
    weights_by_ctx: {ctx: {source: weight}}.
    Returns {variant: deltas[T,G]}."""
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
    norms = np.linalg.norm(raw, axis=2, keepdims=True)
    unit = np.where(norms > 0, raw / np.where(norms == 0, 1.0, norms), 0.0)

    variants = {}
    for ctx, wmap in weights_by_ctx.items():
        w = np.array([float(wmap.get(o, 0.0)) for o in order])  # (S,)
        ctxw = np.zeros((len(targets), len(genes)), dtype=np.float64)
        ctxw_eb2 = np.zeros_like(ctxw)
        for i in range(len(targets)):
            mask = covered[:, i]
            if not mask.any():
                continue
            stack = unit[mask, i]  # (s,G) present sources
            wm = w[mask]
            if wm.sum() <= 0:
                wm = np.ones_like(wm)  # all-zero weights -> uniform hedge
            mu_w = np.average(stack, axis=0, weights=wm)
            # eb2 shrinkage from UNWEIGHTED moments (identical to champion)
            lam = np.ones(stack.shape[1])
            if stack.shape[0] >= 2:
                mu_u = stack.mean(0)
                var_u = stack.var(0, ddof=0)
                snr = (mu_u * mu_u) / (var_u + 1e-12)
                sg = snr**2
                lam = sg / (sg + 1.0)
            norm = k562_norm[i] if k562_norm[i] > 0 else median_norm
            ctxw[i] = mu_w * norm
            ctxw_eb2[i] = mu_w * lam * norm
        tag = ctx.lower()
        variants[f"cons_ctxw_{tag}"] = ctxw.astype(np.float32)
        variants[f"cons_ctxw_{tag}_ctr"] = cd.center_common_response(ctxw).astype(np.float32)
        variants[f"cons_ctxw_{tag}_eb2"] = ctxw_eb2.astype(np.float32)
        variants[f"cons_ctxw_{tag}_eb2_ctr"] = cd.center_common_response(ctxw_eb2).astype(
            np.float32
        )
    return variants


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--src-dir", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument(
        "--rules",
        type=str,
        default="p1,p2",
        help="weight-rule keys from the report (comma-separated; p1,p2,top)",
    )
    args = p.parse_args(argv)

    report = json.loads(args.report.read_text())
    weights = report["weights"]
    rules = [r.strip() for r in args.rules.split(",") if r.strip()]
    for r in rules:
        if r not in weights:
            raise ValueError(f"rule {r!r} not in report weights {sorted(weights)}")

    sources = {}
    for path in sorted(args.src_dir.glob("deltas_*.npz")):
        sources[path.stem.removeprefix("deltas_")] = load_source_npz(path)
    if "k562" not in sources:
        raise ValueError("deltas_k562.npz is required as the reference source")

    args.out_dir.mkdir(parents=True, exist_ok=False)
    all_variants = {}
    for r in rules:
        all_variants.update(
            {f"{r}_{k}": v for k, v in build_ctxw_variants(sources, weights[r]).items()}
        )
    ref = sources["k562"]
    for name, matrix in all_variants.items():
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
        "rules": rules,
        "report": str(args.report),
        "variants": sorted(all_variants),
        "semantics": [
            "source deltas unit-normalized before mixing",
            "per-context weights from basal-similarity report (leak-free)",
            "eb2 factor computed from UNWEIGHTED cross-source moments, "
            "applied to the context-weighted mean (weighting isolated)",
            "amplitude restored to the target's K562 delta norm",
            "*_ctr subtracts the per-gene median across targets",
        ],
    }
    (args.out_dir / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"variants": sorted(all_variants), "out": str(args.out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
