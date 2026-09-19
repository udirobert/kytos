"""Modal k017 job: offline cell-eval validation harness on the 2025 H1 set.

Stages the persisted volume artifacts (2025 validation h5ad, paired transfer
npz, H1 train deltas, combined source matrix), clones the repo for the runner
and kytos.models.dual_moment, runs the count-level evaluation, and persists
the summaries back to the volume. Does NOT submit anything.

Run:
  modal run -d tools/modal_k017_offline_cell_eval.py::run_cell_eval \
    -- --candidates identity_ds1p7,h1lr64_ds1p7_selfTrain,h1lr64_ds2p0_selfTrainScaled

Persisted to /kytos-vol/k017-offline-cell-eval/:
  summary.json, real_de.csv, per-candidate results.csv (+ prediction.h5ad
  when --keep-pred is passed)
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-k017-offline-cell-eval")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
OUT_DIR = "/root/kytos/experiments/k017-offline-cell-eval"
VOL_OUT = "/kytos-vol/k017-offline-cell-eval"


@app.function(
    image=modal.Image.debian_slim()
    .apt_install("git", "curl")
    .pip_install("cell-eval", "anndata", "scanpy", "numpy", "pandas", "scipy", "polars", "h5py"),
    timeout=60 * 60 * 6,
    memory=64 * 1024,
    cpu=8,
    volumes={"/kytos-vol": vol},
)
def run_cell_eval(
    candidates: str = "identity_ds1p7,h1lr64_ds1p7_selfTrain,h1lr64_ds2p0_selfTrainScaled",
    cells_per_target: int = 400,
    control_cells: int = 4000,
    max_targets: int = 0,
    profile: str = "minimal",
    keep_pred: bool = False,
    ceiling: bool = False,
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

    run_step("clone Kytos", f"rm -rf {REPO_DIR}\ngit clone --depth 1 {REPO_URL} {REPO_DIR}")

    run_step(
        "stage inputs",
        "mkdir -p /root/atlas /root/paired /root/h1train\n"
        "cp /kytos-vol/atlas/adata_Validation.h5ad /root/atlas/\n"
        "cp /kytos-vol/paired-transfer/paired_transfer_train.npz /root/paired/\n"
        "cp /kytos-vol/paired-transfer/delta_matrix_src.npz /root/paired/\n"
        "cp /kytos-vol/h1-2025-train/h1_train_deltas.npz /root/h1train/\n"
        "ls -lh /root/atlas /root/paired /root/h1train",
    )

    flags = []
    if keep_pred:
        flags.append("--keep-pred")
    if ceiling:
        flags.append("--ceiling")
    flag_str = (" " + " ".join(flags)) if flags else ""
    run_step(
        "run offline cell-eval",
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k017_offline_cell_eval.py"
        " --val-h5ad /root/atlas/adata_Validation.h5ad"
        " --paired-npz /root/paired/paired_transfer_train.npz"
        " --h1-npz /root/h1train/h1_train_deltas.npz"
        " --src-matrix /root/paired/delta_matrix_src.npz"
        f" --outdir {OUT_DIR}"
        f" --candidates '{candidates}'"
        f" --cells-per-target {cells_per_target}"
        f" --control-cells {control_cells}"
        f" --max-targets {max_targets}"
        f" --profile {profile}{flag_str}",
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
        f"ls -lhR {VOL_OUT} | head -50",
    )

    vol.commit()
    elapsed = time.time() - t_start
    return {"status": "ok", "elapsed_s": elapsed, "volume_out": VOL_OUT}


@app.local_entrypoint()
def main(
    candidates: str = "identity_ds1p7,h1lr64_ds1p7_selfTrain,h1lr64_ds2p0_selfTrainScaled",
    cells_per_target: int = 400,
    control_cells: int = 4000,
    max_targets: int = 0,
    profile: str = "minimal",
    keep_pred: bool = False,
    ceiling: bool = False,
):
    result = run_cell_eval.remote(
        candidates=candidates,
        cells_per_target=cells_per_target,
        control_cells=control_cells,
        max_targets=max_targets,
        profile=profile,
        keep_pred=keep_pred,
        ceiling=ceiling,
    )
    print(result)
