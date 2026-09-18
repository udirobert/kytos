"""Modal job: extract essential-screen pairs and evaluate transfer methods.

This is the evaluation-only step for k015. It extracts paired deltas from
K562, RPE1, Jurkat, and HepG2 essential screens, evaluates transfer methods,
and saves results + transfer parameters to the volume.

Run:
  modal run -d tools/modal_k015_essential_eval.py::evaluate
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-k015-essential-eval")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = "/root/kytos/data/raw/vcc2026"
REF_DIR = "/root/refs"
OUT_DIR = "/root/kytos/experiments/k015-essential-transfer"


@app.function(
    image=modal.Image.debian_slim()
    .apt_install("git", "curl", "unzip")
    .pip_install("vcc-cli", "anndata", "scanpy", "numpy", "pandas", "scipy"),
    timeout=60 * 60 * 2,
    memory=64 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def evaluate(min_cells: int = 10, top_k: int = 200, test_frac: float = 0.2) -> dict:
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

    # Clone repo
    run_step("clone Kytos", f"rm -rf {REPO_DIR}\ngit clone --depth 1 {REPO_URL} {REPO_DIR}")

    # Download 2026 controls (for gene_names.csv)
    run_step(
        "download controls",
        f"cd {REPO_DIR}\n"
        "vcc datasets download controls\n"
        "mkdir -p data/raw/vcc2026\n"
        "unzip -q vcc_2026_controls.zip -d data/raw/vcc2026",
    )

    # Stage reference files from volume
    run_step(
        "stage reference files",
        f"mkdir -p {REF_DIR}\n"
        f"cp /kytos-vol/refs/k562_bulk.h5ad {REF_DIR}/k562_bulk.h5ad\n"
        f"cp /kytos-vol/refs/rpe1_bulk.h5ad {REF_DIR}/rpe1_bulk.h5ad\n"
        f"cp /kytos-vol/refs/jurkat.h5ad {REF_DIR}/jurkat.h5ad\n"
        f"cp /kytos-vol/refs/hepg2.h5ad {REF_DIR}/hepg2.h5ad\n"
        f"ls -lh {REF_DIR}/",
    )

    # Run the evaluation script
    run_step(
        "run essential transfer evaluation",
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k015_essential_transfer.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --k562-essential-src {REF_DIR}/k562_bulk.h5ad \\\n"
        f"  --rpe1-essential-src {REF_DIR}/rpe1_bulk.h5ad \\\n"
        f"  --jurkat-src {REF_DIR}/jurkat.h5ad \\\n"
        f"  --hepg2-src {REF_DIR}/hepg2.h5ad \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        f"  --min-cells {min_cells} \\\n"
        f"  --top-k {top_k} \\\n"
        f"  --test-frac {test_frac}",
    )

    # Persist results to volume
    run_step(
        "persist to volume",
        f"mkdir -p /kytos-vol/k015-essential-transfer\n"
        f"cp {OUT_DIR}/transfer_report.json /kytos-vol/k015-essential-transfer/\n"
        f"cp {OUT_DIR}/transfer_params.json /kytos-vol/k015-essential-transfer/\n"
        f"cp {OUT_DIR}/essential_transfer_data.npz /kytos-vol/k015-essential-transfer/\n"
        f"ls -lh /kytos-vol/k015-essential-transfer/",
    )

    vol.commit()

    elapsed = time.time() - t_start
    return {"status": "ok", "elapsed_s": elapsed}


@app.local_entrypoint()
def main(min_cells: int = 10, top_k: int = 200, test_frac: float = 0.2):
    result = evaluate.remote(min_cells=min_cells, top_k=top_k, test_frac=test_frac)
    print(result)
