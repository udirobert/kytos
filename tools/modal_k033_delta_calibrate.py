"""k033 — Calibrate ST panel deltas onto the kytos consensus axis (task #7).

Reads the HVG-space deltas emitted by ``modal_k033_state_train.py::infer_deltas``
and reindexes them onto the 18,533-gene 2026 panel axis, producing gate-ready
variant npz files in the same schema as ``variant_consensus_w_ctr.npz``
(``genes``, ``targets``, ``deltas``; additive_log1p space):

  variant_k033_st_raw.npz   ST delta on covered HVG genes, zero elsewhere
                            (uncalibrated amplitude — diagnostic arm)
  variant_k033_st_norm.npz  per-target L2 rescaled to the consensus_w_ctr
                            norm on the shared support (k020 lesson: raw
                            trained-model magnitudes blew up the scorer)
  non-panel-covered targets fall back to the consensus delta unchanged.

Run:  modal run tools/modal_k033_delta_calibrate.py --ckpt best
"""

from __future__ import annotations

from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
VOLUME_ROOT = Path("/kytos-vol")
K033_ROOT = VOLUME_ROOT / "k033-state"
DATA_RUN = "gwps-20260925-01"
TRAIN_RUN = "k033-st-gwps-k562-v1"
VARIANTS_DIR = VOLUME_ROOT / "k023-consensus/extract-20260921-02-honest/variants"
GENE_NAMES = LOCAL_ROOT / "data/raw/vcc2026/gene_names.csv"

app = modal.App("kytos-k033-calibrate")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy", "pandas")
    .add_local_file(GENE_NAMES, "/root/gene_names.csv", copy=True)
)


def _reindex(matrix: "object", src_genes: list[str], axis: list[str]):
    import numpy as np

    pos = {g: i for i, g in enumerate(src_genes)}
    col = np.array([pos.get(g, -1) for g in axis])
    keep = col >= 0
    out = np.zeros((matrix.shape[0], len(axis)), dtype=np.float32)
    out[:, keep] = matrix[:, col[keep]]
    return out, keep


@app.function(
    image=image, volumes={str(VOLUME_ROOT): volume}, cpu=4, memory=8 * 1024, timeout=30 * 60
)
def calibrate(checkpoint: str = "best") -> dict:
    import json

    import numpy as np
    import pandas as pd

    axis_symbols = pd.read_csv("/root/gene_names.csv").iloc[:, 0].astype(str).tolist()

    delta_dir = K033_ROOT / "deltas" / f"{TRAIN_RUN}-{checkpoint}"
    with np.load(delta_dir / "st_deltas_hvg.npz", allow_pickle=False) as d:
        st_targets = [str(t) for t in d["targets"]]
        hvg_genes = [str(g) for g in d["hvg_genes"]]
        st_delta = d["delta"].astype(np.float32)

    with np.load(VARIANTS_DIR / "variant_consensus_w_ctr.npz", allow_pickle=False) as d:
        cons_genes = [str(g) for g in d["genes"]]
        cons_targets = [str(t) for t in d["targets"]]
        cons = (
            d["deltas"].astype(np.float32)
            if "deltas" in d.files
            else d["delta_k562"].astype(np.float32)
        )
    cons_axis, cons_keep = _reindex(cons, cons_genes, axis_symbols)
    cons_by_target = dict(zip(cons_targets, cons_axis))

    st_axis, st_keep = _reindex(st_delta, hvg_genes, axis_symbols)

    rows_raw, rows_norm = [], []
    norms = []
    for i, tgt in enumerate(st_targets):
        raw = st_axis[i]
        base = cons_by_target.get(tgt, np.zeros(len(axis_symbols), np.float32))
        n_st = float(np.linalg.norm(raw[st_keep]))
        n_co = float(np.linalg.norm(base[st_keep & cons_keep]))
        scale = n_co / max(n_st, 1e-9)
        norms.append((tgt, n_st, n_co, scale))
        rows_raw.append(raw)
        rows_norm.append(raw * scale)

    out_dir = K033_ROOT / f"calib-{TRAIN_RUN}-{checkpoint}"
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_dir / "variant_k033_st_raw.npz",
        genes=np.asarray(axis_symbols),
        targets=np.asarray(st_targets),
        deltas=np.stack(rows_raw),
    )
    np.savez_compressed(
        out_dir / "variant_k033_st_norm.npz",
        genes=np.asarray(axis_symbols),
        targets=np.asarray(st_targets),
        deltas=np.stack(rows_norm),
    )
    med_scale = float(np.median([s for _, _, _, s in norms]))
    report = {
        "train_run": TRAIN_RUN,
        "checkpoint": checkpoint,
        "n_targets": len(st_targets),
        "axis_genes": len(axis_symbols),
        "hvg_on_axis": int(st_keep.sum()),
        "median_norm_st": float(np.median([n for _, n, _, _ in norms])),
        "median_norm_consensus_hvg": float(np.median([c for _, _, c, _ in norms])),
        "median_scale": med_scale,
        "per_target": [
            {"target": t, "norm_st": a, "norm_cons": b, "scale": c} for t, a, b, c in norms
        ],
    }
    (out_dir / "calibration_report.json").write_text(json.dumps(report, indent=2))
    volume.commit()
    print({k: v for k, v in report.items() if k != "per_target"}, flush=True)
    return {"out_dir": str(out_dir), "median_scale": med_scale}


@app.local_entrypoint()
def main(ckpt: str = "best") -> None:
    print(calibrate.remote(checkpoint=ckpt), flush=True)
