"""Modal job: measure per-cell knockdown-strength spread in the 2025 Atlas.

k006/k007 transport real control cells by a fixed per-target delta plus
isotropic noise. Real CRISPRi perturbations have per-cell knockdown
heterogeneity (guide efficacy, dCas9-KRAB expression), so true perturbed
populations spread along the delta direction. That missing spread is our
leading hypothesis for k006's weak fid component (-0.359).

v2 also records the basal-projection floor (control cells projected onto
each delta direction, in eta units). Our sampler transports real control
cells, so that component is already present in predictions; the
knockdown-specific remainder is kd_std_est = sqrt(eta_std^2 -
basal_eta_std^2). Writes /kytos-vol/k008-kd-spread-v2.json.

This job projects each real perturbed Atlas cell onto its target's mean
delta direction and reports the distribution of the projection coefficient
eta_i: real cells should show mean~1 with substantial spread; our transport
produces eta=1 exactly. The fitted sigma_eta parameterizes k008's
heterogeneous-knockdown sampler.

Run:
  modal run tools/modal_k008_measure_kd_spread.py
"""

from __future__ import annotations

import modal

app = modal.App("kytos-k008-kd-spread")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)


@app.function(
    image=modal.Image.debian_slim().pip_install("anndata", "numpy", "pandas", "scipy", "h5py"),
    timeout=60 * 60,
    memory=32 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
)
def measure() -> dict:
    import json

    import anndata as ad
    import numpy as np

    atlas = ad.read_h5ad("/kytos-vol/atlas/adata_Validation.h5ad")
    print(f"atlas: {atlas.shape}", flush=True)
    print("obs cols:", list(atlas.obs.columns), flush=True)

    pert_col = "target_gene"
    obs = atlas.obs
    perts = obs[pert_col].astype(str).to_numpy()
    ctrl_mask = perts == "non-targeting"

    X = atlas.X
    if hasattr(X, "tocsr"):
        X = X.tocsr()
    Xl = X.copy()
    if hasattr(Xl, "data"):
        Xl.data = np.log1p(Xl.data)
    else:
        Xl = np.log1p(np.asarray(Xl))

    ctrl_mean = np.asarray(Xl[ctrl_mask].mean(axis=0)).ravel()
    C = Xl[ctrl_mask]
    Cd = C.todense() if hasattr(C, "todense") else np.asarray(C)

    targets = sorted(set(perts[~ctrl_mask]))
    print(f"targets: {len(targets)}", flush=True)

    report = {}
    all_eta = []
    for tgt in targets[:60]:  # cap for speed
        m = perts == tgt
        n = int(m.sum())
        if n < 30:
            continue
        T = Xl[m]
        tgt_mean = np.asarray(T.mean(axis=0)).ravel()
        delta = tgt_mean - ctrl_mean
        dn = np.linalg.norm(delta)
        if dn < 1e-6:
            continue
        u = delta / dn
        # eta_i = projection of (cell - ctrl_mean) onto delta direction, in delta units
        if hasattr(T, "todense"):
            Td = T.todense()
        else:
            Td = np.asarray(T)
        eta = np.asarray((Td - ctrl_mean) @ u).ravel() / dn
        all_eta.append(eta)
        # Basal-projection noise floor: control cells projected onto the same
        # direction, in the same eta units. This component of eta_std is already
        # present in our sampler (we transport real control cells), so the
        # knockdown-specific spread is sqrt(eta_std^2 - basal_eta_std^2).
        basal_eta = np.asarray((Cd - ctrl_mean) @ u).ravel() / dn
        basal_eta_std = float(np.std(basal_eta))
        kd_std = float(np.sqrt(max(eta.var() - basal_eta_std**2, 0.0)))
        report[tgt] = {
            "n_cells": n,
            "eta_mean": float(np.mean(eta)),
            "eta_std": float(np.std(eta)),
            "basal_eta_std": basal_eta_std,
            "kd_std_est": kd_std,
            "delta_norm": float(dn),
        }
        print(
            f"  {tgt:12s} n={n:4d} eta={np.mean(eta):.2f}+/-{np.std(eta):.2f} "
            f"basal_eta_std={basal_eta_std:.2f} kd_std~{kd_std:.2f} |delta|={dn:.2f}",
            flush=True,
        )

    eta_all = np.concatenate(all_eta) if all_eta else np.array([0.0])
    summary = {
        "n_targets_measured": len(report),
        "eta_mean_global": float(np.mean(eta_all)),
        "eta_std_global": float(np.std(eta_all)),
        "eta_std_median_of_targets": float(
            np.median([r["eta_std"] for r in report.values()]) if report else 0.0
        ),
        "kd_std_median_of_targets": float(
            np.median([r["kd_std_est"] for r in report.values()]) if report else 0.0
        ),
        "per_target": report,
    }
    with open("/kytos-vol/k008-kd-spread-v2.json", "w") as fh:
        json.dump(summary, fh)
    vol.commit()
    return summary


@app.local_entrypoint()
def main():
    result = measure.remote()
    import json

    top = {k: v for k, v in result.items() if k != "per_target"}
    print(json.dumps(top, indent=2))
