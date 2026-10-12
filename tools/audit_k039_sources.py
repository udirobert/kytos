"""k039 audit: coverage + basal-match + cross-source agreement for new sources.

Inputs (VPS paths, produced by earlier steps):
  data/raw/scperteval/deltas/deltas_<src>.npz   (new sources; ctrl_mean member)
  data/raw/audit_k039/basal/basal_<name>.npz   (k030 ctxlineage basals)
  data/raw/audit_k039/k023/deltas_<src>.npz    (existing-source panel deltas)

Metrics mirror tools/modal_ctxlineage_basal.py (pearson_all / pearson_nonzero /
spearman_nonzero / pearson_discriminative on the top-2000 context-variable
genes). Caveat: new-source basals/deltas are log-normalized units, existing
sources are mean-log1p(raw) -- rank statistics remain meaningful but the
comparison is coarser than same-units; recorded in the report.
"""

import json
from pathlib import Path

import numpy as np
from scipy import stats

REPO = Path("/opt/kytos/repo")
NEW_DIR = REPO / "data/raw/scperteval/deltas"
BASAL_DIR = REPO / "data/raw/audit_k039/basal"
K023_DIR = REPO / "data/raw/audit_k039/k023"
PANEL = REPO / "data/raw/vcc2026/pert_counts.csv"
TOP_DISC = 2000

NEW_SOURCES = [
    "replogle22rpe1",
    "kaden25rpe1",
    "nadig25jurkat",
    "nadig25hepg2",
    "wessels23",
    "arch1",
]
OLD_SOURCES = ["k562", "hct116", "hek293t", "cd4"]
CONTEXTS = ["A", "B", "C", "eval"]


def pearson(a, b, mask):
    a, b = a[mask], b[mask]
    if a.std() < 1e-8 or b.std() < 1e-8:
        return float("nan")
    return float(stats.pearsonr(a, b)[0])


def main():
    import pandas as pd

    panel_targets = sorted(pd.read_csv(PANEL).iloc[:, 0].astype(str).unique())

    # ---- basals ----------------------------------------------------------
    ctx_basal, src_basal = {}, {}
    for c in CONTEXTS:
        with np.load(BASAL_DIR / f"basal_ctx{c}.npz") as d:
            ctx_basal[c] = d["basal"].astype(np.float64)
    for s in OLD_SOURCES:
        with np.load(BASAL_DIR / f"basal_{s}.npz") as d:
            src_basal[s] = d["basal"].astype(np.float64)

    new = {}
    for s in NEW_SOURCES:
        p = NEW_DIR / f"deltas_{s}.npz"
        if not p.exists():
            print(f"[skip] {s}: no deltas npz yet")
            continue
        with np.load(p) as d:
            new[s] = {
                "genes": d["genes"].astype(str),
                "targets": d["targets"].astype(str),
                "delta": d["delta"],
                "covered": d["covered"],
                "n_cells": d["n_cells"],
                "ctrl_mean": d["ctrl_mean"].astype(np.float64),
            }
        src_basal[s] = new[s]["ctrl_mean"]

    # ---- coverage --------------------------------------------------------
    coverage = {}
    pset = set(panel_targets)
    for s, v in new.items():
        cov = sorted(set(v["targets"][v["covered"]]) & pset)
        coverage[s] = {
            "n_targets": int(v["covered"].sum()),
            "panel_covered": len(cov),
            "panel_targets": cov,
        }

    # ---- basal similarity (same masks as ctxlineage report) ---------------
    ctx_mat = np.stack([ctx_basal[c] for c in CONTEXTS])
    disc_mask = np.zeros(ctx_mat.shape[1], dtype=bool)
    disc_mask[ctx_mat.std(axis=0).argsort()[::-1][:TOP_DISC]] = True
    all_mask = np.ones_like(disc_mask)

    sim = {}
    for c in CONTEXTS:
        sim[c] = {}
        for s in OLD_SOURCES + list(new):
            b = src_basal[s]
            both = (ctx_basal[c] > 0) & (b > 0)
            sim[c][s] = {
                "pearson_all": pearson(ctx_basal[c], b, all_mask),
                "pearson_nonzero": pearson(ctx_basal[c], b, both),
                "spearman_nonzero": float(stats.spearmanr(ctx_basal[c][both], b[both])[0])
                if both.sum() > 10
                else float("nan"),
                "pearson_discriminative": pearson(ctx_basal[c], b, disc_mask),
                "n_both_nonzero": int(both.sum()),
            }

    # ---- cross-source agreement on shared panel targets ------------------
    old_deltas = {}
    for s in OLD_SOURCES:
        p = K023_DIR / f"deltas_{s}.npz"
        if p.exists():
            with np.load(p) as d:
                old_deltas[s] = {
                    t: d["delta"][i]
                    for i, t in enumerate(d["targets"].astype(str))
                    if d["covered"][i]
                }

    agree = {}
    for s, v in new.items():
        shared = sorted(set(v["targets"][v["covered"]]) & pset)
        if not shared:
            continue
        tpos = {t: i for i, t in enumerate(v["targets"])}
        per_src = {}
        for os_, od in old_deltas.items():
            rows = []
            for t in shared:
                if t not in od:
                    continue
                a, b = v["delta"][tpos[t]], od[t]
                m = (np.abs(a) > 0) | (np.abs(b) > 0)
                if m.sum() > 50:
                    c = stats.pearsonr(a[m], b[m])[0]
                    rows.append((t, float(c)))
            if rows:
                vals = [r[1] for r in rows]
                per_src[os_] = {
                    "n": len(vals),
                    "median_pearson": float(np.median(vals)),
                    "frac_pos": float(np.mean([x > 0 for x in vals])),
                }
        agree[s] = {"n_shared_panel": len(shared), "per_source": per_src}

    report = {
        "created": "2026-10-12",
        "run_id": "k039-audit-01",
        "units_caveat": "new sources = log-normalized mean diff; existing = "
        "mean(log1p(raw)); rank stats meaningful, magnitudes "
        "not directly comparable",
        "coverage": {
            s: {k: v for k, v in c.items() if k != "panel_targets"} for s, c in coverage.items()
        },
        "panel_target_lists": {s: c["panel_targets"] for s, c in coverage.items()},
        "similarity": sim,
        "agreement": agree,
    }
    out = REPO / "data/raw/audit_k039/k039_audit_report.json"
    out.write_text(json.dumps(report, indent=1))

    # ---- console summary --------------------------------------------------
    print("== coverage ==")
    for s, c in coverage.items():
        print(f"  {s:<16} targets={c['n_targets']:>6}  panel={c['panel_covered']}/300")
    print("== basal spearman_nonzero (context x source) ==")
    for c in CONTEXTS:
        row = (
            "  " + c + "  " + "  ".join(f"{s}:{sim[c][s]['spearman_nonzero']:.3f}" for s in sim[c])
        )
        print(row)
    print("== basal pearson_discriminative ==")
    for c in CONTEXTS:
        row = (
            "  "
            + c
            + "  "
            + "  ".join(f"{s}:{sim[c][s]['pearson_discriminative']:.3f}" for s in sim[c])
        )
        print(row)
    print("== agreement ==")
    print(json.dumps(agree, indent=1))
    print(f"[out] {out}")


if __name__ == "__main__":
    main()
