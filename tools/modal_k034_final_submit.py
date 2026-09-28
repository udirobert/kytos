"""Modal k034 job: build + prep the final-phase (contexts D/E/F) submission.

Parameterized clone of ``modal_k027_dual_moment_submit.py`` for the Oct-22
bundle: the same consensus_w_ctr + dual-moment champion recipe, but the raw
bundle directory, deltas NPZ, context letters, and output tag are arguments
instead of baked constants.

Usage (after the Oct-22 controls bundle drops):

  modal run -d tools/modal_k034_final_submit.py::build_and_prep \
      --dataset-id <final-controls-id> \
      --deltas-vol /kytos-vol/k034-final-prep/<variant>/variant_consensus_w_ctr.npz \
      --contexts D,E,F --tag k034-final-dm

  modal run -d tools/modal_k034_final_submit.py::submit_from_volume \
      --tag k034-final-dm --model-name kytos-k034-final-dm

The build function runs ``vcc datasets download <dataset-id>`` inside the
container, unzips it, stages the deltas NPZ from the volume, generates with
``tools/run_k027_dual_moment_submit.py --contexts D,E,F``, then runs
``vcc prep --contexts D,E,F`` and persists the .vcc to the volume.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import modal

app = modal.App("kytos-k034-final-dm")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

LOCAL_ROOT = Path(__file__).resolve().parent.parent
REMOTE_ROOT = Path("/root/kytos")

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
    dataset_id: str,
    deltas_vol: str,
    tag: str,
    contexts: str = "D,E,F",
    cells_per_pert: int = 400,
    seed: int = 0,
    amplitude: float = 1.0,
    bulk_amplitude: float = 0.5,
    prep_dry_run: bool = False,
) -> dict:
    t_start = time.time()
    raw_dir = f"{REMOTE_ROOT}/data/raw/{tag}"
    out_dir = f"{REMOTE_ROOT}/experiments/{tag}"

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
        f"vcc datasets download {dataset_id}\n"
        f"mkdir -p {raw_dir}\n"
        f"unzip -q -o *.zip -d {raw_dir}\n"
        f"ls -lh {raw_dir}"
    )
    run_step("download controls", download_cmd)

    deltas_cmd = f"cp {deltas_vol} /root/deltas.npz\nls -lh /root/deltas.npz"
    run_step("stage deltas", deltas_cmd)

    build_cmd = (
        f"cd {REMOTE_ROOT}\n"
        f"mkdir -p {out_dir}\n"
        "python tools/run_k027_dual_moment_submit.py \\\n"
        f"  --raw-dir {raw_dir} \\\n"
        "  --deltas-npz /root/deltas.npz \\\n"
        f"  --out-dir {out_dir} \\\n"
        f"  --contexts {contexts} \\\n"
        f"  --amplitude {amplitude} \\\n"
        f"  --bulk-amplitude {bulk_amplitude} \\\n"
        f"  --cells-per-pert {cells_per_pert} \\\n"
        f"  --seed {seed}"
    )
    run_step("build dual-moment prediction", build_cmd)

    vcc_path = f"{out_dir}/prediction.prep.vcc"
    # --contexts MUST match the obs context labels produced above; the vcc
    # default is A,B,C and would fail the final panel's verification.
    prep_cmd = (
        f"cd {REMOTE_ROOT}\n"
        "vcc prep \\\n"
        f"  -g {raw_dir}/gene_names.csv \\\n"
        f"  --perts {raw_dir}/pert_counts.csv \\\n"
        f"  --contexts {contexts} \\\n"
        f"  -o {vcc_path} \\\n"
        f"  {'--dry-run ' if prep_dry_run else ''}"
        f"  {out_dir}/prediction.h5ad"
    )
    run_step("vcc prep", prep_cmd)

    if not prep_dry_run:
        persist_cmd = (
            f"mkdir -p /kytos-vol/{tag}\n"
            f"cp {vcc_path} /kytos-vol/{tag}/prediction.prep.vcc\n"
            f"cp {out_dir}/meta.json /kytos-vol/{tag}/meta.json\n"
            f"ls -lh /kytos-vol/{tag}"
        )
        run_step("persist .vcc to Modal Volume", persist_cmd)

    return {
        "status": "ok",
        "elapsed_s": time.time() - t_start,
        "out_dir": out_dir,
        "vcc_path": None if prep_dry_run else vcc_path,
        "volume_path": f"/kytos-vol/{tag}",
        "contexts": contexts,
        "dry_run": prep_dry_run,
    }


@app.function(
    image=modal.Image.debian_slim().apt_install("git", "curl", "unzip").pip_install("vcc-cli"),
    timeout=60 * 60 * 2,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume(tag: str, model_name: str) -> dict:
    """Submit the persisted .vcc from the Modal Volume (approval only)."""
    vcc_path = f"/kytos-vol/{tag}/prediction.prep.vcc"
    print(f"submitting {vcc_path}", flush=True)
    result = subprocess.run(
        ["vcc", "submit", vcc_path, "--model-name", model_name, "--wait"],
        stdout=None,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {"status": "ok", "returncode": result.returncode}
