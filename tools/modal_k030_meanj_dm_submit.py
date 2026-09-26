"""Modal k030 job: 5-source plain-mean consensus (+Jurkat) + dual-moment .vcc.

Deltas: ``variant_consensus_mean.npz`` on src5j -- uniform mean of
unit-normalized per-source deltas over {k562, hct116, hek293t, cd4,
jurkat_stim}, rescaled to K562 norm; built by
``tools/build_consensus_deltas.py``. Jurkat is the only real
context-A-like signal in the arsenal (source self-eval: no other source
predicts Jurkat responses, cosine ~0). Generator config identical to
the k027 champion: build_prediction_dual_moment(amplitude=1.0,
bulk_amplitude=0.5, pool_k=4). Arm metrics embargoed
(experiments/_embargoed/k030-ctxlineage.md).

Run:
  modal run -d tools/modal_k030_meanj_dm_submit.py::build_and_prep
  modal run -d tools/modal_k030_meanj_dm_submit.py::submit_from_volume

Persists to /kytos-vol/k030-consensus-meanj-dm/.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import modal

app = modal.App("kytos-k030-consensus-meanj-dm")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

LOCAL_ROOT = Path(__file__).resolve().parent.parent
REMOTE_ROOT = Path("/root/kytos")
RAW_DIR = "/root/kytos/data/raw/vcc2026"
OUT_DIR = "/root/kytos/experiments/k030-consensus-meanj-dm"
DELTAS_VOL = "/kytos-vol/k030-ctxlineage/newsrc-5j/variant_consensus_mean.npz"
TAG = "k030-consensus-meanj-dm"
MODEL_NAME = "kytos-k030-consensus-meanj-dm"

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
def build_and_prep(max_targets: int = 0, cells_per_pert: int = 400, seed: int = 0) -> dict:
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
        f"cp {DELTAS_VOL} /root/variant_consensus_mean.npz\nls -lh /root/variant_consensus_mean.npz"
    )
    run_step("stage consensus deltas", deltas_cmd)

    build_cmd = (
        f"cd {REMOTE_ROOT}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/run_k027_dual_moment_submit.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --deltas-npz /root/variant_consensus_mean.npz \\\n"
        f"  --out-dir {OUT_DIR} \\\n"
        f"  --run-id {TAG} \\\n"
        "  --contexts A,B,C \\\n"
        "  --amplitude 1.0 \\\n"
        "  --bulk-amplitude 0.5 \\\n"
        "  --pool-k 4 \\\n"
        f"  --cells-per-pert {cells_per_pert} \\\n"
        f"  --seed {seed} \\\n"
        f"  --max-targets {max_targets}"
    )
    run_step("build k030 dual-moment prediction", build_cmd)

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
    timeout=60 * 60 * 4,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume(wait_until_utc: str = "") -> dict:
    """Submit the persisted .vcc from the Modal Volume.

    ``wait_until_utc`` (ISO-8601, e.g. "2026-09-23T00:05:00") optionally delays
    submission until after the daily allowance reset — server-side, so it does
    not depend on the local session staying alive.
    """
    if wait_until_utc:
        import datetime

        target = datetime.datetime.fromisoformat(wait_until_utc).replace(
            tzinfo=datetime.timezone.utc
        )
        delay = max(0.0, target.timestamp() - time.time())
        print(f"sleeping {delay:.0f}s until {wait_until_utc}", flush=True)
        time.sleep(delay)

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
