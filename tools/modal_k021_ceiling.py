"""Modal k021 job: ceiling / attribution analysis on the 2025 Atlas validation set.

Self-contained: the runner (tools/run_k021_ceiling.py) and the kytos package are
injected into the image via add_local_* rather than cloning from GitHub, so this
job needs no repo-push credential. It stages the persisted validation h5ad +
paired K562 transfer npz, runs the three-arm attribution (identity_ds1p7 vs
true_ds1p0 vs real-data ceiling), and persists the summaries back to the volume.
CPU only -- no GPU, no submission slot. Does NOT submit.

Run:
  modal run -d tools/modal_k021_ceiling.py::run_ceiling

Persisted to /kytos-vol/k021-ceiling/:
  summary.json, real_de.csv, per-arm results.csv
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import modal

app = modal.App("kytos-k021-ceiling")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

REPO_DIR = "/root/kytos"
OUT_DIR = "/root/kytos/experiments/k021-ceiling"
VOL_OUT = "/kytos-vol/k021-ceiling"

LOCAL_ROOT = Path(__file__).resolve().parents[1]

_cell_eval_pkgs = [
    "cell-eval",
    "anndata",
    "scanpy",
    "numpy",
    "pandas",
    "scipy",
    "polars",
    "h5py",
]


def _build_image() -> modal.Image:
    return (
        modal.Image.debian_slim()
        .pip_install(*_cell_eval_pkgs)
        .add_local_dir(LOCAL_ROOT / "src/kytos", f"{REPO_DIR}/src/kytos", copy=True)
        .add_local_file(
            LOCAL_ROOT / "tools/run_k021_ceiling.py",
            f"{REPO_DIR}/tools/run_k021_ceiling.py",
            copy=True,
        )
    )


@app.function(
    image=_build_image(),
    timeout=60 * 60 * 4,
    memory=64 * 1024,
    cpu=8,
    volumes={"/kytos-vol": vol},
)
def run_ceiling(
    cells_per_target: int = 400,
    control_cells: int = 4000,
    max_targets: int = 0,
    profile: str = "minimal",
    keep_pred: bool = False,
) -> dict:
    t_start = time.time()

    def run_step(name: str, cmd: str) -> None:
        print(f"\n=== {name} ===", flush=True)
        result = subprocess.run(
            ["bash", "-c", f"set -ex\n{cmd}"],
            stdout=None,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{name} failed with exit code {result.returncode}")

    run_step(
        "stage inputs",
        "mkdir -p /root/atlas /root/paired\n"
        "cp /kytos-vol/atlas/adata_Validation.h5ad /root/atlas/\n"
        "cp /kytos-vol/paired-transfer/paired_transfer_train.npz /root/paired/\n"
        "ls -lh /root/atlas /root/paired",
    )

    keep_flag = " --keep-pred" if keep_pred else ""
    run_step(
        "run ceiling attribution",
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k021_ceiling.py"
        " --val-h5ad /root/atlas/adata_Validation.h5ad"
        " --paired-npz /root/paired/paired_transfer_train.npz"
        f" --outdir {OUT_DIR}"
        f" --cells-per-target {cells_per_target}"
        f" --control-cells {control_cells}"
        f" --max-targets {max_targets}"
        f" --profile {profile}{keep_flag}",
    )

    run_step(
        "persist to volume",
        f"mkdir -p {VOL_OUT}\n"
        f"cp {OUT_DIR}/summary.json {VOL_OUT}/\n"
        f"cp {OUT_DIR}/real_de.csv {VOL_OUT}/\n"
        f"for d in {OUT_DIR}/*/; do\n"
        '  name=$(basename "$d")\n'
        f"  mkdir -p {VOL_OUT}/$name\n"
        f'  cp "$d"*.csv {VOL_OUT}/$name/ 2>/dev/null || true\n'
        "done\n"
        f"ls -lhR {VOL_OUT} | head -60",
    )

    vol.commit()
    elapsed = time.time() - t_start
    return {"status": "ok", "elapsed_s": elapsed, "volume_out": VOL_OUT}


@app.local_entrypoint()
def main(
    cells_per_target: int = 400,
    control_cells: int = 4000,
    max_targets: int = 0,
    profile: str = "minimal",
    keep_pred: bool = False,
):
    result = run_ceiling.remote(
        cells_per_target=cells_per_target,
        control_cells=control_cells,
        max_targets=max_targets,
        profile=profile,
        keep_pred=keep_pred,
    )
    print(result)
