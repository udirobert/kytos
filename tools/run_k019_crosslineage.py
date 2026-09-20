"""Kytos k019 — cross-lineage transfer with an OOD-proxy gate.

Why this exists:
  k015 fit a rank-R *linear* K562->lineage delta map on the ~2.3k paired
  ESSENTIAL targets. On held-out essential targets it beat identity
  (Jurkat cosine 0.439 -> 0.549, still rising with rank), but the
  leaderboard score REGRESSED, because the 272/300 panel targets are
  non-essential and share 0 genes with the essential training set: the map
  fit essential-specific cross-lineage structure that does not extrapolate.

  No public paired cross-lineage data exists for non-essential targets, so
  the real panel extrapolation cannot be measured offline. This script
  builds the closest honest proxy and refuses to ship anything that only
  wins in-distribution.

OOD split (the whole point):
  Per paired target, "conservation" = cosine(x_t, y_t) under raw identity
  transplant -- how well the K562 delta already aligns with the lineage
  delta. We report every model on BOTH tails of held-out targets:
    IN-DIST   = high-conservation (the k015 regime)
    OOD-PROXY = low-conservation  (closest stand-in for panel targets)
  A model earns a submission only if it holds up on OOD-PROXY.

Candidates: identity, global_scalar, low_rank (k015 ref), ridge_dual
  (full-feature linear, no subspace projection), kernel_rbf (nonlinear),
  gene_scale (per-gene coefficient shrunk to global s -- most
  extrapolatable since it uses only per-gene quantities).

Run:
  modal run tools/run_k019_crosslineage.py::fit_all      # full, Modal CPU
  python tools/run_k019_crosslineage.py --subsample 800  # needs local npz copy
"""

from __future__ import annotations

import json
from pathlib import Path

try:  # numpy is absent from the pipx modal runner but present in the remote image;
    import numpy as np  # np is only touched inside remote-executed functions.
except ImportError:  # noqa: BLE001
    np = None

try:
    import modal
except Exception:  # noqa: BLE001  modal optional for local smoke
    modal = None

REPO = Path(__file__).resolve().parents[1]
PAIR_NPZ = "k015-essential-transfer/essential_transfer_data.npz"
LOCAL_NPZ = REPO / "data" / "k019" / "essential_transfer_data.npz"
OUT_DIR = REPO / "experiments" / "k019-crosslineage"

LINEAGES = {  # context -> npz key prefix
    "jurkat": "k562_to_jurkat",  # A
    "rpe1": "k562_to_rpe1",  # B
    "hepg2": "k562_to_hepg2",  # C (hESC proxy)
}


