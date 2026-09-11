"""Modal k007 job: k006 priors + STRING-neighbor imputation for uncovered targets.

Same pipeline as k006; the run script adds a third dispatch tier:
Atlas/Replogle real delta > neighbor-imputed delta > fallback.

Prereqs:
  - modal token set (profile active)
  - VCC_TOKEN in .env (only needed if you submit from Modal)

Run:
  modal run -d tools/modal_k007_neighbor_prior.py::build_and_prep

Persists the `.vcc` to the `kytos-vcc` Modal Volume under
/kytos-vol/k007-neighbor-prior/.
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-k007-neighbor-prior")

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
OUT_DIR = "/root/kytos/experiments/k007-neighbor-prior-validation"


@app.function(
    image=modal.Image.debian_slim()
    .apt_install("git", "curl", "unzip")
    .pip_install("vcc-cli", "cell-eval", "anndata", "scanpy", "numpy", "pandas", "scipy"),
    timeout=60 * 60 * 4,
    memory=64 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
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
        "python tools/run_k007_neighbor_prior.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --atlas-src {ATLAS_DIR}/adata_Validation.h5ad \\\n"
        f"  --replogle-src {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        "  --contexts A,B,C \\\n"
        f"  --max-targets {max_targets}"
    )
    run_step("build k007 neighbor-prior prediction", build_cmd)

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
        f"mkdir -p /kytos-vol/k007-neighbor-prior\n"
        f"cp {vcc_path} /kytos-vol/k007-neighbor-prior/prediction.prep.vcc\n"
        f"cp {OUT_DIR}/meta.json /kytos-vol/k007-neighbor-prior/meta.json\n"
        "ls -lh /kytos-vol/k007-neighbor-prior"
    )
    run_step("persist .vcc to Modal Volume", persist_cmd)

    elapsed = time.time() - t_start
    return {
        "status": "ok",
        "elapsed_s": elapsed,
        "out_dir": OUT_DIR,
        "vcc_path": vcc_path,
        "volume_path": "/kytos-vol/k007-neighbor-prior",
    }


@app.function(
    image=modal.Image.debian_slim().apt_install("git", "curl", "unzip").pip_install("vcc-cli"),
    timeout=60 * 60 * 2,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume() -> dict:
    """Submit the persisted .vcc from the Modal Volume."""
    vcc_path = "/kytos-vol/k007-neighbor-prior/prediction.prep.vcc"
    print(f"submitting {vcc_path}", flush=True)
    result = subprocess.run(
        [
            "vcc",
            "submit",
            vcc_path,
            "--model-name",
            "kytos-k007-neighbor-prior",
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
