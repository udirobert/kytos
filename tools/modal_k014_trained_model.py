"""Modal k014 job: build predictions from Track-2 trained model deltas.

Expects prediction_deltas.npz to already be on the kytos-vcc volume at
/kytos-vol/k014/prediction_deltas.npz (uploaded after Nebius training).

Run:
  modal run -d tools/modal_k014_trained_model.py::build_and_prep
  modal run -d tools/modal_k014_trained_model.py::submit_from_volume

Persists the .vcc to the kytos-vcc Modal Volume under /kytos-vol/k014-trained/.
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-k014-trained-model")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

REPLOGLE_URL = "https://ndownloader.figshare.com/files/35774443"

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = "/root/kytos/data/raw/vcc2026"
REPLOGLE_DIR = "/root/replogle"
OUT_DIR = "/root/kytos/experiments/k014-track2-mlp"


@app.function(
    image=modal.Image.debian_slim()
    .apt_install("git", "curl", "unzip")
    .pip_install("vcc-cli", "anndata", "scanpy", "numpy", "pandas", "scipy"),
    timeout=60 * 60 * 4,
    memory=64 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def build_and_prep(delta_scale: float = 1.0, kd_std: float = 2.0) -> dict:
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

    run_step("clone Kytos", f"rm -rf {REPO_DIR}\ngit clone --depth 1 {REPO_URL} {REPO_DIR}")

    run_step(
        "download controls",
        f"cd {REPO_DIR}\n"
        "vcc datasets download controls\n"
        "mkdir -p data/raw/vcc2026\n"
        "unzip -q vcc_2026_controls.zip -d data/raw/vcc2026",
    )

    run_step(
        "download Replogle K562 GWPS bulk",
        f"mkdir -p {REPLOGLE_DIR}\n"
        f"curl -L --fail --retry 3 -o {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad {REPLOGLE_URL}\n"
        f"ls -lh {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad",
    )

    # Copy trained deltas from volume
    run_step(
        "fetch trained deltas from volume",
        f"mkdir -p {OUT_DIR}\n"
        "cp /kytos-vol/k014/prediction_deltas.npz "
        f"{OUT_DIR}/prediction_deltas.npz\n"
        f"ls -lh {OUT_DIR}/prediction_deltas.npz",
    )

    build_cmd = (
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k014_trained_model.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --replogle-src {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad \\\n"
        f"  --deltas {OUT_DIR}/prediction_deltas.npz \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        "  --contexts A,B,C \\\n"
        f"  --kd-std {kd_std} \\\n"
        f"  --delta-scale {delta_scale}"
    )
    run_step("build k014 trained-model prediction", build_cmd)

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
        "mkdir -p /kytos-vol/k014-trained\n"
        f"cp {vcc_path} /kytos-vol/k014-trained/prediction.prep.vcc\n"
        f"cp {OUT_DIR}/meta.json /kytos-vol/k014-trained/meta.json\n"
        "ls -lh /kytos-vol/k014-trained"
    )
    run_step("persist .vcc to Modal Volume", persist_cmd)

    vol.commit()

    elapsed = time.time() - t_start
    return {
        "status": "ok",
        "elapsed_s": elapsed,
        "volume_path": "/kytos-vol/k014-trained",
        "delta_scale": delta_scale,
        "kd_std": kd_std,
    }


@app.function(
    image=modal.Image.debian_slim().apt_install("git", "curl").pip_install("vcc-cli"),
    timeout=60 * 60,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume(tag: str = "kytos-k014-trained") -> dict:
    """Submit the persisted .vcc from the Modal Volume."""
    import os

    vcc_path = "/kytos-vol/k014-trained/prediction.prep.vcc"
    if not os.path.exists(vcc_path):
        raise FileNotFoundError(f"{vcc_path} not found on volume")

    result = subprocess.run(
        ["vcc", "submit", "--file", vcc_path, "--name", tag],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(f"vcc submit failed: {result.stderr}")

    return {"status": "submitted", "tag": tag}


@app.local_entrypoint()
def main(delta_scale: float = 1.0, kd_std: float = 2.0):
    result = build_and_prep.remote(delta_scale=delta_scale, kd_std=kd_std)
    print(f"\nBuild complete: {result}")
    print("Run submit_from_volume to submit when ready.")
