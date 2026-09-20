"""Modal k020 job: Track-2 GNN cross-lineage deltas -> .vcc -> submit.

Two stages, both CPU (the GNN is trained; we only predict on it):

  1. predict_and_stage  — runs make_panel_deltas.py + train_gnn_crosslineage.py
     --predict --norm-match using the checkpoint at /kytos-vol/k020/model/gnn.pt,
     writing prediction_deltas.npz to /kytos-vol/k020/prediction_deltas.npz.
     --norm-match rescales each GNN delta to the L2 norm of its own borrowed K562
     signature, so GNN *direction* is the only change vs the k011 champion
     (k020's regression was traced to un-calibrated cosine magnitudes).
  2. build_and_prep     — feeds those deltas through run_k014_trained_model.py
     (champion sampler, kd_std=2.0, delta_scale=1.7), preps, persists the .vcc.
  3. submit_from_volume — vcc submit.

Run:
  modal run -d tools/modal_k020_gnn_model.py::predict_and_stage
  modal run -d tools/modal_k020_gnn_model.py::build_and_prep --persist-dir /kytos-vol/k020b-gnn
  modal run -d tools/modal_k020_gnn_model.py::submit_from_volume \
      --vcc-path /kytos-vol/k020b-gnn/prediction.prep.vcc --tag kytos-k020b-gnn-nm
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-k020-gnn-model")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

REPLOGLE_URL = "https://ndownloader.figshare.com/files/35774443"
REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = "/root/kytos/data/raw/vcc2026"
REPLOGLE_DIR = "/root/replogle"
OUT_DIR = "/root/kytos/experiments/k020-gnn-crosslineage"

DELTA_DST = "/kytos-vol/k020/prediction_deltas.npz"
MODEL_DIR = "/kytos-vol/k020/model"
SRC_MATRIX = "/kytos-vol/paired-transfer/delta_matrix_src.npz"

PREDICT_IMAGE = (
    modal.Image.debian_slim()
    .pip_install("numpy", "pandas", "torch")
    .add_local_dir("tools/track2", "/root/track2")
    .add_local_file("data/raw/vcc2026/gene_names.csv", "/root/gene_names.csv")
    .add_local_file("data/raw/vcc2026/pert_counts.csv", "/root/pert_counts.csv")
)


@app.function(
    image=PREDICT_IMAGE,
    timeout=60 * 60,
    memory=32 * 1024,
    cpu=4,
    volumes={"/kytos-vol": vol},
)
def predict_and_stage() -> dict:
    t_start = time.time()

    def run_step(name: str, cmd: str) -> None:
        print(f"\n=== {name} ===", flush=True)
        result = subprocess.run(
            ["bash", "-c", f"set -ex\n{cmd}"], stdout=None, stderr=subprocess.STDOUT, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"{name} failed with exit code {result.returncode}")

    run_step(
        "make panel K562 deltas",
        "python /root/track2/make_panel_deltas.py \\\n"
        f"  --src-matrix {SRC_MATRIX} \\\n"
        "  --gene-names /root/gene_names.csv \\\n"
        "  --pert-counts /root/pert_counts.csv \\\n"
        "  --out /tmp/panel_k562_deltas.npz",
    )
    run_step(
        "GNN predict (--norm-match)",
        "python /root/track2/train_gnn_crosslineage.py \\\n"
        "  --predict --norm-match \\\n"
        f"  --ckpt {MODEL_DIR}/gnn.pt \\\n"
        "  --panel-deltas /tmp/panel_k562_deltas.npz \\\n"
        "  --out-dir /tmp/k020b",
    )
    run_step(
        "stage norm-matched deltas to volume",
        f"cp /tmp/k020b/prediction_deltas.npz {DELTA_DST}\nls -lh {DELTA_DST}",
    )

    vol.commit()
    return {"status": "ok", "elapsed_s": time.time() - t_start, "dst": DELTA_DST}


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
    delta_scale: float = 1.7, kd_std: float = 2.0, persist_dir: str = "/kytos-vol/k020-gnn"
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

    run_step(
        "fetch GNN deltas from volume",
        f"mkdir -p {OUT_DIR}\n"
        f"cp {DELTA_DST} {OUT_DIR}/prediction_deltas.npz\n"
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
    run_step("build k020 GNN prediction", build_cmd)

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
        f"mkdir -p {persist_dir}\n"
        f"cp {vcc_path} {persist_dir}/prediction.prep.vcc\n"
        f"cp {OUT_DIR}/meta.json {persist_dir}/meta.json\n"
        f"ls -lh {persist_dir}"
    )
    run_step("persist .vcc to Modal Volume", persist_cmd)

    vol.commit()

    elapsed = time.time() - t_start
    return {
        "status": "ok",
        "elapsed_s": elapsed,
        "volume_path": persist_dir,
        "delta_scale": delta_scale,
        "kd_std": kd_std,
    }


@app.function(
    image=modal.Image.debian_slim().apt_install("git", "curl").pip_install("vcc-cli"),
    timeout=60 * 60,
    volumes={"/kytos-vol": vol},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def submit_from_volume(
    vcc_path: str = "/kytos-vol/k020-gnn/prediction.prep.vcc",
    tag: str = "kytos-k020-gnn-crosslineage",
) -> dict:
    """Submit a persisted .vcc from the Modal Volume."""
    import os

    if not os.path.exists(vcc_path):
        raise FileNotFoundError(f"{vcc_path} not found on volume")

    result = subprocess.run(
        [
            "vcc",
            "submit",
            vcc_path,
            "--model-name",
            tag,
            "-d",
            "Track-2 GNN cross-lineage transfer, norm-matched to K562 signature "
            "magnitude (direction-only change vs k011); contexts A/B, C on champion",
            "--json",
        ],
        stdout=None,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"vcc submit failed with exit code {result.returncode}")

    return {"status": "submitted", "tag": tag, "returncode": result.returncode}


@app.local_entrypoint()
def main(delta_scale: float = 1.7, kd_std: float = 2.0):
    stage = predict_and_stage.remote()
    print(f"[predict] {stage}")
    result = build_and_prep.remote(delta_scale=delta_scale, kd_std=kd_std)
    print(f"\nBuild complete: {result}")
    print("Run submit_from_volume to submit when ready.")
