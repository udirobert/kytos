"""Modal runner for Kytos k005 Atlas-prior model.

Downloads the 2025 VCC validation set, builds the Atlas-informed prediction,
runs `vcc prep`, and stores the `.vcc` + `meta.json` on a Modal Volume so we
can submit later without re-running the heavy prep.
"""

from __future__ import annotations

import os
import subprocess
import time

import modal

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = f"{REPO_DIR}/data/raw/vcc2026"
ATLAS_DIR = "/root/atlas"
ATLAS_URL = (
    "https://storage.googleapis.com/arc-institute-virtual-cell-atlas/"
    "virtual-cell-challenge/2025/validation/adata_Validation.h5ad"
)
OUT_DIR = f"{REPO_DIR}/experiments/k005-atlas-prior-validation"
VCC_NAME = "kytos-k005-atlas-prior"

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
app = modal.App("kytos-k005-atlas-prior")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)


@app.function(
    image=image,
    secrets=[vcc_secret],
    cpu=4.0,
    memory=65536,
    timeout=14400,
    volumes={"/kytos-vol": vol},
)
def build_and_prep(max_targets: int = 0, submit: bool = False) -> dict:
    """Clone, download Atlas + controls, build prediction, prep, persist."""
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

    atlas_cmd = (
        f"mkdir -p {ATLAS_DIR}\n"
        f"curl -L --fail --retry 3 -o {ATLAS_DIR}/adata_Validation.h5ad {ATLAS_URL}\n"
        f"ls -lh {ATLAS_DIR}/adata_Validation.h5ad"
    )
    run_step("download 2025 Atlas validation", atlas_cmd)

    build_cmd = (
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k005_atlas_prior.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --atlas-src {ATLAS_DIR}/adata_Validation.h5ad \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        "  --contexts A,B,C \\\n"
        f"  --max-targets {max_targets}"
    )
    run_step("build k005 Atlas-prior prediction", build_cmd)

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

    persist_cmd = (
        f"mkdir -p /kytos-vol/k005-atlas-prior\n"
        f"cp {vcc_path} /kytos-vol/k005-atlas-prior/prediction.prep.vcc\n"
        f"cp {OUT_DIR}/meta.json /kytos-vol/k005-atlas-prior/meta.json\n"
        "ls -lh /kytos-vol/k005-atlas-prior"
    )
    run_step("persist .vcc to Modal Volume", persist_cmd)

    submit_rc = 0
    if submit:
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
        "status": "submitted" if submit and submit_rc == 0 else "built",
        "elapsed_seconds": round(elapsed, 1),
        "vcc_path": vcc_path,
        "volume_path": "/kytos-vol/k005-atlas-prior",
        "submit_exit_code": submit_rc if submit else None,
    }


@app.function(
    image=image,
    secrets=[vcc_secret],
    cpu=4.0,
    memory=65536,
    timeout=14400,
)
def smoke_test() -> dict:
    """Small 30-target dry-run to validate the Atlas pipeline."""
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

    atlas_cmd = (
        f"mkdir -p {ATLAS_DIR}\n"
        f"curl -L --fail --retry 3 -o {ATLAS_DIR}/adata_Validation.h5ad {ATLAS_URL}\n"
        f"ls -lh {ATLAS_DIR}/adata_Validation.h5ad"
    )
    run_step("download 2025 Atlas validation", atlas_cmd)

    build_cmd = (
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}-smoke\n"
        "python tools/run_k005_atlas_prior.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --atlas-src {ATLAS_DIR}/adata_Validation.h5ad \\\n"
        f"  --out-dir {OUT_DIR}-smoke \\\n"
        "  --contexts A \\\n"
        "  --max-targets 30"
    )
    run_step("build k005 Atlas-prior smoke", build_cmd)

    prep_cmd = (
        f"cd {REPO_DIR}\n"
        "vcc prep --dry-run \\\n"
        f"  -g {RAW_DIR}/gene_names.csv \\\n"
        f"  --perts {RAW_DIR}/pert_counts.csv \\\n"
        f"  {OUT_DIR}-smoke/prediction.h5ad"
    )
    run_step("vcc prep --dry-run", prep_cmd)

    elapsed = time.time() - t_start
    return {
        "status": "ok",
        "elapsed_seconds": round(elapsed, 1),
        "out_dir": f"{OUT_DIR}-smoke",
    }
