"""Modal job: score 2026 contexts A/B/C against reference lineage controls.

Runs tools/score_context_lineage.py on a 64 GiB Function — loads Atlas +
K562 + RPE1 + Jurkat + HepG2 controls and correlates each context's basal
log1p profile against each reference. The decision gate for swapping in
lineage-matched priors (e.g. RPE1 arm for context B).

Run:
  modal run -d tools/modal_lineage_score.py::score

Persists lineage_report.json to /kytos-vol/lineage-score/.
"""

from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("kytos-lineage-score")

vol = modal.Volume.from_name("kytos-vcc", create_if_missing=True)

REPLOGLE_K562_URL = "https://ndownloader.figshare.com/files/35774443"
REPLOGLE_RPE1_URL = "https://ndownloader.figshare.com/files/35775581"
HF_BASE = "https://huggingface.co/datasets/bendidiihab/tx_evaluation/resolve/main"

REPO_URL = "https://github.com/udirobert/kytos.git"
REPO_DIR = "/root/kytos"
RAW_DIR = "/root/kytos/data/raw/vcc2026"
ATLAS_DIR = "/root/atlas"
REF_DIR = "/root/refs"
OUT_DIR = "/root/kytos/experiments/k012-lineage-score"


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
def score() -> dict:
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
        "  echo 'atlas missing from volume' >&2; exit 1\n"
        "fi\n"
        f"ls -lh {ATLAS_DIR}/adata_Validation.h5ad",
    )

    # per-file downloads, cached on the volume — figshare rate-limits repeat hits
    for fname, url in [
        ("k562_bulk.h5ad", REPLOGLE_K562_URL),
        ("rpe1_bulk.h5ad", REPLOGLE_RPE1_URL),
        ("jurkat.h5ad", f"{HF_BASE}/nadig_2024_jurkat.h5ad"),
        ("hepg2.h5ad", f"{HF_BASE}/nadig_2024_hepg2.h5ad"),
    ]:
        run_step(
            f"fetch {fname}",
            f"mkdir -p /kytos-vol/refs {REF_DIR}\n"
            f"if [ -f /kytos-vol/refs/{fname} ]; then\n"
            f"  cp /kytos-vol/refs/{fname} {REF_DIR}/{fname}\n"
            "else\n"
            f"  curl -L --fail --retry 5 --retry-all-errors --retry-delay 30 "
            f"-o /kytos-vol/refs/{fname} {url}\n"
            f"  cp /kytos-vol/refs/{fname} {REF_DIR}/{fname}\n"
            "fi\n"
            f"ls -lh {REF_DIR}/{fname}",
        )

    run_step(
        "score context lineage",
        f"cd {REPO_DIR}\n"
        f"mkdir -p {OUT_DIR}\n"
        "python tools/score_context_lineage.py \\\n"
        f"  --raw-dir {RAW_DIR} \\\n"
        f"  --atlas-src {ATLAS_DIR}/adata_Validation.h5ad \\\n"
        f"  --k562-src {REF_DIR}/k562_bulk.h5ad \\\n"
        f"  --rpe1-src {REF_DIR}/rpe1_bulk.h5ad \\\n"
        f"  --jurkat-src {REF_DIR}/jurkat.h5ad \\\n"
        f"  --hepg2-src {REF_DIR}/hepg2.h5ad \\\n"
        f"  --out {OUT_DIR}/lineage_report.json \\\n"
        "  --contexts A,B,C",
    )

    run_step(
        "persist report to Modal Volume",
        "mkdir -p /kytos-vol/lineage-score\n"
        f"cp {OUT_DIR}/lineage_report.json /kytos-vol/lineage-score/\n"
        "ls -lh /kytos-vol/lineage-score",
    )

    return {
        "status": "ok",
        "elapsed_s": time.time() - t_start,
        "volume_path": "/kytos-vol/lineage-score",
    }


@app.local_entrypoint()
def main():
    result = score.remote()
    print(result)
