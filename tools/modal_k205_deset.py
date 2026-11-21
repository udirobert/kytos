"""k205 — L2 DE-set predictor + calibration (engine-v2 design §5).

Consumes the L1 consensus store (k204) and per-store L0 evidence to
learn `de_prob(target, gene)` — the probability a gene is truly DE
under the target's knockdown — then emits a calibrated `lfc_cal`.

Training protocol is leave-one-label-store-out (LOSO): for each label
store E (a dataset with honest sample-level statistics), the L1
consensus is rebuilt WITHOUT E so features cannot leak E's own
measurement; labels are E's within-store DE calls (q < 0.05). This
matches deployment semantics: predicting DE in an unseen context from
all-source cross-context evidence.

Outputs (stats.npz, same axis conventions as L1):
    genes, targets, covered        -- union axis (from the L1 run)
    de_prob   (T,G) f32            -- P(gene truly DE | evidence)
    lfc_cal   (T,G) f32            -- empirical-Bayes shrunk lfc_hat
Manifest records: label stores, features, model, per-E metrics
(AUROC/AUPRC, predicted-vs-measured DE counts), threshold, L1 run id.

Run:
    modal run tools/modal_k205_deset.py                # build + audit
    modal run tools/modal_k205_deset.py --stage loso   # only LOSO L1s
"""

from __future__ import annotations

import json
from pathlib import Path

import modal

APP_NAME = "kytos-k205-deset"
EVIDENCE_ROOT = Path("/kytos-vol/k201-evidence")
L1_ROOT = Path("/kytos-vol/k204-meta")
L1_RUN = "h204-20261121-03"
OUT_ROOT = Path("/kytos-vol/k205-deset")
RUN_ID = "h205-20261121-01"

# label stores: honest welch-per-sample/gem_group/batch statistics,
# different contexts, high coverage
LABEL_STORES = ("hct116", "hek293t", "k562")

FEATURES = (
    "z_hat",
    "se_z",
    "tau2_z",
    "i2_z",
    "votes_pos",
    "votes_neg",
    "n_sources",
    "log1p_n_voting",
    "lfc_hat",
    "se_hat",
    "kd_eff",
)
POS_Q = 0.05
POS_PER_TARGET = 300
NEG_PER_TARGET = 600

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "pandas==2.2.3",
        "scipy==1.15.3",
        "scikit-learn==1.5.2",
    )
    .add_local_file(str(Path(__file__).resolve()), "/root/modal_k205_deset.py")
    .add_local_file(
        str(Path(__file__).resolve().with_name("modal_k204_meta.py")),
        "/root/modal_k204_meta.py",
    )
)

app = modal.App(APP_NAME, image=image)
vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)


def _latest_run(ds_dir: Path) -> Path | None:
    runs = [r for r in ds_dir.iterdir() if (r / "stats.npz").exists()]
    return max(runs, key=lambda r: r.name) if runs else None


def _load_feats(npz):
    """Materialize each feature member once -- npz[name] re-decompresses
    the full array on every access, so dict-of-arrays is mandatory."""
    import numpy as np

    arr = {}
    for name in FEATURES:
        if name == "log1p_n_voting":
            arr[name] = np.log1p(np.nan_to_num(npz["n_voting"].astype(np.float32), nan=0.0))
        else:
            arr[name] = npz[name].astype(np.float32)
    return arr


def _feature_matrix(arr, n_genes, kd_row, rows, cols=None):
    """Assemble (len(rows), G or len(cols), F) block from loaded arrays."""
    import numpy as np

    F = len(FEATURES)
    ncol = n_genes if cols is None else len(cols)
    out = np.full((len(rows), ncol, F), np.nan, np.float32)
    for fi, name in enumerate(FEATURES):
        if name == "kd_eff":
            v = np.broadcast_to(kd_row[rows, None], (len(rows), n_genes))
        else:
            v = arr[name][rows]
        if cols is not None:
            v = v[:, cols]
        out[:, :, fi] = v.astype(np.float32)
    return out