# ------------------------------------------------------------------- metrics
def _cos(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    num = (A * B).sum(1)
    den = np.linalg.norm(A, axis=1) * np.linalg.norm(B, axis=1)
    return num / np.maximum(den, 1e-9)


def _norm_ratio(pred: np.ndarray, truth: np.ndarray) -> np.ndarray:
    return np.linalg.norm(pred, axis=1) / np.maximum(np.linalg.norm(truth, axis=1), 1e-9)


def _sq_dists(A: np.ndarray, B: np.ndarray | None = None) -> np.ndarray:
    if B is None:
        B = A
    aa = (A * A).sum(1)[:, None]
    bb = (B * B).sum(1)[None, :]
    return np.maximum(aa + bb - 2.0 * (A @ B.T), 0.0)


# -------------------------------------------------------------------- models
def m_identity(xtr, ytr, xte, yte):
    return xte, {}


def m_global_scalar(xtr, ytr, xte, yte):
    s = float((xtr * ytr).sum() / max((xtr * xtr).sum(), 1e-9))
    return s * xte, {"s": s}


def _solve_dual(Ktr, Kte, ytr, lam):
    alpha = np.linalg.solve(Ktr + lam * np.eye(ytr.shape[0]), ytr)
    return Kte @ alpha


def _tune_linear(Ktr, Kte, ytr, lam_grid, folds):
    n = ytr.shape[0]
    best = (-2.0, lam_grid[0])
    for lam in lam_grid:
        cs = []
        for f in folds:
            tr = np.ones(n, dtype=bool)
            tr[f] = False
            cs.append(
                _cos(
                    _solve_dual(Ktr[np.ix_(tr, tr)], Ktr[np.ix_(f, tr)], ytr[tr], lam), ytr[f]
                ).mean()
            )
        m = float(np.mean(cs))
        if m > best[0]:
            best = (m, lam)
    return best[1]


def m_ridge_dual(xtr, ytr, xte, yte):
    Ktr = xtr @ xtr.T
    Kte = xte @ xtr.T
    folds = np.array_split(np.random.default_rng(1).permutation(ytr.shape[0]), 5)
    lam = _tune_linear(Ktr, Kte, ytr, (1e-1, 1, 10, 100, 1e3, 1e4), folds)
    return _solve_dual(Ktr, Kte, ytr, lam), {"lam": lam}


def m_kernel_rbf(xtr, ytr, xte, yte):
    med = float(np.median(_sq_dists(xtr))) or 1.0
    folds = np.array_split(np.random.default_rng(2).permutation(ytr.shape[0]), 5)
    n = ytr.shape[0]
    best = (-2.0, 1.0, 10.0)  # cos, gamma, lam
    for gmul in (1e-5, 3e-5, 1e-4):
        gamma = gmul / med
        Ktr = np.exp(-gamma * _sq_dists(xtr))
        lam = _tune_linear(Ktr, None, ytr, (1e-1, 1, 10, 100), folds)
        cs = []
        for f in folds:
            tr = np.ones(n, dtype=bool)
            tr[f] = False
            cs.append(
                _cos(
                    _solve_dual(Ktr[np.ix_(tr, tr)], Ktr[np.ix_(f, tr)], ytr[tr], lam), ytr[f]
                ).mean()
            )
        m = float(np.mean(cs))
        if m > best[0]:
            best = (m, gamma, lam)
    _, gamma, lam = best
    Ktr = np.exp(-gamma * _sq_dists(xtr))
    Kte = np.exp(-gamma * _sq_dists(xte, xtr))  # (n_te, n_tr)
    return _solve_dual(Ktr, Kte, ytr, lam), {"gamma": float(gamma), "lam": float(lam)}


def m_low_rank(xtr, ytr, xte, yte, rank_grid=(16, 32, 64, 128, 256)):
    _, _, vt_s = np.linalg.svd(xtr, full_matrices=False)
    _, _, vt_d = np.linalg.svd(ytr, full_matrices=False)
    max_rank = min(xtr.shape[0], xtr.shape[1], ytr.shape[0], ytr.shape[1])
    scores = []
    for R in rank_grid:
        if R > max_rank:
            continue
        bs, bd = vt_s[:R], vt_d[:R]
        sp, dp = xtr @ bs.T, ytr @ bd.T
        W = np.linalg.solve(sp.T @ sp + 1.0 * np.eye(R), sp.T @ dp)
        scores.append((_cos(((xtr @ bs.T) @ W) @ bd, ytr).mean(), R, bs, bd, W))
    scores.sort(key=lambda t: -t[0])
    _, R, bs, bd, W = scores[0]
    return ((xte @ bs.T) @ W) @ bd, {"rank": R}


def m_gene_scale(xtr, ytr, xte, yte, shrink_grid=(0.0, 0.25, 0.5, 0.75, 1.0)):
    """Per-gene transfer coefficient w_g=<x_g,y_g>/<x_g^2> shrunk to global s."""
    s = float((xtr * ytr).sum() / max((xtr * xtr).sum(), 1e-9))
    n = ytr.shape[0]
    folds = np.array_split(np.random.default_rng(3).permutation(n), 5)

    def _w_for(rows, b):
        num = (xtr[rows] * ytr[rows]).sum(0)
        den = (xtr[rows] * xtr[rows]).sum(0) + 1e-9
        s_r = float((xtr[rows] * ytr[rows]).sum() / max((xtr[rows] * xtr[rows]).sum(), 1e-9))
        return b * (num / den) + (1 - b) * s_r

    best = (-2.0, 0.0)
    for b in shrink_grid:
        cs = []
        for f in folds:
            tr = np.ones(n, dtype=bool)
            tr[f] = False
            cs.append(_cos(xtr[f] * _w_for(np.where(tr)[0], b), ytr[f]).mean())
        m = float(np.mean(cs))
        if m > best[0]:
            best = (m, b)
    b = best[1]
    return xte * _w_for(np.arange(n), b), {"shrink": b, "s": s}


MODELS = {
    "identity": m_identity,
    "global_scalar": m_global_scalar,
    "ridge_dual": m_ridge_dual,
    "kernel_rbf": m_kernel_rbf,
    "low_rank": m_low_rank,
    "gene_scale": m_gene_scale,
}


# ---------------------------------------------------------------- evaluation
def evaluate_pair(
    name: str, x: np.ndarray, y: np.ndarray, gene_cap: int = 6000, target_cap: int = 3000
) -> dict:
    n = min(x.shape[0], target_cap)
    x = np.asarray(x[:n], dtype=np.float32)
    y = np.asarray(y[:n], dtype=np.float32)

    if x.shape[1] > gene_cap:  # keep the highest-variance lineage-response genes
        keep = np.argsort(-y.var(0))[:gene_cap]
        x, y = x[:, keep], y[:, keep]

    cons = _cos(x, y)
    order = np.argsort(cons)
    ood = set(order[: n // 4].tolist())  # least conserved ~ panel-like
    indist = set(order[-n // 4 :].tolist())  # most conserved ~ k015 regime

    te = np.random.default_rng(7).permutation(n)[: max(n // 5, 80)]
    tr = np.setdiff1d(np.arange(n), te)
    ood_mask = np.array([t in ood for t in te])
    indist_mask = np.array([t in indist for t in te])

    xtr, ytr, xte, yte = x[tr], y[tr], x[te], y[te]
    out = {
        "n_train": int(len(tr)),
        "n_test": int(len(te)),
        "n_genes": int(x.shape[1]),
        "models": {},
    }
    for mname, fn in MODELS.items():
        try:
            pred, params = fn(xtr, ytr, xte, yte)
        except Exception as e:  # noqa: BLE001
            out["models"][mname] = {"error": repr(e)}
            continue
        c = _cos(pred, yte)
        out["models"][mname] = {
            "params": params,
            "cos_all": float(c.mean()),
            "cos_indist": float(c[indist_mask].mean()) if indist_mask.any() else None,
            "cos_ood_proxy": float(c[ood_mask].mean()) if ood_mask.any() else None,
            "norm_ratio": float(_norm_ratio(pred, yte).mean()),
        }
    return {"pair": name, "eval": out}


def fit_all_data(subsample_targets: int | None = None, local: bool = False) -> dict:
    if local or modal is None:
        path = LOCAL_NPZ
    else:
        path = Path("/kytos-vol") / PAIR_NPZ
    d = np.load(path, allow_pickle=False)
    results = {}
    for lineage, pref in LINEAGES.items():
        if f"{pref}_src" not in d:
            continue
        x = d[f"{pref}_src"]
        y = d[f"{pref}_dst"]
        if subsample_targets and x.shape[0] > subsample_targets:
            x, y = x[:subsample_targets], y[:subsample_targets]
        results[lineage] = evaluate_pair(lineage, x, y)
    return results


# ------------------------------------------------------------------- runner
if modal is not None:
    app = modal.App("k019-crosslineage")
    vol = modal.Volume.from_name("kytos-vcc")

    @app.function(
        image=modal.Image.debian_slim().pip_install("numpy"),
        timeout=60 * 60 * 3,
        volumes={"/kytos-vol": vol},
        cpu=16,
        memory=64 * 1024,
    )
    def fit_all():
        res = fit_all_data()
        out_dir = Path("/kytos-vol/k019-crosslineage")
        out_dir.mkdir(parents=True, exist_ok=True)
        txt = json.dumps(res, indent=2)
        (out_dir / "ood_proxy_report.json").write_text(txt)
        print(txt)
        return res


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--subsample", type=int, default=0, help="cap paired targets for local smoke")
    args = ap.parse_args(argv)
    res = fit_all_data(subsample_targets=args.subsample or None, local=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "ood_proxy_report.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
