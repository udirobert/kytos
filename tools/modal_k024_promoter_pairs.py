"""Build the promoter-neighbor pairs table (k024) on Modal.

Why Modal: ftp.ebi.ac.uk is unreachable from the dev network, and the GTF
download (~45 MB gz) is the only heavy step. Everything else is a pure port
of the reference pairs builder (kaipengm2 prepare.py::pairs /
prepare_promoters).

Outputs (on the Modal volume under ``k024-promoter-prior/<run_id>/``)
-------------------------------------------------------------------
- ``promoter_pairs.csv``   (target, neighbor, distance, chromosome,
                            target_tss, neighbor_tss, target_strand,
                            neighbor_strand, divergent)
- ``gencode_tss.csv``      the parsed per-symbol TSS table (provenance)
- ``manifest.json``        gencode URL/sha256, target universe, coverage

Run:
  modal run tools/modal_k024_promoter_pairs.py --run-id pairs-YYYYMMDD-NN
"""

from __future__ import annotations

import re
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
OUT_DIR = VOLUME_ROOT / "k024-promoter-prior"
PAIRED_PATH = VOLUME_ROOT / "paired-transfer/paired_transfer_train.npz"
PANEL_COUNTS = REMOTE_ROOT / "data/vcc2026/pert_counts.csv"
PANEL_GENES = REMOTE_ROOT / "data/vcc2026/gene_names.csv"

GENCODE_URL = (
    "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_47/"
    "gencode.v47.annotation.gtf.gz"
)

app = modal.App("kytos-k024-promoter-pairs")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy==2.2.6", "pandas==2.2.3", "requests==2.32.4")
    .add_local_file(
        LOCAL_ROOT / "tools/promoter_neighbor.py",
        str(REMOTE_ROOT / "tools/promoter_neighbor.py"),
        copy=True,
    )
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/gene_names.csv",
        str(PANEL_GENES),
        copy=True,
    )
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/pert_counts.csv",
        str(PANEL_COUNTS),
        copy=True,
    )
)


@app.function(
    image=image,
    cpu=(2.0, 2.0),
    memory=(8192, 8192),
    timeout=1800,
    startup_timeout=300,
    retries=1,
    max_containers=1,
    volumes={str(VOLUME_ROOT): volume},
)
def build_pairs(run_id: str) -> dict:
    import hashlib
    import json
    import sys
    import tempfile

    import numpy as np
    import pandas as pd
    import requests

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import promoter_neighbor as pn

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Use a new alphanumeric run ID (hyphens/underscores allowed)")
    out = OUT_DIR / run_id
    pairs_path = out / "promoter_pairs.csv"
    if pairs_path.exists():
        raise FileExistsError(f"{pairs_path} already exists -- use a new run ID")
    out.mkdir(parents=True, exist_ok=True)

    # Target universe: 2026 panel targets ∪ 47 Atlas-eval targets (the eval
    # set the k022 diagnostic scores).
    panel_targets = pd.read_csv(PANEL_COUNTS).iloc[:, 0].astype(str).tolist()
    with np.load(PAIRED_PATH, allow_pickle=False) as paired:
        eval_targets = paired["paired_targets"].astype(str).tolist()
    targets = sorted(set(panel_targets) | set(eval_targets))
    genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()

    sha = hashlib.sha256()
    with tempfile.NamedTemporaryFile(suffix=".gtf.gz") as tmp:
        with requests.get(GENCODE_URL, stream=True, timeout=600) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=1 << 20):
                sha.update(chunk)
                tmp.write(chunk)
        tmp.flush()
        tss = pn.parse_gencode_tss(tmp.name)
    gencode_sha256 = sha.hexdigest()

    pairs = pn.build_pairs(tss, targets, genes)
    pairs.to_csv(pairs_path, index=False)
    tss.to_csv(out / "gencode_tss.csv", index=False)

    n_eval_with_pairs = len(set(pairs.target.unique()) & set(eval_targets))
    manifest = {
        "run_id": run_id,
        "gencode": {
            "url": GENCODE_URL,
            "sha256": gencode_sha256,
            "n_gene_features": int(len(tss)),
            "n_unique_symbols": int((~tss.gene.duplicated(keep=False)).sum()),
        },
        "window_bp": pn.WINDOW_BP,
        "ramp_floor_bp": pn.RAMP_FLOOR_BP,
        "fraction": pn.FRACTION,
        "targets_requested": len(targets),
        "panel_targets": len(panel_targets),
        "eval_targets": len(eval_targets),
        "n_pairs": int(len(pairs)),
        "n_targets_with_pairs": int(pairs.target.nunique()),
        "n_eval_targets_with_pairs": n_eval_with_pairs,
        "eval_targets_with_pairs": sorted(set(pairs.target.unique()) & set(eval_targets)),
        "outputs": {"pairs": str(pairs_path), "tss": str(out / "gencode_tss.csv")},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    volume.commit()
    return manifest


@app.local_entrypoint()
def main(run_id: str):
    import json

    print(json.dumps(build_pairs.remote(run_id), indent=2))
