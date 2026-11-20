"""k201 validation — inspect L0 evidence stores on the volume.

Loads each ``k201-evidence/<dataset>/<run>/stats.npz`` and reports:
- array shapes / dtypes / schema keys
- target coverage, finite-stat fractions per field
- self-gene knockdown audit (fraction of targets whose own-gene lfc < 0)
- z distribution sanity (|z|>2 fraction over estimable entries)
- per-dataset manifest echo

Run:
  modal run -d tools/modal_k201_validate.py
"""

from __future__ import annotations

import json
from pathlib import Path

import modal

VOLUME_ROOT = Path("/kytos-vol")
EVIDENCE_ROOT = VOLUME_ROOT / "k201-evidence"

app = modal.App("kytos-k201-validate")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = modal.Image.debian_slim(python_version="3.12").pip_install("numpy==2.2.6", "pandas==2.2.3")


@app.function(image=image, memory=(24576, 24576), timeout=3600, volumes={"/kytos-vol": volume})
def validate() -> dict:
    import numpy as np

    report = {}
    for ds_dir in sorted(EVIDENCE_ROOT.iterdir()):
        if not ds_dir.is_dir():
            continue
        for run_dir in sorted(ds_dir.iterdir()):
            npz_path = run_dir / "stats.npz"
            manifest_path = run_dir / "manifest.json"
            if not npz_path.exists():
                report[f"{ds_dir.name}/{run_dir.name}"] = {
                    "status": "incomplete",
                    "missing": "stats.npz",
                }
                continue
            with np.load(npz_path, allow_pickle=False) as d:
                keys = sorted(d.files)
                genes = d["genes"].astype(str)
                targets = d["targets"].astype(str)
                covered = d["covered"].astype(bool)
                lfc = d["lfc"]
                se = d["se"]
                q = d["q"]
                z = d["z"]
                n_voting = d["n_voting"]
                kd_eff = d["kd_eff"]

                gpos = {g: i for i, g in enumerate(genes)}
                self_neg = self_tot = 0
                for i, t in enumerate(targets):
                    j = gpos.get(str(t))
                    if j is not None and np.isfinite(lfc[i, j]):
                        self_tot += 1
                        if lfc[i, j] < 0:
                            self_neg += 1

                fin = np.isfinite(lfc[covered]) if covered.any() else np.array([False])
                entry = {
                    "status": "ok",
                    "keys": keys,
                    "n_targets": int(len(targets)),
                    "n_genes": int(len(genes)),
                    "covered": int(covered.sum()),
                    "lfc_finite_frac_cov": float(fin.mean()) if fin.size else 0,
                    "se_finite_frac": float(np.isfinite(se[covered]).mean())
                    if covered.any()
                    else 0,
                    "q_lt_0.05_median": float(np.nanmedian((q[covered] < 0.05).sum(axis=1)))
                    if covered.any()
                    else 0,
                    "z_abs_gt2_frac": float((np.abs(z[covered]) > 2).mean())
                    if covered.any()
                    else 0,
                    "self_kd_neg": f"{self_neg}/{self_tot}",
                    "kd_eff_nan_frac": float(np.isnan(kd_eff).mean()),
                    "n_voting_max": int(n_voting.max()),
                }
            if manifest_path.exists():
                m = json.loads(manifest_path.read_text())
                entry["se_kind"] = m.get("se_kind")
                entry["lfc_kind"] = m.get("lfc_kind")
                entry["sample_unit"] = m.get("sample_unit")
            report[f"{ds_dir.name}/{run_dir.name}"] = entry
    return report


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(validate.remote(), indent=2))
