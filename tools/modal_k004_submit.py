"""Modal runner for Kytos k004 real resampling baseline + VCC submission.

Runs `tools/run_k004_real_resampling.py` end-to-end on a 64 GB Modal Function,
then calls `vcc prep` and `vcc submit --wait` on the resulting prediction.
"""

from __future__ import annotations

import os
import subprocess
import time

import modal

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = f"{REPO_DIR}/data/raw/vcc2026"
OUT_DIR = f"{REPO_DIR}/experiments/k004-real-resampling-validation"
VCC_NAME = "kytos-k004-real-resampling"


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

app = modal.App("kytos-k004-submit")


@app.function(
    image=image,
    secrets=[vcc_secret],
    cpu=4.0,
    memory=65536,
    timeout=14400,
)
def run_and_submit() -> dict:
    """Clone, build k004, prep, and submit."""
    t_start = time.time()

    def run_step(name: str, cmd: str, check: bool = True) -> int:
        print(f"\n=== {name} ===", flush=True)
        result = subprocess.run(
            ["bash", "-c", f"set -ex\n{cmd}"],
            stdout=None,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"{name} failed with exit code {result.returncode}")
        return result.returncode

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
        "python tools/run_k004_real_resampling.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        "  --contexts A,B,C"
    )
    run_step("build k004 real resampling baseline", build_cmd)

    vcc_path = f"{OUT_DIR}/prediction.prep.vcc"
    prep_cmd = (
        f"cd {REPO_DIR}\n"
        "vcc prep \\\n"
        f"  -g {RAW_DIR}/gene_names.csv \\\n"
        f"  --perts {RAW_DIR}/pert_counts.csv \\\n"
        f"  -o {vcc_path} \\\n"
        f"  {OUT_DIR}/prediction.h5ad"
    )
    run_step("vcc prep", prep_cmd)

    submit_cmd = (
        f"cd {REPO_DIR}\n"
        "vcc submit \\\n"
        f"  -m {VCC_NAME} \\\n"
        "  --wait \\\n"
        "  --wait-timeout 1800 \\\n"
        f"  {vcc_path}"
    )
    submit_rc = run_step("vcc submit", submit_cmd, check=False)

    elapsed = time.time() - t_start
    return {
        "status": "submitted" if submit_rc == 0 else "prep-ok-submit-failed",
        "elapsed_seconds": round(elapsed, 1),
        "vcc_path": vcc_path,
        "submit_exit_code": submit_rc,
    }
