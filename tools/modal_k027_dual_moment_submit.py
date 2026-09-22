"""Modal k027 job: build + prep the consensus + dual-moment submission .vcc.

Same pipeline shape as k026 (vcc download controls -> build -> vcc prep ->
persist) with the same delta source (variant_consensus_w_ctr.npz from the
k023 honest extraction), but generation is build_prediction_dual_moment,
selected via Gate B sweep gate-20260922-02. Arm metrics are embargoed
(experiments/_embargoed/k025-eval2-gate/).

Run:
  modal run -d tools/modal_k027_dual_moment_submit.py::build_and_prep
  modal run -d tools/modal_k027_dual_moment_submit.py::submit_from_volume

Persists to /kytos-vol/k027-consensus-dm/.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import modal

app = modal.App("kytos-k027-consensus-dm")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

LOCAL_ROOT = Path(__file__).resolve().parent.parent
REMOTE_ROOT = Path("/root/kytos")
RAW_DIR = "/root/kytos/data/raw/vcc2026"
OUT_DIR = "/root/kytos/experiments/k027-consensus-dm"
DELTAS_VOL = (
    "/kytos-vol/k023-consensus/extract-20260921-02-honest/variants/variant_consensus_w_ctr.npz"
)
TAG = "k027-consensus-dm"
MODEL_NAME = "kytos-k027-consensus-dm"

image = (
    modal.Image.debian_slim()
    .apt_install("git", "curl", "unzip")
    .pip_install("vcc-cli", "anndata", "scanpy", "numpy", "pandas", "scipy")
    .add_local_dir(LOCAL_ROOT / "src/kytos", str(REMOTE_ROOT / "src/kytos"), copy=True)
    .add_local_file(
        str(LOCAL_ROOT / "tools/run_k007_neighbor_prior.py"),
        str(REMOTE_ROOT / "tools/run_k007_neighbor_prior.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/run_k005_atlas_prior.py"),
        str(REMOTE_ROOT / "tools/run_k005_atlas_prior.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/run_k006_replogle_prior.py"),
        str(REMOTE_ROOT / "tools/run_k006_replogle_prior.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/perturbation_priors.py"),
        str(REMOTE_ROOT / "tools/perturbation_priors.py"),
        copy=True,
    )
    .add_local_file(
        str(LOCAL_ROOT / "tools/run_k027_dual_moment_submit.py"),
        str(REMOTE_ROOT / "tools/run_k027_dual_moment_submit.py"),
        copy=True,
    )
)


@app.function(
    image=image,
    timeout=60 * 60 * 4,
    memory=64 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def build_and_prep(
    max_targets: int = 0,
    cells_per_pert: int = 400,
    seed: int = 0,
    amplitude: float = 1.0,
    bulk_amplitude: float = 0.5,
) -> dict:
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

    download_cmd = (
        f"cd {REMOTE_ROOT}\n"
        "vcc datasets download controls\n"
        "mkdir -p data/raw/vcc2026\n"
        "unzip -q -o vcc_2026_controls.zip -d data/raw/vcc2026\n"
        "ls -lh data/raw/vcc2026"
    )
    run_step("download controls", download_cmd)

    deltas_cmd = (
        f"cp {DELTAS_VOL} /root/variant_consensus_w_ctr.npz\n"
        "ls -lh /root/variant_consensus_w_ctr.npz"
    )
    run_step("stage consensus deltas", deltas_cmd)

    build_cmd = (
        f"cd {REMOTE_ROOT}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k027_dual_moment_submit.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --deltas-npz /root/variant_consensus_w_ctr.npz \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        "  --contexts A,B,C \\\n"
        f"  --amplitude {amplitude} \\\n"
        f"  --bulk-amplitude {bulk_amplitude} \\\n"
        f"  --cells-per-pert {cells_per_pert} \\\n"
        f"  --seed {seed} \\\n"
        f"  --max-targets {max_targets}"
    )
    run_step("build k027 dual-moment prediction", build_cmd)

    vcc_path = f"{OUT_DIR}/prediction.prep.vcc"
    prep_cmd = (
        f"cd {REMOTE_ROOT}\n"
        "vcc prep \\\n"
        f"  -g {RAW_DIR}/gene_names.csv \\\n"
        f"  --perts {RAW_DIR}/pert_counts.csv \\\n"
        f"  -o {vcc_path} \\\n"
        f"  {OUT_DIR}/prediction.h5ad"
    )
    run_step("vcc prep", prep_cmd)

    persist_cmd = (
        f"mkdir -p /kytos-vol/{TAG}\n"
        f"cp {vcc_path} /kytos-vol/{TAG}/prediction.prep.vcc\n"
        f"cp {OUT_DIR}/meta.json /kytos-vol/{TAG}/meta.json\n"
        f"ls -lh /kytos-vol/{TAG}"
    )
    run_step("persist .vcc to Modal Volume", persist_cmd)

    elapsed = time.time() - t_start
    return {
        "status": "ok",
        "elapsed_s": elapsed,
        "out_dir": OUT_DIR,
        "vcc_path": vcc_path,
        "volume_path": f"/kytos-vol/{TAG}",
        "model_name": MODEL_NAME,
    }


@app.function(
    image=modal.Image.debian_slim().apt_install("git", "curl", "unzip").pip_install("vcc-cli"),
    timeout=60 * 60 * 2,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume() -> dict:
    """Submit the persisted .vcc from the Modal Volume."""
    vcc_path = f"/kytos-vol/{TAG}/prediction.prep.vcc"
    print(f"submitting {vcc_path}", flush=True)
    result = subprocess.run(
        [
            "vcc",
            "submit",
            vcc_path,
            "--model-name",
            MODEL_NAME,
            "--wait",
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
