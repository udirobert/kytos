"""Modal k015 job: sparse delta selection on top of champion config.

Applies top-K sparsification to delta vectors before transport, keeping
only the K genes with largest |delta| per target. Validated offline:
top-50 gives +19% cosine improvement on held-out hESC pairs.

Run:
  modal run -d tools/modal_k015_sparse_delta.py::build_and_prep --top-k 100
  modal run -d tools/modal_k015_sparse_delta.py::submit_from_volume --top-k 100

Persists the `.vcc` to the `kytos-vcc` Modal Volume under
/kytos-vol/k015-sparse-top<k>/.
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-k015-sparse-delta")

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
OUT_DIR = "/root/kytos/experiments/k015-sparse-delta"


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
def build_and_prep(
    max_targets: int = 0,
    delta_scale: float = 1.7,
    kd_std: float = 2.0,
    top_k: int = 100,
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

    replogle_cmd = (
        f"mkdir -p {REPLOGLE_DIR}\n"
        f"curl -L --fail --retry 3 -o {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad {REPLOGLE_URL}\n"
        f"ls -lh {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad"
    )
    run_step("download Replogle K562 GWPS bulk", replogle_cmd)

    build_cmd = (
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k015_sparse_delta.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --atlas-src {ATLAS_DIR}/adata_Validation.h5ad \\\n"
        f"  --replogle-src {REPLOGLE_DIR}/K562_gwps_raw_bulk_01.h5ad \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        "  --contexts A,B,C \\\n"
        f"  --kd-std {kd_std} \\\n"
        f"  --delta-scale {delta_scale} \\\n"
        f"  --top-k {top_k} \\\n"
        f"  --max-targets {max_targets}"
    )
    run_step("build k015 sparse-delta prediction", build_cmd)

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

    tag = f"k015-sparse-top{top_k}"
    persist_cmd = (
        f"mkdir -p /kytos-vol/{tag}\n"
        f"cp {vcc_path} /kytos-vol/{tag}/prediction.prep.vcc\n"
        f"cp {OUT_DIR}/meta.json /kytos-vol/{tag}/meta.json\n"
        f"ls -lh /kytos-vol/{tag}"
    )
    run_step("persist .vcc to Modal Volume", persist_cmd)

    if submit:
        result = subprocess.run(
            ["vcc", "submit", vcc_path, "--model-name", f"kytos-{tag}", "--wait"],
            stdout=None,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"vcc submit failed with code {result.returncode}")

    elapsed = time.time() - t_start
    return {
        "status": "ok",
        "elapsed_s": elapsed,
        "out_dir": OUT_DIR,
        "vcc_path": vcc_path,
        "volume_path": f"/kytos-vol/{tag}",
        "delta_scale": delta_scale,
        "kd_std": kd_std,
        "top_k": top_k,
    }


@app.function(
    image=modal.Image.debian_slim().apt_install("git", "curl", "unzip").pip_install("vcc-cli"),
    timeout=60 * 60 * 2,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume(top_k: int = 100) -> dict:
    """Submit the persisted .vcc from the Modal Volume."""
    tag = f"k015-sparse-top{top_k}"
    vcc_path = f"/kytos-vol/{tag}/prediction.prep.vcc"
    print(f"submitting {vcc_path} as kytos-{tag}", flush=True)
    result = subprocess.run(
        ["vcc", "submit", vcc_path, "--model-name", f"kytos-{tag}", "--wait"],
        stdout=None,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {"status": "ok", "returncode": result.returncode}


@app.local_entrypoint()
def main(top_k: int = 100, delta_scale: float = 1.7, kd_std: float = 2.0):
    result = build_and_prep.remote(top_k=top_k, delta_scale=delta_scale, kd_std=kd_std)
    print(result)
