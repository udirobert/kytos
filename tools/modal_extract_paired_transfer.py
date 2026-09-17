"""Modal job: extract the paired K562/Atlas transfer training set (k012).

Runs tools/extract_paired_transfer.py on a 64 GiB Function — same data
footprint as the prediction builders (Atlas 6.5 GB + Replogle + controls),
but no 360k-cell generation, so it is much faster (~10 min).

Run:
  modal run -d tools/modal_extract_paired_transfer.py::extract

Persists to the kytos-vcc Modal Volume under /kytos-vol/paired-transfer/:
  paired_transfer_train.npz   — paired deltas + basal features (spec:
                                docs/k012-layer-a-pipeline.md)
  delta_matrix_src.npz        — all combined real priors (Track-2 input)
  extract_report.json         — pair counts, targets, timing
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-extract-paired-transfer")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

REPLOGLE_URL = "https://ndownloader.figshare.com/files/35774443"

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = "/root/kytos/data/raw/vcc2026"
ATLAS_DIR = "/root/atlas"
REPLOGLE_DIR = "/root/replogle"
OUT_DIR = "/root/kytos/experiments/k012-paired-transfer"


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
def extract() -> dict:
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
        "fetch 2025 Atlas validation (from volume cache)",
        f"mkdir -p /kytos-vol/atlas {ATLAS_DIR}\n"
        "if [ -f /kytos-vol/atlas/adata_Validation.h5ad ]; then\n"
        f"  cp /kytos-vol/atlas/adata_Validation.h5ad {ATLAS_DIR}/adata_Validation.h5ad\n"
        "else\n"
        "  echo 'atlas missing from volume — upload it first' >&2; exit 1\n"
        "fi\n"
        f"ls -lh {ATLAS_DIR}/adata_Validation.h5ad",
    )

    run_step(
        "download Replogle K562 GWPS bulk",
        f"mkdir -p {REPLOGLE_DIR}\n"
        f"curl -L --fail --retry 3 -o {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad {REPLOGLE_URL}\n"
        f"ls -lh {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad",
    )

    run_step(
        "extract paired transfer set",
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/extract_paired_transfer.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --atlas-src {ATLAS_DIR}/adata_Validation.h5ad \\\n"
        f"  --replogle-src {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad \\\n"
        f"  --out {OUT_DIR}/paired_transfer_train.npz \\\n"
        "  --contexts A,B,C \\\n"
        "  --emit-src-matrix",
    )

    run_step(
        "persist artifacts to Modal Volume",
        "mkdir -p /kytos-vol/paired-transfer\n"
        f"cp {OUT_DIR}/paired_transfer_train.npz /kytos-vol/paired-transfer/\n"
        f"cp {OUT_DIR}/delta_matrix_src.npz /kytos-vol/paired-transfer/\n"
        f"cp {OUT_DIR}/extract_report.json /kytos-vol/paired-transfer/\n"
        "ls -lh /kytos-vol/paired-transfer",
    )

    return {
        "status": "ok",
        "elapsed_s": time.time() - t_start,
        "volume_path": "/kytos-vol/paired-transfer",
    }


@app.local_entrypoint()
def main():
    result = extract.remote()
    print(result)
