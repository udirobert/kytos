"""Context-matched source self-evaluation (k030).

Gate B's hESC-only eval subset cannot arbitrate source-mixing recipes
(ordering inverted vs official). This harness answers the complementary
question with in-source ground truth: for each delta source S (a context
proxy -- jurkat_stim ~ ctx A, hipsci iPSC ~ hESC/C-like, k562_repA/B ~
K562 replicates, hct116/hek293t ~ epithelial, cd4 ~ T-cell), predict each
of S's measured per-target deltas using ONLY the other sources, under
several fixed mixing recipes, and score unit cosine vs the real delta.

No fitting, no leakage: recipes are fixed a priori, sources are excluded
wholesale (not per-target), and eval targets are simply all targets S
covers. The "oracle" recipe (best single source per target) is the
per-target source-selection ceiling -- the trust-gate headroom.

Run:
  python tools/source_selfeval.py --src-dir experiments/k030-ctxlineage/src-deltas \
      --out experiments/_embargoed/k030-selfeval/report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_consensus_deltas import load_source_npz

# eval source -> context proxy label
CONTEXTS = {
    "jurkat_stim": "ctxA-like (activated Jurkat T)",
    "hipsci": "hESC/iPSC-like",
    "k562_repA": "K562 replicate A",
    "k562_repB": "K562 replicate B",
    "hct116": "HCT116 epithelial",
    "hek293t": "HEK293T epithelial",
    "cd4": "CD4 T-cell rest",
}

# prediction sources excluded per eval source: the eval source itself plus
# its replicate sibling (repA eval must not see repB -- same cells' noise)
SIBLINGS = {
    "k562_repA": {"k562_repB"},
    "k562_repB": {"k562_repA"},
    "jurkat_stim": {"jurkat_rest"},
    "jurkat_rest": {"jurkat_stim"},
}


def unit(m):
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return np.where(n > 0, m / np.where(n == 0, 1.0, n), 0.0)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--src-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)

    sources = {}
    for path in sorted(args.src_dir.glob("deltas_*.npz")):
        sources[path.stem.removeprefix("deltas_")] = load_source_npz(path)

    ref = next(iter(sources.values()))
    genes, targets = ref["genes"], ref["targets"]
    for name, s in sources.items():
        if s["genes"] != genes or s["targets"] != targets:
            raise ValueError(f"{name}: axis mismatch")
    T, G = len(targets), len(genes)

    order = sorted(sources)
    covered = np.stack(
        [
            s["covered"] if s["covered"] is not None else np.ones(T, bool)
            for s in (sources[o] for o in order)
        ]
    )
    U = unit(np.stack([sources[o]["delta"].astype(np.float64) for o in order]))  # (S,T,G)
    oidx = {o: i for i, o in enumerate(order)}

    report = {"axis": {"targets": T, "genes": G}, "contexts": {}}
    for eval_name, ctx_label in CONTEXTS.items():
        if eval_name not in oidx:
            continue
        ei = oidx[eval_name]
        pred_pool = [o for o in order if o != eval_name and o not in SIBLINGS.get(eval_name, set())]
        eval_t = np.flatnonzero(covered[ei])
        u_real = U[ei]  # (T,G)

        recipes = {}
        for o in pred_pool:
            recipes[f"only_{o}"] = ("single", o)
        recipes["mean"] = ("mean", dict((o, 1.0) for o in pred_pool))
        recipes["w_k562x2"] = (
            "mean",
            {o: (2.0 if o.startswith("k562") else 1.0) for o in pred_pool},
        )

        res = {r: [] for r in list(recipes) + ["oracle"]}
        for t in eval_t:
            present = [o for o in pred_pool if covered[oidx[o], t]]
            if not present:
                continue
            stack = {o: U[oidx[o], t] for o in present}
            for rname, (kind, arg) in recipes.items():
                if kind == "single":
                    if arg not in stack:
                        continue
                    pred = stack[arg]
                else:
                    num = np.zeros(G)
                    den = 0.0
                    for o in present:
                        w = arg.get(o, 0.0)
                        if w > 0:
                            num += w * stack[o]
                            den += w
                    if den <= 0:
                        continue
                    pred = num / den
                res[rname].append(float(pred @ u_real[t]))
            res["oracle"].append(float(max(s @ u_real[t] for s in stack.values())))

        ctx = {"label": ctx_label, "n_targets": int(len(eval_t)), "recipes": {}}
        for rname, vals in res.items():
            v = np.asarray(vals)
            if len(v) == 0:
                continue
            ctx["recipes"][rname] = {
                "n": int(len(v)),
                "mean_cos": float(v.mean()),
                "median_cos": float(np.median(v)),
                "p10": float(np.percentile(v, 10)),
                "p90": float(np.percentile(v, 90)),
                "frac_pos": float((v > 0).mean()),
            }
        report["contexts"][eval_name] = ctx

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")

    # printable summary
    for eval_name, ctx in report["contexts"].items():
        print(f"\n=== {eval_name} ({ctx['label']}) n={ctx['n_targets']}")
        rows = sorted(ctx["recipes"].items(), key=lambda kv: -kv[1]["mean_cos"])
        for rname, st in rows:
            print(
                f"  {rname:>16}  mean {st['mean_cos']:+.3f}  med {st['median_cos']:+.3f}"
                f"  p90 {st['p90']:+.3f}  frac>0 {st['frac_pos']:.2f}"
            )
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
