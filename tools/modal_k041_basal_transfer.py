"""Modal k041 rung 1b: does basal similarity predict cross-lineage transfer?

Rung-1 oracle showed best-single-source ~= oracle mixing, i.e. the
deployable question is source SELECTION. This job tests the cheapest
selection feature we own: basal-state similarity. For each held-out
lineage L and each other source s it computes

  transfer_cos(s, L) = median_t cos(u_s[t], u_L[t])     over shared targets
  basal_sim(s, L)    = pearson(basal_s, basal_L)        (18,533-gene basal
                                                        expression vectors,
                                                        plus spearman on
                                                        informative genes)

then asks whether rank(basal_sim) predicts rank(transfer_cos) across the
30 ordered (s, L) pairs, and whether the basal-nearest source is the
transfer-best source per held-out L. Also scores the three validation
contexts' basal vectors against each source -- the same computation we
would run on Oct-22 test lines.

Run:
  modal run tools/modal_k041_basal_transfer.py

Writes /kytos-vol/k041-lolo/basal_transfer.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import modal

app = modal.App("kytos-k041-basal-transfer")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

LOCAL_ROOT = Path(__file__).resolve().parent.parent

SOURCES = ["k562", "hct116", "hek293t", "jurkat_rest", "jurkat_stim", "cd4"]
SRC_GLOB = "/kytos-vol/k034-final-prep/k034-{dir}-all/deltas_{name}.npz"
SRC_DIRS = {
    "k562": "k562",
    "hct116": "hct116",
    "hek293t": "hek293t",
    "cd4": "cd4",
    "jurkat_rest": "jurkat",
    "jurkat_stim": "jurkat",
}
BASAL = {
    "k562": "/kytos-vol/k030-ctxlineage/basal-20260924-01/basal_k562.npz",
    "hct116": "/kytos-vol/k030-ctxlineage/basal-20260924-01/basal_hct116.npz",
    "hek293t": "/kytos-vol/k030-ctxlineage/basal-20260924-01/basal_hek293t.npz",
    "cd4": "/kytos-vol/k030-ctxlineage/basal-20260924-01/basal_cd4.npz",
    "jurkat_rest": "/kytos-vol/k034-final-prep/k034-jurkat-all/basal_jurkat.npz",
    "jurkat_stim": "/kytos-vol/k034-final-prep/k034-jurkat-all/basal_jurkat.npz",
    "ctxA": "/kytos-vol/k030-ctxlineage/basal-20260924-01/basal_ctxA.npz",
    "ctxB": "/kytos-vol/k030-ctxlineage/basal-20260924-01/basal_ctxB.npz",
    "ctxC": "/kytos-vol/k030-ctxlineage/basal-20260924-01/basal_ctxC.npz",
    "ctxeval": "/kytos-vol/k030-ctxlineage/basal-20260924-01/basal_ctxeval.npz",
}

image = modal.Image.debian_slim().pip_install("numpy", "scipy")


def _unit_rows(delta, covered):
    import numpy as np

    d = delta.astype(np.float32)
    norms = np.linalg.norm(d, axis=1, keepdims=True)
    return np.where(covered[:, None], d / np.maximum(norms, 1e-12), 0.0).astype(np.float32)


def _load_basal(path):
    import numpy as np

    with np.load(path, allow_pickle=False) as d:
        keys = list(d.files)
        # accept common key spellings
        v = None
        for k in ("basal", "vec", "mean", "x", "expression"):
            if k in d.files:
                v = d[k].astype(np.float64).ravel()
                break
        if v is None:
            v = d[keys[0]]
            if v.ndim > 1:
                v = v.ravel() if v.size == max(v.shape) else None
        g = d["genes"].astype(str).tolist() if "genes" in d.files else None
    return np.asarray(v, dtype=np.float64), g, keys


@app.function(
    image=image,
    timeout=60 * 60,
    memory=24 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
)
def run() -> dict:
    import numpy as np
    from scipy.stats import pearsonr, spearmanr

    t0 = time.time()

    deltas = {}
    genes_ref = None
    for name in SOURCES:
        with np.load(SRC_GLOB.format(dir=SRC_DIRS[name], name=name), allow_pickle=False) as d:
            genes = d["genes"].astype(str).tolist()
            targets = d["targets"].astype(str).tolist()
            covered = (
                d["covered"].astype(bool) if "covered" in d.files else np.ones(len(targets), bool)
            )
            deltas[name] = {
                "tpos": {t: i for i, t in enumerate(targets)},
                "unit": _unit_rows(d["delta"], covered),
                "covered": covered,
            }
        if genes_ref is None:
            genes_ref = genes

    basals = {}
    basal_keys = {}
    for name, path in BASAL.items():
        p = Path(path)
        if not p.exists():
            print(f"missing basal {name}: {path}", flush=True)
            continue
        v, g, keys = _load_basal(p)
        basal_keys[name] = keys
        if g is not None and g != genes_ref:
            pos = {x: i for i, x in enumerate(g)}
            idx = np.array([pos.get(x, -1) for x in genes_ref])
            vv = np.zeros(len(genes_ref))
            ok = idx >= 0
            vv[ok] = v[idx[ok]]
            v = vv
        basals[name] = np.asarray(v, dtype=np.float64)

    # per-(s,L) transfer cosines
    transfer = {}
    for L in SOURCES:
        lt = deltas[L]
        for s in SOURCES:
            if s == L:
                continue
            st = deltas[s]
            shared = [t for t in lt["tpos"] if t in st["tpos"]]
            cos = []
            for t in shared:
                i, j = lt["tpos"][t], st["tpos"][t]
                if not (lt["covered"][i] and st["covered"][j]):
                    continue
                a, b = lt["unit"][i], st["unit"][j]
                if np.any(a) and np.any(b):
                    cos.append(float(a @ b))
            transfer[f"{s}->{L}"] = {
                "n_shared": len(cos),
                "median_cos": float(np.median(cos)) if cos else None,
                "mean_cos": float(np.mean(cos)) if cos else None,
            }

    # basal similarity among sources (pearson on full axis + spearman on
    # top-2000 variable genes across the source set)
    src_basals = {n: basals[n] for n in SOURCES if n in basals}
    stack = np.stack(list(src_basals.values()))
    names = list(src_basals)
    top_var = np.argsort(stack.var(axis=0))[-2000:]
    sim_p = {}
    sim_s = {}
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if i == j:
                continue
            sim_p[f"{a}|{b}"] = float(pearsonr(src_basals[a], src_basals[b]).statistic)
            sim_s[f"{a}|{b}"] = float(
                spearmanr(src_basals[a][top_var], src_basals[b][top_var]).statistic
            )

    # does basal rank predict transfer rank? (30 pairs)
    xs, ys = [], []
    per_L = {}
    for L in SOURCES:
        cands = [
            s
            for s in SOURCES
            if s != L
            and f"{s}|{L}" in sim_s
            and transfer.get(f"{s}->{L}", {}).get("median_cos") is not None
        ]
        if not cands:
            continue
        basal_rank = sorted(cands, key=lambda s: -sim_s[f"{s}|{L}"])
        tr_rank = sorted(cands, key=lambda s: -transfer[f"{s}->{L}"]["median_cos"])
        per_L[L] = {
            "transfer_ranking": [
                (s, round(transfer[f"{s}->{L}"]["median_cos"], 4)) for s in tr_rank
            ],
            "basal_ranking": [(s, round(sim_s[f"{s}|{L}"], 4)) for s in basal_rank],
            "basal_nearest_is_transfer_best": basal_rank[0] == tr_rank[0],
            "basal_nearest_transfer_rank": tr_rank.index(basal_rank[0]) + 1,
        }
        for s in cands:
            xs.append(sim_s[f"{s}|{L}"])
            ys.append(transfer[f"{s}->{L}"]["median_cos"])

    xs = np.asarray(xs)
    ys = np.asarray(ys)
    corr = float(spearmanr(xs, ys).statistic) if len(xs) > 3 else None

    # contexts vs sources -- the Oct-22-shaped output
    ctx_ranking = {}
    for c in ("ctxA", "ctxB", "ctxC", "ctxeval"):
        if c not in basals:
            continue
        ranked = sorted(
            (s for s in SOURCES if s in basals),
            key=lambda s: -float(spearmanr(basals[c][top_var], basals[s][top_var]).statistic),
        )
        ctx_ranking[c] = [
            (s, round(float(spearmanr(basals[c][top_var], basals[s][top_var]).statistic), 4))
            for s in ranked
        ]

    out = {
        "kind": "k041_basal_predicts_transfer",
        "basal_npz_keys": basal_keys,
        "spearman_basal_vs_transfer_all_pairs": corr,
        "n_pairs": int(len(xs)),
        "per_heldout": per_L,
        "context_rankings_spearman_topvar": ctx_ranking,
        "transfer_medians": {k: v["median_cos"] for k, v in transfer.items()},
        "elapsed_s": time.time() - t0,
    }
    out_dir = Path("/kytos-vol/k041-lolo")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "basal_transfer.json").write_text(json.dumps(out, indent=2) + "\n")
    vol.commit()
    return out


@app.local_entrypoint()
def main():
    r = run.remote()
    print(
        json.dumps({k: r[k] for k in ("spearman_basal_vs_transfer_all_pairs", "n_pairs")}, indent=1)
    )
    print(json.dumps(r["per_heldout"], indent=1))
    print(json.dumps(r["context_rankings_spearman_topvar"], indent=1))
