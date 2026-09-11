"""Modal k006 job: build and prep a Replogle/Atlas-prior prediction on Modal.

Prereqs:
  - modal token set (profile active)
  - VCC_TOKEN in .env (only needed if you submit from Modal)

Run:
  modal run -d tools/modal_k006_replogle_prior.py::build_and_prep

This clones Kytos, downloads the 2026 controls, downloads the Replogle
K562 GWPS bulk (and optionally the 2025 Atlas if present on the volume),
builds the prediction, runs `vcc prep`, and persists the `.vcc` to the
`kytos-vcc` Modal Volume.
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-k006-replogle-prior")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

ATLAS_URL = (
    "https://storage.googleapis.com/arc-institute-virtual-cell-atlas/"
    "virtual-cell-challenge/2025/validation/adata_Validation.h5ad"
)
REPLOGLE_URL = "https://ndownloader.figshare.com/files/35774443"

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = "/root/kytos/data/raw/vcc2026"
ATLAS_DIR = "/root/atlas"
REPLOGLE_DIR = "/root/replogle"
OUT_DIR = "/root/kytos/experiments/k006-replogle-prior-validation"


@app.function(
    image=modal.Image.debian_slim()
    .apt_install("git", "curl", "unzip")
    .pip_install("vcc-cli", "cell-eval", "anndata", "scanpy", "numpy", "pandas", "scipy"),
    timeout=60 * 60 * 4,
    memory=64 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_dotenv()],
)
def build_and_prep(max_targets: int = 0, submit: bool = False) -> dict:
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

    # 2025 Atlas (optional, from volume or fresh download)
    atlas_cmd = (
        f"mkdir -p /kytos-vol/atlas {ATLAS_DIR}\n"
        "if [ -f /kytos-vol/atlas/adata_Validation.h5ad ]; then\n"
        f"  cp /kytos-vol/atlas/adata_Validation.h5ad {ATLAS_DIR}/adata_Validation.h5ad\n"
        "else\n"
        "  curl -L --fail --retry 3 -o /kytos-vol/atlas/adata_Validation.h5ad "
        f"{ATLAS_URL}\n"
        f"  cp /kytos-vol/atlas/adata_Validation.h5ad {ATLAS_DIR}/adata_Validation.h5ad\n"
        "fi\n"
        f"ls -lh {ATLAS_DIR}/adata_Validation.h5ad"
    )
    run_step("download 2025 Atlas validation", atlas_cmd)

    # Replogle K562 GWPS bulk (357 MB)
    replogle_cmd = (
        f"mkdir -p {REPLOGLE_DIR}\n"
        f"curl -L --fail --retry 3 -o {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad {REPLOGLE_URL}\n"
        f"ls -lh {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad"
    )
    run_step("download Replogle K562 GWPS bulk", replogle_cmd)

    build_cmd = (
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k006_replogle_prior.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --atlas-src {ATLAS_DIR}/adata_Validation.h5ad \\\n"
        f"  --replogle-src {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        "  --contexts A,B,C \\\n"
        f"  --max-targets {max_targets}"
    )
    run_step("build k006 Replogle-prior prediction", build_cmd)

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
        f"mkdir -p /kytos-vol/k006-replogle-prior\n"
        f"cp {vcc_path} /kytos-vol/k006-replogle-prior/prediction.prep.vcc\n"
        f"cp {OUT_DIR}/meta.json /kytos-vol/k006-replogle-prior/meta.json\n"
        "ls -lh /kytos-vol/k006-replogle-prior"
    )
    run_step("persist .vcc to Modal Volume", persist_cmd)

    elapsed = time.time() - t_start
    return {
        "status": "ok",
        "elapsed_s": elapsed,
        "out_dir": OUT_DIR,
        "vcc_path": vcc_path,
        "volume_path": "/kytos-vol/k006-replogle-prior",
    }


@app.local_entrypoint()
def main():
    result = build_and_prep.remote()
    print(result)