@app.function(
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=14400,
    volumes={"/kytos-vol": vol},
)
def build(run_id: str = RUN_ID, l1_run: str = L1_RUN, stage: str = "all") -> dict:
    import modal_k204_meta as k4
    import numpy as np

    rng = np.random.default_rng(0)

    # ---- stage 1: LOSO L1 rebuilds (one per label store) ----
    loso_dirs = {}
    for E in LABEL_STORES:
        lid = f"loso-{E}"
        ldir = L1_ROOT / lid
        if not (ldir / "stats.npz").exists() and stage in ("all", "loso"):
            print(f"building LOSO L1 without {E}...", flush=True)
            k4.meta.local(lid, [E])
        loso_dirs[E] = ldir
    if stage == "loso":
        return {"status": "ok", "stage": "loso", "dirs": {k: str(v) for k, v in loso_dirs.items()}}

    # ---- stage 2: assemble training rows ----
    X_rows, y_rows, grp_rows = [], [], []
    G_LEN = None
    for E in LABEL_STORES:
        es_dir = _latest_run(EVIDENCE_ROOT / E)
        eq = np.load(es_dir / "stats.npz")
        l1 = np.load(loso_dirs[E] / "stats.npz")
        if G_LEN is None:
            G_LEN = len(l1["genes"])
        l1f = _load_feats(l1)
        l1kd = l1["kd_eff"].astype(np.float32)
        u_targets = l1["targets"].astype(str)
        u_idx = {t: i for i, t in enumerate(u_targets)}
        e_tgts = eq["targets"].astype(str)
        e_cov = eq["covered"].astype(bool)
        shared = [(u_idx[t], i) for i, t in enumerate(e_tgts) if e_cov[i] and t in u_idx]
        print(f"{E}: {len(shared)} shared targets for labels", flush=True)
        q = eq["q"]
        for u_row, e_row in shared:
            pos = np.flatnonzero(q[e_row] < POS_Q)
            if pos.size > POS_PER_TARGET:
                pos = rng.choice(pos, POS_PER_TARGET, replace=False)
            neg = np.flatnonzero(~(q[e_row] < POS_Q))
            neg = rng.choice(neg, min(NEG_PER_TARGET, neg.size), replace=False)
            cols = np.concatenate([pos, neg])
            X_rows.append(_feature_matrix(l1f, G_LEN, l1kd, [u_row], cols)[0])
            y_rows.append(
                np.concatenate([np.ones(pos.size), np.zeros(neg.size)]).astype(np.float32)
            )
            grp_rows.append(np.full(cols.size, len(grp_rows), np.int32))
    X = np.concatenate(X_rows)
    y = np.concatenate(y_rows)
    grp = np.concatenate(grp_rows)
    print(f"training set: {X.shape[0]} rows, pos frac {y.mean():.4f}", flush=True)

    # ---- stage 3: train + held-out eval (target-grouped split) ----
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    u_groups = np.unique(grp)
    rng.shuffle(u_groups)
    n_tr = int(0.85 * len(u_groups))
    tr_g = set(u_groups[:n_tr])
    tr = np.array([g in tr_g for g in grp])
    te = ~tr
    clf = HistGradientBoostingClassifier(
        max_iter=400,
        learning_rate=0.06,
        max_leaf_nodes=63,
        early_stopping=True,
        validation_fraction=0.1,
        random_state=0,
    )
    clf.fit(X[tr], y[tr])
    p_te = clf.predict_proba(X[te])[:, 1]
    metrics = {
        "auroc": float(roc_auc_score(y[te], p_te)),
        "auprc": float(average_precision_score(y[te], p_te)),
        "brier": float(brier_score_loss(y[te], p_te)),
        "n_train": int(tr.sum()),
        "n_eval": int(te.sum()),
        "pos_frac_eval": float(y[te].mean()),
    }
    # predicted vs measured DE counts at 0.5 on eval targets
    te_groups = grp[te]
    pred_cnt, true_cnt = {}, {}
    for g, pv, yv in zip(te_groups, p_te, y[te]):
        pred_cnt[g] = pred_cnt.get(g, 0) + (pv > 0.5)
        true_cnt[g] = true_cnt.get(g, 0) + yv
    metrics["de_count_pred_median"] = float(np.median(list(pred_cnt.values())))
    metrics["de_count_true_median_sampled"] = float(np.median(list(true_cnt.values())))
    print(f"eval: {metrics}", flush=True)

    # ---- stage 4: predict on the full L1 corpus ----
    l1 = np.load(L1_ROOT / l1_run / "stats.npz")
    l1f = _load_feats(l1)
    l1kd = l1["kd_eff"].astype(np.float32)
    T, G = l1["targets"].shape[0], l1["genes"].shape[0]
    de_prob = np.full((T, G), np.nan, np.float32)
    CH = 64
    for t0 in range(0, T, CH):
        t1 = min(t0 + CH, T)
        blk = _feature_matrix(l1f, G, l1kd, np.arange(t0, t1)).reshape(-1, len(FEATURES))
        de_prob[t0:t1] = clf.predict_proba(blk)[:, 1].reshape(t1 - t0, G).astype(np.float32)
    de_prob[~l1["covered"]] = np.nan

    # ---- stage 5: lfc_cal — per-target EB shrinkage toward 0 ----
    lfc_hat = l1["lfc_hat"].astype(np.float64)
    se_hat = l1["se_hat"].astype(np.float64)
    floor = np.nanmedian(se_hat[np.isfinite(se_hat) & (se_hat > 0)])
    lfc_cal = np.full((T, G), np.nan, np.float32)
    for t0 in range(0, T, 256):
        t1 = min(t0 + 256, T)
        lh, sh = lfc_hat[t0:t1], se_hat[t0:t1]
        sig2 = np.nanvar(lh, axis=1, keepdims=True)
        lam = sig2 / (sig2 + np.maximum(sh, floor) ** 2)
        lfc_cal[t0:t1] = (lh * lam).astype(np.float32)

    out = OUT_ROOT / run_id
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "stats.npz",
        genes=l1["genes"],
        targets=l1["targets"],
        covered=l1["covered"],
        de_prob=de_prob,
        lfc_cal=lfc_cal,
    )
    manifest = {
        "run_id": run_id,
        "layer": "L2",
        "l1_run": l1_run,
        "method": (
            "HistGradientBoostingClassifier trained LOSO on label stores "
            f"{list(LABEL_STORES)} (features exclude each label store's own "
            "contribution); labels = within-store q<0.05. de_prob predicted "
            "on full L1. lfc_cal = lfc_hat * sig2_t/(sig2_t + se'^2), "
            "per-target empirical-Bayes shrinkage to 0, se' = max(se_hat, "
            f"global floor={floor:.4g})"
        ),
        "features": list(FEATURES),
        "label_stores": list(LABEL_STORES),
        "metrics": metrics,
        "n_targets": int(T),
        "notes": (
            "de_count band check vs measured 22-44 regime pending on "
            "per-target (not sampled) eval; sampled-eval medians reported. "
            "Control-expression feature deferred (not in L1 schema)."
        ),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    vol.commit()
    return {"status": "ok", "out": str(out), "metrics": metrics}


@app.function(image=image, volumes={"/kytos-vol": vol}, cpu=4, memory=49152, timeout=3600)
def audit(run_id: str, l1_run: str) -> dict:
    """Threshold-grid DE-count audit on the emitted store.

    The design gate (§5/§9): predicted DE-count median in the measured
    22--44/target band, with the operating threshold chosen to land
    there rather than fixed at 0.5. Also reports the label stores'
    own measured counts (regime comparison) and lfc_cal diagnostics.
    """
    import numpy as np

    out = OUT_ROOT / run_id
    k5 = np.load(out / "stats.npz")
    l1 = np.load(L1_ROOT / l1_run / "stats.npz")
    de_prob = k5["de_prob"]
    lfc_cal = k5["lfc_cal"]
    covered = k5["covered"].astype(bool)
    cov_t = covered.any(axis=1)
    targets = k5["targets"].astype(str)

    THRESH = [
        0.5,
        0.55,
        0.6,
        0.62,
        0.64,
        0.65,
        0.66,
        0.68,
        0.7,
        0.75,
        0.8,
        0.9,
        0.95,
        0.99,
    ]
    curve = []
    for th in THRESH:
        cnt = np.nansum(de_prob > th, axis=1)  # NaN > th is False
        c = cnt[cov_t]
        curve.append(
            {
                "thr": th,
                "median_cov": float(np.median(c)),
                "q25": float(np.percentile(c, 25)),
                "q75": float(np.percentile(c, 75)),
                "frac_in_band": float(((c >= 22) & (c <= 44)).mean()),
            }
        )
    # operating threshold = first whose covered median lands in band
    op = next(
        (c["thr"] for c in curve if 22 <= c["median_cov"] <= 44),
        None,
    )
    if op is None:
        # closest median to band midpoint
        op = min(curve, key=lambda c: abs(c["median_cov"] - 33))["thr"]

    # measured per-target DE counts from label stores (regime check)
    t_idx = {t: i for i, t in enumerate(targets)}
    measured = {}
    for E in LABEL_STORES:
        es = np.load(_latest_run(EVIDENCE_ROOT / E) / "stats.npz")
        et = es["targets"].astype(str)
        q = es["q"]
        cnts = np.nansum(q < POS_Q, axis=1)
        shared = [i for i, tg in enumerate(et) if tg in t_idx and cov_t[t_idx[tg]]]
        measured[E] = {
            "n_shared_cov": len(shared),
            "median_de_count": float(np.median(cnts[shared])),
            "q25": float(np.percentile(cnts[shared], 25)),
            "q75": float(np.percentile(cnts[shared], 75)),
        }

    # lfc_cal diagnostics
    lfc_hat = l1["lfc_hat"]
    fin = np.isfinite(lfc_cal)
    diag = {
        "lfc_cal_finite_frac": float(fin[covered].mean()),
        "targets_all_nan_lfc_cal": int((~fin.any(axis=1) & cov_t).sum()),
    }
    m = fin & np.isfinite(lfc_hat) & (lfc_hat != 0)
    shrink = np.abs(lfc_cal[m]) / np.abs(lfc_hat[m])
    diag["shrink_ratio_median"] = float(np.median(shrink))
    diag["shrink_ratio_q10"] = float(np.percentile(shrink, 10))
    diag["shrink_ratio_q90"] = float(np.percentile(shrink, 90))

    rep = {
        "run_id": run_id,
        "l1_run": l1_run,
        "n_targets_cov": int(cov_t.sum()),
        "count_curve": curve,
        "operating_threshold": op,
        "measured_label_counts": measured,
        "lfc_cal_diag": diag,
    }
    (out / "audit.json").write_text(json.dumps(rep, indent=2))
    vol.commit()
    return rep


@app.local_entrypoint()
def main(run_id: str = RUN_ID, stage: str = "all") -> None:
    if stage == "audit":
        print(json.dumps(audit.remote(run_id, L1_RUN), indent=2))
    else:
        print(json.dumps(build.remote(run_id, L1_RUN, stage), indent=2))
