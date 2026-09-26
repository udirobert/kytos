"""Extract basal (control) expression profiles for context-lineage weighting (k030).

Why this job exists
-------------------
The consensus deltas built in k023/k029 mix four source lineages with static
weights ({k562:2, hct116:1, hek293t:1, cd4:1}) applied identically to every
eval context. The k012 lineage report showed contexts A/B/C resemble
different reference lines on discriminative genes. This job extracts the
basal (unperturbed control) expression profile of each *delta source* and of
each *eval context* so a leak-free similarity score can weight each source
per context. Basal profiles use only control cells -- never held-out
perturbation responses -- so the weights are fit entirely on source/input
data.

Basal sources
-------------
- ``hct116`` / ``hek293t``: X-Atlas Orion Non-Targeting cells, mean
  log1p(raw counts) on the panel axis (same streaming scan as k023).
- ``k562``: Replogle GWPS bulk non-targeting mean (refs/k562_bulk.h5ad on
  the volume).
- ``cd4``: Marson 2025 DE_stats ``layers/baseMean`` -- DESeq2 mean
  normalized counts per contrast; median over Rest-condition contrasts is a
  resting-CD4 basal proxy (units differ from log1p cell means -- recorded).
- Contexts ``A``/``B``/``C``: 2026 controls bundle (all rows are controls).
- ``eval``: 2025 Atlas validation non-targeting rows -- the Gate B eval
  context.

Outputs (on the Modal volume under ``k030-ctxlineage/<run_id>/``)
-----------------------------------------------------------------
``basal_<name>.npz``  -- genes, basal (G,) float32, n_cells/units metadata
``ctxlineage_report.json`` -- similarity matrix (pearson/spearman on all /
nonzero / top-2000 context-discriminative genes) + derived weight vectors.

Run:
  modal run -d tools/modal_ctxlineage_basal.py --run-id basal-YYYYMMDD-NN
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
OUT_DIR = VOLUME_ROOT / "k030-ctxlineage"
PANEL_GENES = REMOTE_ROOT / "data/vcc2026/gene_names.csv"
REFS_DIR = VOLUME_ROOT / "refs"
ATLAS_PATH = VOLUME_ROOT / "atlas/adata_Validation.h5ad"

HF_XATLAS = "hf://datasets/slaf-project/X-Atlas-Orion/data/{}"
XATLAS_ARMS = {"hct116": "HCT116", "hek293t": "HEK293T"}
XATLAS_CONTROL = "Non-Targeting"
CONTROL_CAP_PER_SAMPLE = 150  # match k023 control sampling
SCAN_BATCH_ROWS = 8_000_000
SCAN_MAX_RETRIES = 30
SCAN_CKPT_EVERY = 250  # batches (~2B rows at 8M/batch)

CD4_URL = (
    "https://genome-scale-tcell-perturb-seq.s3.amazonaws.com/marson2025_data/GWCD4i.DE_stats.h5ad"
)
TOP_DISC = 2000
BASE_WEIGHTS = {"k562": 2.0, "hct116": 1.0, "hek293t": 1.0, "cd4": 1.0}

app = modal.App("kytos-k030-ctxlineage")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

scan_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "scipy==1.15.3",
        "pandas==2.2.3",
        "pylance==12.0.0",
        "h5py==3.13.0",
        "anndata==0.11.4",
        "requests==2.32.4",
    )
    .add_local_file(
        LOCAL_ROOT / "tools/consensus_deltas.py",
        str(REMOTE_ROOT / "tools/consensus_deltas.py"),
        copy=True,
    )
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/gene_names.csv",
        str(PANEL_GENES),
        copy=True,
    )
)

assemble_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "unzip")
    .pip_install(
        "numpy==2.2.6",
        "scipy==1.15.3",
        "pandas==2.2.3",
        "h5py==3.13.0",
        "anndata==0.11.4",
        "requests==2.32.4",
        "fsspec",
        "vcc-cli",
    )
    .add_local_file(
        LOCAL_ROOT / "tools/perturbation_priors.py",
        str(REMOTE_ROOT / "tools/perturbation_priors.py"),
        copy=True,
    )
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/gene_names.csv",
        str(PANEL_GENES),
        copy=True,
    )
)


def _check_run_id(run_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Use a new alphanumeric run ID (hyphens/underscores allowed)")


@app.function(
    image=scan_image,
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=10800,
    startup_timeout=300,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
    secrets=[modal.Secret.from_name("kytos-hf")],
)
def xatlas_basal(source: str, run_id: str) -> dict:
    """Mean log1p over Non-Targeting cells for one X-Atlas arm, on panel axis."""
    import sys
    import time

    import numpy as np
    import pandas as pd

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd

    _check_run_id(run_id)
    if source not in XATLAS_ARMS:
        raise ValueError(f"source must be one of {sorted(XATLAS_ARMS)}")
    out = OUT_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"basal_{source}"
    if (stem.parent / (stem.name + ".npz")).exists():
        return {"status": "exists", "npz": str(stem) + ".npz"}

    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()

    import lance

    t0 = time.time()
    base = HF_XATLAS.format(XATLAS_ARMS[source])
    expression = lance.dataset(f"{base}/expression.lance")
    total_rows = expression.count_rows()

    genes_tbl = (
        lance.dataset(f"{base}/genes.lance")
        .scanner(columns=["gene_id", "gene_integer_id"])
        .to_table()
        .to_pandas()
        .sort_values("gene_integer_id")
    )
    positions, missing_genes = cd.map_gene_axis(
        genes_tbl["gene_id"].astype(str).tolist(), panel_genes
    )
    gene_to_panel = np.full(len(genes_tbl), -1, dtype=np.int32)
    gene_to_panel[positions[positions >= 0]] = np.flatnonzero(positions >= 0)

    all_cells = (
        lance.dataset(f"{base}/cells.lance")
        .scanner(columns=["cell_integer_id", "sample", "gene_target"])
        .to_table()
        .to_pandas()
    )
    ctrl = all_cells[all_cells["gene_target"] == XATLAS_CONTROL]
    n_ctrl_total = len(ctrl)
    ctrl = ctrl.groupby("sample", sort=False).head(CONTROL_CAP_PER_SAMPLE)
    max_cid = int(all_cells["cell_integer_id"].max())
    keep = np.zeros(max_cid + 1, dtype=bool)
    keep[ctrl["cell_integer_id"].to_numpy()] = True
    n_cells = int(keep.sum())
    n_samples = int(ctrl["sample"].nunique())

    sums = np.zeros(len(panel_genes), dtype=np.float64)
    scanned = kept_rows = 0
    ckpt_path = out / f"basal_{source}.ckpt.npz"
    if ckpt_path.exists():
        with np.load(ckpt_path, allow_pickle=False) as d:
            sums = d["sums"].astype(np.float64)
            scanned = int(d["scanned"])
            kept_rows = int(d["kept_rows"])
        print(
            f"[{source}] resuming from checkpoint at row {scanned}/{total_rows}",
            flush=True,
        )
    retries = 0
    batches_since_ckpt = 0
    while True:
        scanner = expression.scanner(batch_size=SCAN_BATCH_ROWS, offset=scanned)
        try:
            for batch in scanner.to_batches():
                if not batch.num_rows:
                    continue
                retries = 0  # per-burst budget: progress resets the counter
                cid = batch.column("cell_integer_id").to_numpy()
                gid = batch.column("gene_integer_id").to_numpy()
                val = batch.column("value").to_numpy()
                in_range = cid < len(keep)
                ckeep = np.where(in_range, keep[np.clip(cid, 0, len(keep) - 1)], False)
                pos = np.where(
                    gid < len(gene_to_panel),
                    gene_to_panel[np.clip(gid, 0, len(gene_to_panel) - 1)],
                    -1,
                )
                sel = ckeep & (pos >= 0)
                if sel.any():
                    np.add.at(sums, pos[sel], np.log1p(val[sel].astype(np.float64)))
                kept_rows += int(sel.sum())
                scanned += batch.num_rows
                batches_since_ckpt += 1
                if batches_since_ckpt >= SCAN_CKPT_EVERY:
                    np.savez_compressed(
                        str(ckpt_path),
                        sums=sums,
                        scanned=np.int64(scanned),
                        kept_rows=np.int64(kept_rows),
                    )
                    volume.commit()
                    batches_since_ckpt = 0
                    print(
                        f"[{source}] checkpoint at {scanned}/{total_rows}",
                        flush=True,
                    )
                if scanned % (SCAN_BATCH_ROWS * 50) < SCAN_BATCH_ROWS:
                    print(
                        f"[{source}] scanned {scanned}/{total_rows} kept {kept_rows}",
                        flush=True,
                    )
            break
        except Exception as exc:
            retries += 1
            if retries > SCAN_MAX_RETRIES:
                raise
            wait = min(120, 10 * retries)
            print(
                f"[{source}] scan error at row {scanned} "
                f"(retry {retries}/{SCAN_MAX_RETRIES} in {wait}s): {exc}",
                flush=True,
            )
            time.sleep(wait)

    basal = (sums / max(n_cells, 1)).astype(np.float32)
    np.savez_compressed(
        str(stem) + ".npz",
        genes=np.asarray(panel_genes),
        basal=basal,
        n_cells=np.int64(n_cells),
        n_samples=np.int64(n_samples),
    )
    manifest = {
        "source": source,
        "kind": "basal_log1p_control_mean",
        "dataset": HF_XATLAS.format(XATLAS_ARMS[source]),
        "run_id": run_id,
        "control_label": XATLAS_CONTROL,
        "control_cap_per_sample": CONTROL_CAP_PER_SAMPLE,
        "ntc_cells_total": n_ctrl_total,
        "ntc_cells_used": n_cells,
        "ntc_samples": n_samples,
        "expression_rows_scanned": int(scanned),
        "expression_rows_kept": int(kept_rows),
        "units": "mean log1p(raw counts) over Non-Targeting cells",
        "panel_genes_missing_from_source": missing_genes,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    (out / f"manifest_basal_{source}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    ckpt_path.unlink(missing_ok=True)
    volume.commit()
    return {"status": "completed", "npz": str(stem) + ".npz", "manifest": manifest}


@app.function(
    image=assemble_image,
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=10800,
    startup_timeout=300,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
    secrets=[modal.Secret.from_name("kytos-vcc")],
)
def assemble(run_id: str) -> dict:
    """All non-X-Atlas basals + context basals + similarity matrix + weights."""
    import subprocess
    import sys
    import time

    import anndata as ad
    import numpy as np
    import pandas as pd
    from scipy import sparse, stats

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import perturbation_priors as pp

    _check_run_id(run_id)
    out = OUT_DIR / run_id
    if not (out / "basal_hct116.npz").exists() or not (out / "basal_hek293t.npz").exists():
        raise FileNotFoundError(
            "basal_<hct116|hek293t>.npz missing -- run xatlas_basal for both arms first"
        )
    t0 = time.time()
    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    n_genes = len(panel_genes)
    gene_pos = {g: i for i, g in enumerate(panel_genes)}

    def map_to_panel(src_genes, src_vec):
        pos = np.array([gene_pos.get(g, -1) for g in src_genes], dtype=np.int64)
        vec = np.zeros(n_genes, dtype=np.float32)
        keep = pos >= 0
        vec[pos[keep]] = np.asarray(src_vec)[keep]
        return vec

    def save_basal(name, vec, meta):
        np.savez_compressed(
            str(out / f"basal_{name}.npz"),
            genes=np.asarray(panel_genes),
            basal=vec.astype(np.float32),
        )
        (out / f"manifest_basal_{name}.json").write_text(json.dumps(meta, indent=2) + "\n")
        print(f"[basal] {name} saved", flush=True)

    basals = {}
    for src in ("hct116", "hek293t"):
        with np.load(out / f"basal_{src}.npz", allow_pickle=False) as d:
            basals[src] = d["basal"].astype(np.float64)

    # ---- K562: Replogle bulk control mean on the volume refs ----
    _, k562_ctrl = pp.build_replogle_deltas_with_control(
        str(REFS_DIR / "k562_bulk.h5ad"), panel_genes
    )
    basals["k562"] = k562_ctrl.astype(np.float64)
    save_basal(
        "k562",
        k562_ctrl,
        {
            "source": "k562",
            "kind": "basal_log1p_control_mean",
            "dataset": "Replogle GWPS bulk (figshare 35774443), /kytos-vol/refs/k562_bulk.h5ad",
            "run_id": run_id,
            "units": "mean log1p over non-targeting pseudobulk rows",
        },
    )

    # ---- CD4: Marson DE_stats baseMean median over Rest contrasts ----
    print("[cd4] range-reading baseMean from DE_stats.h5ad ...", flush=True)
    import fsspec
    import h5py

    with fsspec.open(CD4_URL, "rb") as fh:
        h5 = h5py.File(fh, "r")
        cats = h5["obs/culture_condition/categories"].asstr()[:]
        codes = h5["obs/culture_condition/codes"][:]
        rest_idx = int(np.flatnonzero(cats == "Rest")[0])
        rest_rows = codes == rest_idx
        var_genes = h5["var/gene_name"].asstr()[:]
        base_mean = h5["layers/baseMean"][:]  # (33983, 10282) float64 ~2.8GB
    cd4_med = np.median(base_mean[rest_rows], axis=0)
    cd4_log = np.log1p(np.clip(cd4_med, 0, None))
    basals["cd4"] = map_to_panel(var_genes.tolist(), cd4_log).astype(np.float64)
    save_basal(
        "cd4",
        basals["cd4"],
        {
            "source": "cd4",
            "kind": "basal_proxy_deseq2_basemean_median",
            "dataset_url": CD4_URL,
            "run_id": run_id,
            "rest_contrasts": int(rest_rows.sum()),
            "units": "log1p(median DESeq2 baseMean over Rest contrasts) -- "
            "normalized-count proxy, NOT mean log1p over cells",
            "caveat": "baseMean averages all samples in each contrast "
            "(perturbed + control); a basal approximation only",
        },
    )
    del base_mean

    # ---- contexts A/B/C: 2026 controls bundle ----
    work = Path("/tmp/ctx")
    work.mkdir(exist_ok=True)
    subprocess.run(
        [
            "bash",
            "-c",
            "set -ex\n"
            f"cd {work}\n"
            "vcc datasets download controls\n"
            "unzip -o -q vcc_2026_controls.zip -d controls",
        ],
        check=True,
    )
    ctx_basal = {}
    for ctx in ("A", "B", "C"):
        ctrl = ad.read_h5ad(str(work / f"controls/context_{ctx}.h5ad"))
        X = ctrl.X.tocsr() if not sparse.isspmatrix_csr(ctrl.X) else ctrl.X
        mean = np.asarray(pp.log1p_sparse(X).mean(axis=0)).ravel()
        ctx_basal[ctx] = map_to_panel(ctrl.var_names.astype(str).tolist(), mean).astype(np.float64)
        save_basal(
            f"ctx{ctx}",
            ctx_basal[ctx],
            {
                "source": f"context_{ctx}",
                "kind": "basal_log1p_control_mean",
                "n_cells": int(ctrl.n_obs),
                "run_id": run_id,
                "units": "mean log1p over all cells (controls bundle)",
            },
        )

    # ---- eval context: Atlas validation non-targeting rows ----
    real = ad.read_h5ad(str(ATLAS_PATH), backed="r")
    labels = real.obs["target_gene"].astype(str)
    ctrl_idx = np.flatnonzero((labels == "non-targeting").to_numpy())
    ctrls = real[ctrl_idx].to_memory()
    real.file.close()
    X_log = pp.log1p_sparse(ctrls.X)
    eval_mean = np.asarray(X_log.mean(axis=0)).ravel()
    ctx_basal["eval"] = map_to_panel(ctrls.var_names.astype(str).tolist(), eval_mean).astype(
        np.float64
    )
    save_basal(
        "ctxeval",
        ctx_basal["eval"],
        {
            "source": "eval_atlas_validation",
            "kind": "basal_log1p_control_mean",
            "n_cells": int(ctrls.n_obs),
            "run_id": run_id,
            "units": "mean log1p over non-targeting rows",
        },
    )

    # ---- similarity matrix + weight vectors ----
    ctx_names = ["A", "B", "C", "eval"]
    src_names = ["k562", "hct116", "hek293t", "cd4"]
    ctx_mat = np.stack([ctx_basal[c] for c in ctx_names])
    disc = ctx_mat.std(axis=0).argsort()[::-1][:TOP_DISC]
    disc_mask = np.zeros(n_genes, dtype=bool)
    disc_mask[disc] = True
    all_mask = np.ones(n_genes, dtype=bool)

    def pearson(a, b, mask):
        a, b = a[mask], b[mask]
        if a.std() < 1e-8 or b.std() < 1e-8:
            return float("nan")
        return float(stats.pearsonr(a, b)[0])

    table = {}
    for c in ctx_names:
        table[c] = {}
        for s in src_names:
            both = (ctx_basal[c] > 0) & (basals[s] > 0)
            table[c][s] = {
                "pearson_all": pearson(ctx_basal[c], basals[s], all_mask),
                "pearson_nonzero": pearson(ctx_basal[c], basals[s], both),
                "spearman_nonzero": float(stats.spearmanr(ctx_basal[c][both], basals[s][both])[0])
                if both.sum() > 10
                else float("nan"),
                "pearson_discriminative": pearson(ctx_basal[c], basals[s], disc_mask),
                "n_both_nonzero": int(both.sum()),
            }
            r = table[c][s]
            print(
                f"{c:<5} {s:<9} pz={r['pearson_nonzero']:7.3f} "
                f"sp={r['spearman_nonzero']:7.3f} disc={r['pearson_discriminative']:7.3f}",
                flush=True,
            )

    # Weight rule (predeclared): w_ctx[s] = BASE_W[s] * relu(disc_sim)^p,
    # normalized to sum(BASE_W); all-nonpositive sims fall back to BASE_W.
    weights = {}
    for p in (1, 2):
        wkey = f"p{p}"
        weights[wkey] = {}
        for c in ctx_names:
            raw = {
                s: BASE_WEIGHTS[s] * max(0.0, table[c][s]["pearson_discriminative"]) ** p
                for s in src_names
            }
            if not any(v > 0 for v in raw.values()):
                raw = dict(BASE_WEIGHTS)
            total = sum(raw.values())
            weights[wkey][c] = {s: v / total * sum(BASE_WEIGHTS.values()) for s, v in raw.items()}
    weights["top"] = {
        c: {
            s: (
                sum(BASE_WEIGHTS.values())
                if s
                == max(
                    src_names,
                    key=lambda k: table[c][k]["pearson_discriminative"],
                )
                else 0.0
            )
            for s in src_names
        }
        for c in ctx_names
    }

    report = {
        "created": time.strftime("%Y-%m-%d"),
        "run_id": run_id,
        "sources": src_names,
        "contexts": ctx_names,
        "top_discriminative_genes": TOP_DISC,
        "disc_mask_over": "std across contexts A,B,C,eval on the panel axis",
        "similarity": table,
        "weights": weights,
        "weight_rule": (
            "w_ctx[s] = BASE_W[s] * relu(pearson_discriminative)^p, "
            "normalized to sum(BASE_W); all-nonpositive -> BASE_W; "
            "'top' = argmax source takes all mass"
        ),
        "base_weights": BASE_WEIGHTS,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (out / "ctxlineage_report.json").write_text(json.dumps(report, indent=2) + "\n")
    volume.commit()
    print(f"[out] {out}/ctxlineage_report.json", flush=True)
    return report


@app.local_entrypoint()
def main(run_id: str):
    _check_run_id(run_id)
    handles = [xatlas_basal.spawn(src, run_id) for src in sorted(XATLAS_ARMS)]
    for h in handles:
        print(json.dumps(h.get(), indent=2, default=str))
    print(json.dumps(assemble.remote(run_id), indent=2, default=str))
