"""Modal test runner for the Kytos VCC 2026 pipeline.

This is a disposable, single-shot function that:
1. Clones the Kytos repo into the Modal container.
2. Downloads the official 2026 controls using the VCC token.
3. Builds the k003 sparse mean-shift baseline.
4. Runs `vcc prep --dry-run` on the full panel.

It is intentionally simple and cheap: it proves the Modal memory envelope
(32 GiB) and `vcc prep` path before we spend real compute on a denser model.
"""

from __future__ import annotations

import os
import subprocess
import time

import modal

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = f"{REPO_DIR}/data/raw/vcc2026"
OUT_DIR = f"{REPO_DIR}/experiments/k003-mean-shift-validation"


vcc_token = os.environ["VCC_TOKEN"]


image = (
    modal.Image.from_registry("python:3.12-bookworm")
    .apt_install("git", "curl", "build-essential", "libhdf5-dev", "unzip")
    .pip_install(
        "anndata",
        "cell-eval",
        "h5py",
        "numpy",
        "pandas",
        "pdex",
        "scipy",
        "vcc-cli",
    )
)

vcc_secret = modal.Secret.from_dict({"VCC_TOKEN": vcc_token})

app = modal.App("kytos-pipeline-test")


@app.function(
    image=image,
    secrets=[vcc_secret],
    cpu=4.0,
    memory=32768,
    timeout=10800,
)
def run_pipeline_test() -> dict:
    """Clone, download, build baseline, and dry-run vcc prep."""
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

    clone_cmd = f"rm -rf {REPO_DIR}\ngit clone --depth 1 {REPO_URL} {REPO_DIR}"
    run_step("clone Kytos", clone_cmd)

    download_cmd = (
        f"cd {REPO_DIR}\n"
        "vcc datasets download controls\n"
        "mkdir -p data/raw/vcc2026\n"
        "unzip -q vcc_2026_controls.zip -d data/raw/vcc2026"
    )
    run_step("download controls", download_cmd)

    build_cmd = (
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k003_mean_shift.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        "  --contexts A,B,C"
    )
    run_step("build k003 baseline", build_cmd)

    prep_cmd = (
        f"cd {REPO_DIR}\n"
        "vcc prep --dry-run \\\n"
        f"  -g {RAW_DIR}/gene_names.csv \\\n"
        f"  --perts {RAW_DIR}/pert_counts.csv \\\n"
        f"  {OUT_DIR}/prediction.h5ad"
    )
    run_step("dry-run vcc prep", prep_cmd)

    elapsed = time.time() - t_start
    return {
        "status": "ok",
        "elapsed_seconds": round(elapsed, 1),
        "repo_dir": REPO_DIR,
        "out_dir": OUT_DIR,
    }
