"""Modal k015 job: Learn per-gene context transfer from essential screens, apply to panel.

Strategy:
  1. Extract deltas from K562 GWPS (9,869 targets) and essential screens
     (RPE1, Jurkat, HepG2) for shared targets (~2,055).
  2. For each gene, learn a transfer weight: how does the K562 delta for that
     gene relate to the target-context delta across the ~2,055 shared targets?
  3. Apply per-gene transfer weights to the 272 panel targets' K562 GWPS deltas.
  4. Build prediction h5ad, prep, and persist.

Context mapping (from k012 lineage score):
  A -> Jurkat (disc_p = 0.649)
  B -> RPE1   (disc_p = 0.369)
  C -> hESC   (disc_p = 0.379, use Atlas 47 pairs or HepG2 as proxy)

Run:
  modal run -d tools/modal_k015_essential_transfer.py::build_and_prep
  modal run -d tools/modal_k015_essential_transfer.py::submit_from_volume
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-k015-essential-transfer")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

REPLOGLE_K562_GWPS_URL = "https://ndownloader.figshare.com/files/35774443"
ATLAS_URL = (
    "https://storage.googleapis.com/arc-institute-virtual-cell-atlas/"
    "virtual-cell-challenge/2025/validation/adata_Validation.h5ad"
)

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = "/root/kytos/data/raw/vcc2026"
ATLAS_DIR = "/root/atlas"
REF_DIR = "/root/refs"
REPLOGLE_DIR = "/root/replogle"
OUT_DIR = "/root/kytos/experiments/k015-essential-transfer"
TAG = "k015-essential-transfer"


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
def build_and_prep(
    delta_scale: float = 1.7,
    kd_std: float = 2.0,
    submit: bool = False,
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

    # Clone repo
    run_step("clone Kytos", f"rm -rf {REPO_DIR}\ngit clone --depth 1 {REPO_URL} {REPO_DIR}")

    # Download 2026 controls
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
        f"mkdir -p {REF_DIR} {ATLAS_DIR} {REPLOGLE_DIR}\n"
        f"cp /kytos-vol/refs/k562_bulk.h5ad {REF_DIR}/k562_bulk.h5ad\n"
        f"cp /kytos-vol/refs/rpe1_bulk.h5ad {REF_DIR}/rpe1_bulk.h5ad\n"
        f"cp /kytos-vol/refs/jurkat.h5ad {REF_DIR}/jurkat.h5ad\n"
        f"cp /kytos-vol/refs/hepg2.h5ad {REF_DIR}/hepg2.h5ad\n"
        f"cp /kytos-vol/atlas/adata_Validation.h5ad {ATLAS_DIR}/adata_Validation.h5ad\n"
        f"ls -lh {REF_DIR}/",
    )

    # Download Replogle K562 GWPS (the main delta source for panel targets)
    run_step(
        "download Replogle K562 GWPS",
        f"curl -L --fail --retry 3 -o {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad "
        f"{REPLOGLE_K562_GWPS_URL}\n"
        f"ls -lh {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad",
    )

    # Run the k015 script
    run_step(
        "run k015 essential transfer",
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k015_essential_transfer.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --k562-essential-src {REF_DIR}/k562_bulk.h5ad \\\n"
        f"  --rpe1-essential-src {REF_DIR}/rpe1_bulk.h5ad \\\n"
        f"  --jurkat-src {REF_DIR}/jurkat.h5ad \\\n"
        f"  --hepg2-src {REF_DIR}/hepg2.h5ad \\\n"
        f"  --replogle-gwps-src {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        f"  --min-cells 10 \\\n"
        f"  --top-k 200",
    )

    # Build prediction using low-rank transfer
    run_step(
        "build prediction with low-rank transfer",
        f"cd {REPO_DIR}\n"
        "python tools/run_k015_build_prediction.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --replogle-src {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad \\\n"
        f"  --lowrank-models {OUT_DIR}/lowrank_models.npz \\\n"
        f"  --neighbor-map experiments/k007-neighbor-prior-validation/neighbor_map.json \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        f"  --delta-scale {delta_scale} \\\n"
        f"  --kd-std {kd_std}",
    )

    # vcc prep
    vcc_path = f"{OUT_DIR}/prediction.prep.vcc"
    run_step(
        "vcc prep",
        f"cd {REPO_DIR}\n"
        "vcc prep \\\n"
        f"  -g {RAW_DIR}/gene_names.csv \\\n"
        f"  --perts {RAW_DIR}/pert_counts.csv \\\n"
        f"  -o {vcc_path} \\\n"
        f"  {OUT_DIR}/prediction.h5ad",
    )

    # Persist to volume
    run_step(
        "persist to volume",
        f"mkdir -p /kytos-vol/{TAG}\n"
        f"cp {vcc_path} /kytos-vol/{TAG}/prediction.prep.vcc\n"
        f"cp {OUT_DIR}/meta.json /kytos-vol/{TAG}/meta.json\n"
        f"cp {OUT_DIR}/transfer_report.json /kytos-vol/{TAG}/transfer_report.json\n"
        f"cp {OUT_DIR}/lowrank_models.npz /kytos-vol/{TAG}/lowrank_models.npz\n"
        f"ls -lh /kytos-vol/{TAG}/",
    )

    vol.commit()

    elapsed = time.time() - t_start
    return {
        "status": "ok",
        "elapsed_s": elapsed,
        "volume_path": f"/kytos-vol/{TAG}",
        "delta_scale": delta_scale,
        "kd_std": kd_std,
    }


@app.function(
    image=modal.Image.debian_slim().apt_install("git", "curl").pip_install("vcc-cli"),
    timeout=60 * 60 * 2,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume(tag: str = "kytos-k015-essential-transfer") -> dict:
    """Submit the persisted .vcc from the Modal Volume."""
    import os

    vcc_path = f"/kytos-vol/{TAG}/prediction.prep.vcc"
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
def main(delta_scale: float = 1.7, kd_std: float = 2.0):
    result = build_and_prep.remote(
        delta_scale=delta_scale,
        kd_std=kd_std,
    )
    print(result)
