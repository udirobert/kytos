"""k033 — Probe Arc State ST-HVG-Replogle checkpoints for panel usability.

Downloads only the small metadata files (no .ckpt) for the fewshot and
zeroshot Jurkat/RPE1/K562/HepG2 runs and reports:
  * perturbation-gene coverage of the 300-target 2026 panel and the 47
    gate-B targets (from ``pert_onehot_map.pt`` keys),
  * the checkpoint HVG gene list (``var_dims.pkl``) intersected with the
    panel gene universe,
  * the config contract needed by ``state tx infer``.

Metadata files are pickled objects from the organizers' Hugging Face repo;
``torch.load`` prefers ``weights_only=True`` and only falls back to object
loading for these pinned Arc artifacts.

Writes ``/kytos-vol/k033-state/probe-20260925-01/probe_report.json``.

Run:  modal run tools/modal_k033_state_probe.py
"""

from __future__ import annotations

from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
HF_REPO = "arcinstitute/ST-HVG-Replogle"
EXTRA_REPOS = ("arcinstitute/st-x-replogle-full", "arcinstitute/st-se-replogle-full")
LINES = ("jurkat", "rpe1", "k562", "hepg2")
OUT_DIR = VOLUME_ROOT / "k033-state/probe-20260925-01"

app = modal.App("kytos-k033-state-probe")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "huggingface_hub", "numpy", "pandas", "pyyaml")
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/pert_counts.csv",
        str(REMOTE_ROOT / "data/raw/vcc2026/pert_counts.csv"),
        copy=True,
    )
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/gene_names.csv",
        str(REMOTE_ROOT / "data/raw/vcc2026/gene_names.csv"),
        copy=True,
    )
)


def _load_obj(path):
    import torch

    try:
        return torch.load(path, weights_only=True)
    except Exception:
        # Arc-published onehot maps pickle small Python objects.
        return torch.load(path, weights_only=False)


@app.function(
    image=image,
    cpu=2.0,
    memory=8192,
    timeout=3600,
    retries=1,
    volumes={str(VOLUME_ROOT): volume},
)
def probe() -> dict:
    import json
    import pickle

    import numpy as np
    import pandas as pd
    import yaml
    from huggingface_hub import hf_hub_download

    panel = pd.read_csv(REMOTE_ROOT / "data/raw/vcc2026/pert_counts.csv")["target_gene"].astype(str)
    panel = sorted(set(panel) - {"non-targeting"})
    panel_set = set(panel)
    universe = set(
        pd.read_csv(REMOTE_ROOT / "data/raw/vcc2026/gene_names.csv").iloc[:, 0].astype(str)
    )
    with np.load(VOLUME_ROOT / "paired-transfer/paired_transfer_train.npz") as d:
        gate_set = set(d["paired_targets"].astype(str).tolist())

    report = {"panel_n": len(panel), "gate_n": len(gate_set), "checkpoints": {}}
    targets = [(HF_REPO, f"{mode}/{line}") for mode in ("fewshot", "zeroshot") for line in LINES]
    targets += [(repo, f"{line}_0.99") for repo in EXTRA_REPOS for line in LINES]
    for repo, base in targets:
        key = f"{repo.split('/')[1]}:{base}"
        entry: dict = {}
        try:
            mapping = _load_obj(hf_hub_download(repo, f"{base}/pert_onehot_map.pt"))
            if isinstance(mapping, dict):
                genes = [str(k) for k in mapping.keys()]
            elif hasattr(mapping, "classes_"):
                genes = [str(c) for c in mapping.classes_]
            else:
                obj = vars(mapping) if hasattr(mapping, "__dict__") else {}
                genes = [
                    str(c)
                    for v in obj.values()
                    if hasattr(v, "__iter__")
                    for c in (v.tolist() if hasattr(v, "tolist") else v)
                ] or [f"unparsed:{type(mapping).__name__}"]
            entry["pert_genes"] = len(genes)
            entry["sample_genes"] = genes[:12]
            entry["panel_cov"] = len(panel_set & set(genes))
            entry["gate_cov"] = len(gate_set & set(genes))

            cfg = yaml.safe_load(open(hf_hub_download(repo, f"{base}/config.yaml")))
            entry["cfg_model"] = cfg.get("model", {})
            entry["cfg_data"] = cfg.get("data", {})

            with open(hf_hub_download(repo, f"{base}/var_dims.pkl"), "rb") as fh:
                dims = pickle.load(fh)
            hvg = None
            if isinstance(dims, dict):
                entry["var_dims_keys"] = {
                    k: len(v) if hasattr(v, "__len__") else str(v) for k, v in dims.items()
                }
                for k, v in dims.items():
                    if not hasattr(v, "__iter__"):
                        continue
                    vals = list(v.keys() if isinstance(v, dict) else v)
                    if vals and all(isinstance(x, str) for x in vals[:5]):
                        hvg = {str(x) for x in vals}
                        entry["hvg_key"] = k
                        break
            if hvg:
                entry["hvg_n"] = len(hvg)
                entry["hvg_panel_cov"] = len(panel_set & hvg)
                entry["hvg_in_universe"] = len(hvg & universe)
            entry["status"] = "ok"
        except Exception as exc:  # noqa: BLE001 — report per-entry failure
            entry["status"] = f"error: {type(exc).__name__}: {exc}"
        report["checkpoints"][key] = entry
        print(
            f"{key}: {entry['status']} pert={entry.get('pert_genes')} "
            f"panel_cov={entry.get('panel_cov')} hvg_panel={entry.get('hvg_panel_cov')}",
            flush=True,
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "probe_report.json").write_text(json.dumps(report, indent=2, default=str))
    volume.commit()
    return report


@app.local_entrypoint()
def main():
    import json

    print(json.dumps(probe.remote(), indent=2, default=str))
