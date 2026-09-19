"""Modal k018 job: build and prep the H1-transfer + dual-moment 2026 submission.

Stages the persisted volume artifacts, clones the repo, builds the full-panel
prediction, runs `vcc prep`, and persists the `.vcc` to the volume. Does NOT
submit unless `submit_from_volume` is run separately.

Run:
  modal run -d tools/modal_k018_h1_dualmoment.py::build_and_prep

Submit (after inspecting prep output):
  modal run -d tools/modal_k018_h1_dualmoment.py::submit_from_volume
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-k018-h1-dualmoment")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = "/root/kytos/data/raw/vcc2026"
OUT_DIR = "/root/kytos/experiments/k018-h1-dualmoment"
VOL_OUT = "/kytos-vol/k018-h1-dualmoment"


@app.function(
    image=modal.Image.debian_slim()
    .apt_install("git", "curl", "unzip")
    .pip_install("vcc-cli", "anndata", "numpy", "pandas", "scipy"),
    timeout=60 * 60 * 6,
    memory=64 * 1024,
    cpu=8,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def build_and_prep(
    contexts: str = "A,B,C",
    h1_contexts: str = "C",
    cells_per_pert: int = 400,
    max_targets: int = 0,
    h1_delta_scale: float = 2.0,
    champion_delta_scale: float = 1.7,
    seed: int = 0,
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
        "download controls",
        f"cd {REPO_DIR}\n"
        "vcc datasets download controls\n"
        "mkdir -p data/raw/vcc2026\n"
        "unzip -q vcc_2026_controls.zip -d data/raw/vcc2026",
    )

    run_step(
        "stage inputs",
        "mkdir -p /root/paired /root/h1train\n"
        "cp /kytos-vol/paired-transfer/paired_transfer_train.npz /root/paired/\n"
        "cp /kytos-vol/paired-transfer/delta_matrix_src.npz /root/paired/\n"
        "cp /kytos-vol/h1-2025-train/h1_train_deltas.npz /root/h1train/\n"
        "ls -lh /root/paired /root/h1train",
    )

    run_step(
        "build k018 prediction",
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k018_h1_dualmoment.py"
        f" --raw-dir {RAW_DIR}"
        " --src-matrix /root/paired/delta_matrix_src.npz"
        " --paired-npz /root/paired/paired_transfer_train.npz"
        " --h1-npz /root/h1train/h1_train_deltas.npz"
        f" --out-dir {OUT_DIR}"
        f" --contexts {contexts}"
        f" --h1-contexts {h1_contexts}"
        f" --cells-per-pert {cells_per_pert}"
        f" --max-targets {max_targets}"
        f" --h1-delta-scale {h1_delta_scale}"
        f" --champion-delta-scale {champion_delta_scale}"
        f" --seed {seed}",
    )

    vcc_path = f"{OUT_DIR}/prediction.prep.vcc"
    run_step(
        "vcc prep",
        f"cd {REPO_DIR}\n"
        "vcc prep"
        f" -g {RAW_DIR}/gene_names.csv"
        f" --perts {RAW_DIR}/pert_counts.csv"
        f" -o {vcc_path}"
        f" {OUT_DIR}/prediction.h5ad",
    )

    run_step(
        "persist to volume",
        f"mkdir -p {VOL_OUT}\n"
        f"cp {vcc_path} {VOL_OUT}/prediction.prep.vcc\n"
        f"cp {OUT_DIR}/meta.json {VOL_OUT}/meta.json\n"
        f"ls -lh {VOL_OUT}",
    )

    vol.commit()
    return {
        "status": "ok",
        "elapsed_s": time.time() - t_start,
        "volume_out": VOL_OUT,
        "vcc_path": vcc_path,
    }


@app.function(
    image=modal.Image.debian_slim().apt_install("git", "curl").pip_install("vcc-cli"),
    timeout=60 * 60,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume(
    model_name: str = "kytos-k018-h1lr-dm-c",
    description: str = (
        "H1-trained low-rank transfer for context C + dual-moment counts; A/B champion k011"
    ),
) -> dict:
    vcc_path = f"{VOL_OUT}/prediction.prep.vcc"
    print(f"submitting {vcc_path}", flush=True)
    result = subprocess.run(
        [
            "vcc",
            "submit",
            vcc_path,
            "--model-name",
            model_name,
            "-d",
            description,
            "--json",
        ],
        stdout=None,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {"status": "ok", "returncode": result.returncode}


@app.local_entrypoint()
def main():
    result = build_and_prep.remote()
    print(result)
