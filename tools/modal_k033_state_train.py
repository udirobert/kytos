"""k033 — Train a State Transition (ST) model on Replogle genome-wide K562.

Why: the published Arc State checkpoints carry a 2,024-target essential-gene
onehot vocab (probe 2026-09-25: panel_cov=0 on all 24 checkpoints), so none of
them can emit deltas for the 2026 panel. The 2026 panel IS covered (272/300)
by the Replogle genome-wide Perturb-seq K562 single-cell bundle (figshare
35775507 — same source + access pattern already proven by k032). This tool
trains a state24m-class ST model with the full ~9.8k-target onehot vocab on
Modal GPU, then runs `state tx infer` to emit per-panel-target log1p deltas.

Stages (idempotent, resume via existing artifacts):
  prepare  stream figshare -> cell-load dataset dir of log1p(normalize 1e4)
           h5ad parts with global 6k-HVG obsm['X_hvg'] + control adata + splits
  train    `state tx train` mirroring the published st-x-replogle-full
           backbone (hidden 328, cell_set_len 64, energy loss, batch encoder)
           with genome-wide vocab; periodic checkpoint sync to the volume
  infer    `state tx infer --tsv` clones controls onto the covered panel
           targets and writes st_deltas_hvg.npz for tasks k033-#7/#8

Run:
  modal run --detach tools/modal_k033_state_train.py --stage prepare
  modal run --detach tools/modal_k033_state_train.py --stage train
  modal run tools/modal_k033_state_train.py --stage infer
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
VOLUME_ROOT = Path("/kytos-vol")
K033_ROOT = VOLUME_ROOT / "k033-state"
DATA_RUN = "gwps-20260925-01"
META_DIR = K033_ROOT / DATA_RUN
DATASET_DIR = META_DIR / "dataset"
RUNS_DIR = K033_ROOT / "runs"
DELTA_ROOT = K033_ROOT / "deltas"

REPLOGLE_URL = "https://ndownloader.figshare.com/files/35775507"
PANEL_COUNTS = LOCAL_ROOT / "data/raw/vcc2026/pert_counts.csv"

N_HVG = 6000
ROW_CHUNK = 100_000  # cells per output part file
HVG_CHUNK = 20_000  # contiguous read size for the HVG sample pass
HVG_STRIDE = 10  # sample every 10th chunk (~200k cells)
N_CTRLS = 40_000  # control cells stored for inference
CTRLS_PER_PART = 3_000  # reservoir budget of NTC rows kept per part
CELLS_PER_PERT = 400  # virtual clone budget at infer time
NTC_LABEL = "non-targeting"
CELL_LINE = "K562"
SEED = 42

TRAIN_NAME = "k033-st-gwps-k562-v1"
MAX_STEPS = 40_000
BATCH_SIZE = 8  # cell-sets per step (x cell_set_len 64)
VAL_FREQ = 2_500

app = modal.App("kytos-k033-state")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

_prep_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "scanpy==1.11.2",
        "anndata>=0.11.4",
        "h5py==3.13.0",
        "fsspec",
        "requests",
        "numpy",
        "pandas",
        "scipy",
    )
    .add_local_file(PANEL_COUNTS, "/root/pert_counts.csv", copy=True)
)

_train_image = (
    modal.Image.debian_slim(python_version="3.12")
    # PyPI ceiling is 0.11.1; repo-main 0.11.3 only adds a raw-counts model
    # option unused here (diffed train/infer/preprocess CLIs are identical).
    .pip_install("arc-state==0.11.1", "cell-load==0.10.4")
)


def _open_remote(url: str, retries: int = 6):
    """Reopen the fsspec stream + h5 handle (long HTTP reads flake)."""
    import fsspec
    import h5py

    last: Exception | None = None
    for _ in range(retries):
        try:
            fh = fsspec.open(url, "rb").open()
            return fh, h5py.File(fh, "r")
        except Exception as exc:  # noqa: BLE001 — retry any open failure
            last = exc
            time.sleep(5)
    raise RuntimeError(f"cannot open {url}: {last}")


def _read_rows(url: str, r0: int, r1: int, retries: int = 6):
    import numpy as np

    last: Exception | None = None
    for _ in range(retries):
        fh, h5 = _open_remote(url)
        try:
            return np.asarray(h5["X"][r0:r1], dtype=np.float32)
        except Exception as exc:  # noqa: BLE001 — mid-stream drop, reopen
            last = exc
            try:
                fh.close()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(5)
    raise RuntimeError(f"cannot read rows {r0}:{r1}: {last}")


@app.function(
    image=_prep_image,
    volumes={str(VOLUME_ROOT): volume},
    cpu=16,
    memory=128 * 1024,
    timeout=10 * 3600,
    retries=0,
)
def prepare() -> dict:
    import anndata as ad
    import numpy as np
    import pandas as pd
    import scanpy as sc
    from scipy import sparse

    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    # ---- remote metadata ----
    fh, h5 = _open_remote(REPLOGLE_URL)
    gene_cats = h5["obs/__categories/gene"].asstr()[:]
    var_names = np.asarray(
        h5["var/__categories/gene_name"].asstr()[:][h5["var/gene_name"][:]]
    ).astype(str)
    n_cells, n_genes = h5["X"].shape
    gene_codes = np.asarray(h5["obs/gene"][:])
    gem = np.asarray(h5["obs/gem_group"][:]).astype(str)
    fh.close()
    genes_full = np.asarray(gene_cats)[gene_codes]
    counts = pd.Series(genes_full).value_counts()
    print(f"remote: {n_cells} cells x {n_genes} genes, {len(gene_cats)} perts", flush=True)

    panel = sorted(pd.read_csv("/root/pert_counts.csv").iloc[:, 0].astype(str).unique())
    covered = [t for t in panel if t in counts.index and t != NTC_LABEL]
    uncovered = [t for t in panel if t not in covered]
    print(f"panel coverage: {len(covered)}/{len(panel)}", flush=True)

    # ---- pass A: global HVG list from a strided sample ----
    hvg_path = META_DIR / "hvgs.json"
    if hvg_path.exists():
        hvg_genes = json.loads(hvg_path.read_text())["genes"]
        print(f"hvg cached: {len(hvg_genes)}", flush=True)
    else:
        samples = []
        for w in range(HVG_STRIDE):
            r0 = min(w * (n_cells // HVG_STRIDE), max(n_cells - HVG_CHUNK, 0))
            samples.append(_read_rows(REPLOGLE_URL, r0, r0 + HVG_CHUNK))
        sample = np.concatenate(samples)
        del samples
        print(f"hvg sample: {sample.shape}", flush=True)
        s_ad = ad.AnnData(
            X=sample,
            obs=pd.DataFrame(index=pd.Index([f"s{i}" for i in range(sample.shape[0])])),
            var=pd.DataFrame(index=pd.Index(var_names)),
        )
        sc.pp.normalize_total(s_ad, target_sum=1e4)
        sc.pp.log1p(s_ad)
        sc.pp.highly_variable_genes(s_ad, n_top_genes=N_HVG, flavor="seurat")
        hvg_genes = s_ad.var_names[s_ad.var["highly_variable"].to_numpy()].tolist()
        hvg_path.write_text(
            json.dumps({"genes": hvg_genes, "seed": SEED, "n_sampled": int(sample.shape[0])})
        )
        volume.commit()
        print(f"hvg selected: {len(hvg_genes)}", flush=True)

    hvg_mask = np.isin(var_names, np.asarray(hvg_genes))
    hvg_pos = np.flatnonzero(hvg_mask)
    n_parts = int(np.ceil(n_cells / ROW_CHUNK))

    # ---- pass B: write cell-load parts (resume = skip existing files) ----
    rng = np.random.default_rng(SEED)
    for part in range(n_parts):
        out_path = DATASET_DIR / f"part_{part:03d}.h5ad"
        r0, r1 = part * ROW_CHUNK, min((part + 1) * ROW_CHUNK, n_cells)
        if out_path.exists():
            print(f"part {part}: exists", flush=True)
            continue
        block = _read_rows(REPLOGLE_URL, r0, r1)
        chunk_gene = genes_full[r0:r1]
        keep = np.flatnonzero(
            (chunk_gene == NTC_LABEL)
            & (rng.random(r1 - r0) < (2.0 * CTRLS_PER_PART) / max(r1 - r0, 1))
        )[:CTRLS_PER_PART]
        ctrl_npz = META_DIR / f"ctrl_pool_{part:02d}.npz"
        if not ctrl_npz.exists() and keep.size:
            np.savez_compressed(ctrl_npz, rows=block[keep])
        a = ad.AnnData(
            X=block,
            obs=pd.DataFrame(
                {
                    "gene": pd.Categorical(chunk_gene),
                    "gem_group": pd.Categorical(gem[r0:r1]),
                    "cell_line": pd.Categorical([CELL_LINE] * (r1 - r0)),
                },
                index=[f"k562_{i}" for i in range(r0, r1)],
            ),
            var=pd.DataFrame(index=pd.Index(var_names)),
        )
        sc.pp.normalize_total(a, target_sum=1e4)
        sc.pp.log1p(a)
        a.var["highly_variable"] = hvg_mask
        a.obsm["X_hvg"] = np.ascontiguousarray(a.X[:, hvg_pos], dtype=np.float32)
        a.X = sparse.csr_matrix(a.X.astype(np.float32))
        tmp = Path("/tmp") / out_path.name
        a.write_h5ad(tmp, compression="gzip")
        _copy_to_volume(tmp, out_path)
        print(f"part {part}: wrote {r1 - r0} cells ({tmp.stat().st_size / 1e9:.2f} GB)", flush=True)
    volume.commit()

    # ---- control adata for inference (from the per-part reservoirs) ----
    ctrl_path = META_DIR / "infer_controls.h5ad"
    if not ctrl_path.exists():
        pools = [np.load(p)["rows"] for p in sorted(META_DIR.glob("ctrl_pool_*.npz"))]
        ctrl = np.concatenate(pools)[:N_CTRLS]
        c = ad.AnnData(
            X=ctrl,
            obs=pd.DataFrame(
                {
                    "gene": pd.Categorical([NTC_LABEL] * ctrl.shape[0]),
                    "gem_group": pd.Categorical(["0"] * ctrl.shape[0]),
                    "cell_line": pd.Categorical([CELL_LINE] * ctrl.shape[0]),
                },
                index=[f"ctrl_{i}" for i in range(ctrl.shape[0])],
            ),
            var=pd.DataFrame(index=pd.Index(var_names)),
        )
        sc.pp.normalize_total(c, target_sum=1e4)
        sc.pp.log1p(c)
        c.var["highly_variable"] = hvg_mask
        c.obsm["X_hvg"] = np.ascontiguousarray(c.X[:, hvg_pos], dtype=np.float32)
        c.X = sparse.csr_matrix(c.X.astype(np.float32))
        tmp = Path("/tmp/controls.h5ad")
        c.write_h5ad(tmp, compression="gzip")
        _copy_to_volume(tmp, ctrl_path)
        print(f"controls: {c.shape}", flush=True)

    # ---- val/test holdout (never panel targets) ----
    splits_path = META_DIR / "splits.json"
    if not splits_path.exists():
        panel_set = set(panel)
        pool = sorted(
            t for t, c_ in counts.items() if t != NTC_LABEL and c_ >= 600 and t not in panel_set
        )
        pick = rng.choice(len(pool), size=min(48, len(pool)), replace=False)
        chosen = sorted(pool[int(i)] for i in pick)
        splits = {"val": chosen[: len(chosen) // 2], "test": chosen[len(chosen) // 2 :]}
        splits_path.write_text(json.dumps(splits))
    else:
        splits = json.loads(splits_path.read_text())

    meta = {
        "url": REPLOGLE_URL,
        "n_cells": int(n_cells),
        "n_genes": int(n_genes),
        "n_perts": int(len(gene_cats)),
        "n_hvg": len(hvg_genes),
        "panel_covered": covered,
        "panel_uncovered": uncovered,
        "splits": splits,
    }
    (META_DIR / "meta.json").write_text(json.dumps(meta, default=str))
    volume.commit()
    print("prepare complete", flush=True)
    return {"parts": n_parts, "covered": len(covered), "hvg": len(hvg_genes)}


def _copy_to_volume(src: Path, dst: Path) -> None:
    import shutil

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        shutil.copyfileobj(fin, fout, length=32 * 2**20)
    volume.commit()


def _run_argv(argv: list[str]) -> None:
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    for line in proc.stdout:  # type: ignore[union-attr]
        print(line.rstrip(), flush=True)
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"command failed ({rc}): {' '.join(argv[:4])} ...")


def _start_run_sync(local_run: Path, vol_run: Path, stop: threading.Event):
    synced: dict[str, float] = {}
    seen_size: dict[str, int] = {}

    def loop() -> None:
        while True:
            try:
                vol_run.mkdir(parents=True, exist_ok=True)
                for f in sorted(local_run.rglob("*")):
                    if not f.is_file():
                        continue
                    size = f.stat().st_size
                    if f.suffix != ".ckpt" and size > 50 * 2**20:
                        continue
                    key = str(f.relative_to(local_run))
                    # require two consecutive identical sizes before copying:
                    # lightning rewrites last/best ckpts in place
                    if f.suffix == ".ckpt" and seen_size.get(key) != size:
                        seen_size[key] = size
                        continue
                    mtime = f.stat().st_mtime
                    if synced.get(key) == mtime:
                        continue
                    _copy_to_volume(f, vol_run / key)
                    synced[key] = mtime
                    print(f"[sync] {key} ({size / 1e6:.0f} MB)", flush=True)
            except Exception as exc:  # noqa: BLE001 — keep training alive
                print(f"[sync] error: {exc}", flush=True)
            if stop.is_set():
                return
            time.sleep(600)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


@app.function(
    image=_train_image,
    volumes={str(VOLUME_ROOT): volume},
    gpu="L4",
    cpu=8,
    memory=32 * 1024,
    ephemeral_disk=524288,  # Modal GPU floor (512 GiB)
    timeout=22 * 3600,
    retries=0,
)
def train(run_name: str = TRAIN_NAME, max_steps: int = MAX_STEPS) -> str:
    import shutil
    import time as _t

    local = Path("/root/work")
    local.mkdir(parents=True, exist_ok=True)
    data_local = local / "dataset"
    if not (data_local / ".done").exists():
        t0 = _t.time()
        data_local.mkdir(parents=True, exist_ok=True)
        for f in sorted(DATASET_DIR.glob("*.h5ad")):
            shutil.copy2(f, data_local / f.name)
        (data_local / ".done").touch()
        print(f"[copy] dataset done in {_t.time() - t0:.0f}s", flush=True)

    run_local = local / "runs" / run_name
    run_vol = RUNS_DIR / run_name
    if run_vol.exists() and not run_local.exists():
        run_local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(run_vol, run_local)
        print("[resume] restored run dir from volume", flush=True)
    run_local.mkdir(parents=True, exist_ok=True)

    splits = json.loads((META_DIR / "splits.json").read_text())
    toml_path = local / "replogle_k562.toml"
    toml_path.write_text(
        "[datasets]\n"
        f'replogle = "{data_local}"\n\n'
        "[training]\n"
        'replogle = "train"\n\n'
        "[zeroshot]\n\n"
        f'[fewshot."replogle.{CELL_LINE}"]\n'
        f"val = {json.dumps(splits['val'])}\n"
        f"test = {json.dumps(splits['test'])}\n"
    )

    overrides = [
        f"data.kwargs.toml_config_path={toml_path}",
        "data.kwargs.embed_key=X_hvg",
        "data.kwargs.output_space=gene",
        "data.kwargs.pert_col=gene",
        "data.kwargs.batch_col=gem_group",
        "data.kwargs.cell_type_key=cell_line",
        f"data.kwargs.control_pert={NTC_LABEL}",
        "data.kwargs.num_workers=6",
        "data.kwargs.val_subsample_fraction=0.1",
        "model=state",
        "model.kwargs.cell_set_len=64",
        "model.kwargs.hidden_dim=328",
        "model.kwargs.batch_encoder=true",
        f"training.batch_size={BATCH_SIZE}",
        f"training.max_steps={max_steps}",
        f"training.val_freq={VAL_FREQ}",
        f"output_dir={run_local.parent}",
        f"name={run_name}",
        "use_wandb=false",
    ]
    stop = threading.Event()
    sync_thread = _start_run_sync(run_local, run_vol, stop)
    try:
        _run_argv(["state", "tx", "train", *overrides])
    finally:
        stop.set()
        sync_thread.join(timeout=3600)
        run_vol.mkdir(parents=True, exist_ok=True)
        for f in sorted(run_local.rglob("*")):
            if f.is_file() and (f.suffix == ".ckpt" or f.stat().st_size <= 200 * 2**20):
                _copy_to_volume(f, run_vol / f.relative_to(run_local))
    print("train complete", flush=True)
    return str(run_vol)


@app.function(
    image=_train_image,
    volumes={str(VOLUME_ROOT): volume},
    gpu="L4",
    cpu=8,
    memory=32 * 1024,
    ephemeral_disk=524288,  # Modal GPU floor (512 GiB)
    timeout=6 * 3600,
    retries=0,
)
def infer_deltas(run_name: str = TRAIN_NAME, checkpoint: str = "best") -> dict:
    import anndata as ad
    import numpy as np
    import pandas as pd
    import shutil

    local = Path("/root/work")
    local.mkdir(parents=True, exist_ok=True)
    run_local = local / "runs" / run_name
    run_vol = RUNS_DIR / run_name
    if not run_local.exists():
        run_local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(run_vol, run_local)
    ckpt = run_local / "checkpoints" / f"{checkpoint}.ckpt"
    if not ckpt.exists():
        ckpt = run_local / "checkpoints" / "final.ckpt"
    assert ckpt.exists(), f"no checkpoint '{checkpoint}' under {run_vol}/checkpoints"

    ctrl_local = local / "controls.h5ad"
    if not ctrl_local.exists():
        shutil.copy2(META_DIR / "infer_controls.h5ad", ctrl_local)
    meta = json.loads((META_DIR / "meta.json").read_text())
    covered = meta["panel_covered"]

    tsv = local / "panel.tsv"
    pd.DataFrame({"perturbation": covered, "num_cells": [CELLS_PER_PERT] * len(covered)}).to_csv(
        tsv, sep="\t", index=False
    )

    sim_local = local / "sim.h5ad"
    _run_argv(
        [
            "state",
            "tx",
            "infer",
            "--model-dir",
            str(run_local),
            "--checkpoint",
            str(ckpt),
            "--adata",
            str(ctrl_local),
            "--pert-col",
            "gene",
            "--embed-key",
            "X_hvg",
            "--output",
            str(sim_local),
            "--tsv",
            str(tsv),
            "--seed",
            str(SEED),
            "--quiet",
        ]
    )

    out = ad.read_h5ad(sim_local)
    # infer overwrites obsm['X_hvg'] with predictions; X keeps real controls.
    preds = np.asarray(out.obsm["X_hvg"], dtype=np.float32)
    labels = out.obs["gene"].astype(str).to_numpy()
    n_orig = out.shape[0] - (len(covered) * CELLS_PER_PERT)
    ctrl_pred_mean = preds[:n_orig].mean(axis=0)  # real control rows simulated as NTC

    hvg_genes = json.loads((META_DIR / "hvgs.json").read_text())["genes"]
    hvg_pos = np.flatnonzero(np.isin(np.asarray(out.var_names).astype(str), np.asarray(hvg_genes)))
    ctrl_real_mean = np.asarray(
        out.X[:n_orig][:, hvg_pos].toarray()
        if hasattr(out.X[:n_orig], "toarray")
        else np.asarray(out.X[:n_orig])[:, hvg_pos],
        dtype=np.float32,
    ).mean(axis=0)

    rows, deltas = [], []
    for tgt in covered:
        m = labels == tgt
        if not m.any():
            continue
        rows.append(tgt)
        deltas.append(preds[m].mean(axis=0) - ctrl_pred_mean)
    delta = np.stack(deltas).astype(np.float32)

    out_dir = DELTA_ROOT / f"{run_name}-{checkpoint}"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "st_deltas_hvg.npz", "wb") as fh:
        np.savez_compressed(
            fh,
            targets=np.asarray(rows),
            hvg_genes=np.asarray(hvg_genes),
            delta=delta,
            ctrl_pred_mean=ctrl_pred_mean.astype(np.float32),
            ctrl_real_mean_hvg=ctrl_real_mean,
        )
    report = {
        "run_name": run_name,
        "checkpoint": checkpoint,
        "n_targets": len(rows),
        "cells_per_pert": CELLS_PER_PERT,
        "delta_norm_median": float(np.median(np.linalg.norm(delta, axis=1))),
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    volume.commit()
    print(f"infer complete: {report}", flush=True)
    return report


@app.local_entrypoint()
def main(
    stage: str = "all",
    run_name: str = TRAIN_NAME,
    max_steps: int = MAX_STEPS,
    checkpoint: str = "best",
) -> None:
    if stage in ("all", "prepare"):
        print(prepare.remote(), flush=True)
    if stage in ("all", "train"):
        print(train.remote(run_name=run_name, max_steps=max_steps), flush=True)
    if stage in ("all", "infer"):
        print(infer_deltas.remote(run_name=run_name, checkpoint=checkpoint), flush=True)
