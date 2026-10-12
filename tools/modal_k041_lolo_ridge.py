"""Modal k041 rung 1: leave-one-lineage-out source-mixing oracle.

Per docs/k041-lolo-delta-predictor.md: for each lineage L, for every target
covered by L and >=1 other lineage, solve the per-target nonnegative least
squares

    delta_L[t] ~= sum_{s != L} w_s[t] * u_s[t]        w_s >= 0

over the other lineages' unit-normalized deltas. This is an ORACLE upper
bound on what source-mixing can deliver -- the weights see the held-out
delta. If even the oracle mix cannot beat the fixed transplant consensus on
held-out lineages, learned mixing cannot either and the axis is dead (do not
escalate to rungs 2-3).

Baselines scored on the same (target, L) pairs:
- transplant_consensus: fixed champion weights (k562 2 : others 1) over the
  non-L sources' unit deltas -- exactly what we ship today.
- best_single: best individual source's cosine (diagnostic).

Metrics per target: cos(ridge mix, delta_L), cos(consensus, delta_L),
cos(best single source, delta_L). Aggregated median/mean/share-wins,
weighted by k036 n_samples_voting where available (hct116, hek293t).

Memory: five 18,533-gene unit-normalized delta matrices in float32 (~7 GB)
plus the union target index -> 24 GB container.

Run:
  modal run tools/modal_k041_lolo_ridge.py

Writes /kytos-vol/k041-lolo/lolo_ridge_summary.json + lolo_ridge_cosines.npz.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import modal

app = modal.App("kytos-k041-lolo-ridge")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

LOCAL_ROOT = Path(__file__).resolve().parent.parent

SOURCES = ["k562", "hct116", "hek293t", "jurkat_rest", "jurkat_stim", "cd4"]
WEIGHTED = {s: 1.0 for s in SOURCES}
WEIGHTED["k562"] = 2.0
SRC_GLOB = "/kytos-vol/k034-final-prep/k034-{dir}-all/deltas_{name}.npz"
SRC_DIRS = {
    "k562": "k562",
    "hct116": "hct116",
    "hek293t": "hek293t",
    "cd4": "cd4",
    "jurkat_rest": "jurkat",
    "jurkat_stim": "jurkat",
}
STATS_GLOB = "/kytos-vol/k036-samplestats/{name}_samplestats.npz"

image = modal.Image.debian_slim().pip_install("numpy", "scipy")


def _unit_rows(delta, covered):
    import numpy as np

    d = delta.astype(np.float32)
    norms = np.linalg.norm(d, axis=1, keepdims=True)
    d = d / np.maximum(norms, 1e-12)
    return np.where(covered[:, None], d, 0.0).astype(np.float32)


def _nnls_small(A_rows, y):
    """w = argmin ||sum_s w_s a_s - y||^2, w>=0. A_rows: (S,G) float32."""
    import numpy as np
    from scipy.optimize import nnls

    w, _ = nnls(np.ascontiguousarray(A_rows.T), y.astype(np.float64))
    return w


@app.function(
    image=image,
    timeout=60 * 60 * 2,
    memory=24 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
)
def run() -> dict:
    import numpy as np

    t_start = time.time()
    loaded = {}
    genes_ref = None
    union_targets: list[str] = []
    seen = set()
    for name in SOURCES:
        path = Path(SRC_GLOB.format(dir=SRC_DIRS[name], name=name))
        with np.load(path, allow_pickle=False) as d:
            genes = d["genes"].astype(str).tolist()
            targets = d["targets"].astype(str).tolist()
            delta = d["delta"]
            covered = (
                d["covered"].astype(bool) if "covered" in d.files else np.ones(len(targets), bool)
            )
        if genes_ref is None:
            genes_ref = genes
        elif genes != genes_ref:
            raise ValueError(f"{name}: gene axis differs from reference")
        loaded[name] = {
            "targets": targets,
            "tpos": {t: i for i, t in enumerate(targets)},
            "unit": _unit_rows(delta, covered),
            "covered": covered,
        }
        for t in targets:
            if t not in seen:
                seen.add(t)
                union_targets.append(t)
        print(f"{name}: {len(targets)} targets, {int(covered.sum())} covered", flush=True)

    # Per-source reliability for weighted reporting: k036 n_samples_voting
    # where available (X-Atlas arms), else n_cells or 1.
    for name in SOURCES:
        sdir = Path(STATS_GLOB.format(name=name))
        loaded[name]["votes"] = None
        if not sdir.exists():
            continue
        with np.load(sdir, allow_pickle=False) as d:
            st_targets = d["targets"].astype(str).tolist()
            votes = d["n_samples_voting"].astype(np.float64)
        vmap = {t: votes[i] for i, t in enumerate(st_targets)}
        loaded[name]["votes"] = {t: vmap.get(t, 0.0) for t in loaded[name]["targets"]}

    results = {}
    for held in SOURCES:
        others = [s for s in SOURCES if s != held]
        cos_ridge, cos_cons, cos_best, weights_t, votes_t, covered_t = (
            [],
            [],
            [],
            [],
            [],
            [],
        )
        for t in union_targets:
            lh = loaded[held]
            j = lh["tpos"].get(t)
            if j is None or not lh["covered"][j]:
                continue
            y = lh["unit"][j]
            if not np.any(y):
                continue
            A_rows, w_base = [], []
            for s in others:
                ls = loaded[s]
                i = ls["tpos"].get(t)
                if i is not None and ls["covered"][i] and np.any(ls["unit"][i]):
                    A_rows.append(ls["unit"][i])
                    w_base.append(WEIGHTED[s])
            if not A_rows:
                continue
            A = np.stack(A_rows)
            w_base = np.asarray(w_base, dtype=np.float64)
            w_base /= w_base.sum()

            w_r = _nnls_small(A, y)
            pred_r = w_r @ A
            pred_c = w_base @ A

            def cos(a, b):
                na, nb = np.linalg.norm(a), np.linalg.norm(b)
                return float(a @ b / (na * nb)) if na > 1e-9 and nb > 1e-9 else 0.0

            cos_ridge.append(cos(pred_r, y))
            cos_cons.append(cos(pred_c, y))
            cos_best.append(max(cos(row, y) for row in A))
            covered_t.append(len(A_rows))
            v = lh["votes"].get(t, 0.0) if lh["votes"] else 1.0
            votes_t.append(max(v, 1.0))
            weights_t.append(w_r.tolist())

        cr = np.asarray(cos_ridge)
        cc = np.asarray(cos_cons)
        cb = np.asarray(cos_best)
        vt = np.asarray(votes_t)
        cov = np.asarray(covered_t)
        results[held] = {
            "n_targets": int(len(cr)),
            "median_cos_ridge": float(np.median(cr)) if len(cr) else None,
            "median_cos_consensus": float(np.median(cc)) if len(cc) else None,
            "median_cos_best_single": float(np.median(cb)) if len(cb) else None,
            "mean_cos_ridge": float(np.average(cr, weights=vt)) if len(cr) else None,
            "mean_cos_consensus": float(np.average(cc, weights=vt)) if len(cc) else None,
            "share_ridge_beats_consensus": float((cr > cc + 1e-6).mean()) if len(cr) else None,
            "median_n_sources": float(np.median(cov)) if len(cov) else None,
            "cos_ridge": cr,
            "cos_consensus": cc,
            "cos_best": cb,
        }
        print(
            f"LOLO {held}: n={len(cr)} median ridge {np.median(cr):.4f} "
            f"vs consensus {np.median(cc):.4f} vs best-single {np.median(cb):.4f}; "
            f"ridge wins {100.0 * (cr > cc).mean():.1f}%",
            flush=True,
        )

    summary = {
        "kind": "k041_lolo_ridge_oracle",
        "sources": SOURCES,
        "weights": WEIGHTED,
        "n_union_targets": len(union_targets),
        "per_heldout": {
            k: {kk: vv for kk, vv in v.items() if not kk.startswith("cos_")}
            for k, v in results.items()
        },
        "note": (
            "ridge weights are per-target oracle fits (they see the held-out "
            "delta): this is an upper bound on source-mixing, not a deployable "
            "model. Consensus = fixed champion weights over available non-L "
            "sources."
        ),
        "elapsed_s": time.time() - t_start,
    }
    out_dir = Path("/kytos-vol/k041-lolo")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "lolo_ridge_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    np.savez_compressed(
        out_dir / "lolo_ridge_cosines.npz",
        **{
            f"{held}_{key}": results[held][key]
            for held in results
            for key in ("cos_ridge", "cos_consensus", "cos_best")
        },
    )
    vol.commit()
    return summary


@app.local_entrypoint()
def main():
    summary = run.remote()
    print(json.dumps(summary["per_heldout"], indent=2))
