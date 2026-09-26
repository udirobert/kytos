"""Extract Jurkat perturbation deltas + basal profiles from GSE249595 (k031).

Why this job exists
-------------------
The complementary-corpus audit (experiments/_embargoed/k030-ctxlineage.md)
found GSE249595: a genome-wide CRISPRi Perturb-seq screen in Jurkat E6 --
the lineage context A most resembles on discriminative genes. It covers
299/300 panel targets, an overlap no current source matches. The screen
hashes cells by condition (6x activated + 1x untreated); the untreated arm
gives both resting-Jurkat deltas and a Jurkat basal profile for the k030
context-weighting scheme.

Data layout (per channel, GSM7951413..428)
------------------------------------------
- ``<GSM>_channel<N>_transcriptome_matrix.mtx.gz`` -- 20,606 genes x 6,794,880
  barcode columns, coordinate sparse (real cells = nonzero columns).
- ``<GSM>_channel<N>_guides_matrix.mtx.gz`` -- 83,401 guides x same columns.
  Guide names ``{TARGET}_{n}`` (``~`` = bicistronic pairs, skipped;
  ``non-targeting_*`` = NTC).
- ``<GSM>_channel<N>_labels_matrix.mtx.gz`` -- 7 hash labels x same columns;
  argmax label assigns condition (``untreated_1`` vs ``activated*``).
- Features/barcodes are shared across channels: genes are the same 20,606,
  guide axis is the same 83,401, label axis is the same 7, barcode axis is
  the same 6,794,880 (verified on channel 1; asserted on every channel).

Accumulation
------------
Per channel, per condition (rest / stim):
- for every kept cell: dominant guide -> panel target (or NTC); log1p(raw)
  added to a per-(condition, target, panel_gene) accumulator.
- NTC cells accumulate a per-condition basal sum.
Combine step: delta[target] = mean_log1p(target) - mean_log1p(NTC) per
condition; basal = NTC mean.

Outputs (on the Modal volume under ``k031-jurkat/<run_id>/``)
------------------------------------------------------------
``deltas_jurkat_rest.npz`` / ``deltas_jurkat_stim.npz`` -- genes, targets,
  deltas, covered, n_cells (same schema as k023 source deltas).
``basal_jurkat.npz`` -- genes, basal (resting NTC mean log1p).
``manifest_jurkat.json`` -- provenance, coverage, hashes.

Run:
  modal run -d tools/modal_k031_jurkat_extract.py --run-id jurkat-YYYYMMDD-NN
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
OUT_DIR = VOLUME_ROOT / "k031-jurkat"
PANEL_GENES = REMOTE_ROOT / "data/vcc2026/gene_names.csv"
PANEL_COUNTS = REMOTE_ROOT / "data/vcc2026/pert_counts.csv"
PAIRED_PATH = VOLUME_ROOT / "paired-transfer/paired_transfer_train.npz"

GEO_BASE = (
    "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM7951nnn/GSM795{gsm}/suppl/"
    "GSM795{gsm}_channel{ch}_{part}.gz"
)
CHANNEL_GSMS = {ch: 1413 + (ch - 1) for ch in range(1, 17)}  # GSM7951413 .. GSM7951428
N_GUIDES = 83401
N_LABELS = 7
N_BARCODES = 6794880
REST_LABEL = "untreated_1"
# Assays are shallow (~0.76 guide nnz/cell): accept 1 UMI but require the
# dominant feature to be UNIQUE at max count (no ties) -- a 1-UMI single-
# guide cell is a valid call, a 1-vs-1 tie is not.
GUIDE_MIN_COUNT = 1
LABEL_MIN_COUNT = 1
MIN_CELLS_PER_TARGET = 20  # coverage threshold for a target's delta

app = modal.App("kytos-k031-jurkat")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "scipy==1.15.3",
        "pandas==2.2.3",
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
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/pert_counts.csv",
        str(PANEL_COUNTS),
        copy=True,
    )
)


def _check_run_id(run_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("Use a new alphanumeric run ID (hyphens/underscores allowed)")


def _load_request_targets():
    """Union of the 300-target 2026 panel and the 47 Atlas-eval targets."""
    import numpy as np
    import pandas as pd

    panel = sorted(pd.read_csv(PANEL_COUNTS).iloc[:, 0].astype(str).unique())
    with np.load(PAIRED_PATH, allow_pickle=False) as paired:
        eval_targets = paired["paired_targets"].astype(str).tolist()
    return sorted(set(panel) | set(eval_targets))


def _geo_url(gsm_suffix: int, ch: int, part: str) -> str:
    return GEO_BASE.format(gsm=gsm_suffix, ch=ch, part=part)


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=10800,
    startup_timeout=300,
    retries=0,
    max_containers=4,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
)
def channel_accumulate(ch: int, run_id: str) -> dict:
    """Accumulate per-(condition, target) log1p sums for one channel."""
    import gzip
    import io
    import time
    from urllib.request import urlopen

    import numpy as np
    import pandas as pd
    from scipy import io as sio
    from scipy import sparse

    sys_path = str(REMOTE_ROOT / "tools")
    import sys

    sys.path.insert(0, sys_path)
    import consensus_deltas as cd

    _check_run_id(run_id)
    gsm = CHANNEL_GSMS[ch]
    out = OUT_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    part_path = out / f"part_ch{ch:02d}.npz"
    if part_path.exists():
        return {"status": "exists", "channel": ch}

    t0 = time.time()
    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    n_genes = len(panel_genes)
    request_targets = _load_request_targets()
    n_targets = len(request_targets)
    target_pos = {t: i for i, t in enumerate(request_targets)}
    request_set = set(request_targets)

    def fetch(part: str) -> bytes:
        url = _geo_url(gsm, ch, part)
        for attempt in range(5):
            try:
                with urlopen(url, timeout=300) as r:
                    return r.read()
            except Exception as exc:
                if attempt == 4:
                    raise
                print(f"[ch{ch}] {part} retry {attempt + 1}: {exc}", flush=True)
                time.sleep(5 * (attempt + 1))

    def load_mtx(part: str) -> sparse.coo_matrix:
        raw = fetch(part)
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
            return sio.mmread(io.BytesIO(gz.read())).tocoo()

    def load_tsv(part: str) -> list[list[str]]:
        raw = fetch(part)
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
            return [line.decode().rstrip("\n").split("\t") for line in gz]

    # ---- axes -----------------------------------------------------------
    label_names = [r[0] for r in load_tsv("labels_features.tsv")]
    assert len(label_names) == N_LABELS, label_names
    rest_idx = label_names.index(REST_LABEL)

    guide_names = [r[0] for r in load_tsv("guides_features.tsv")]
    assert len(guide_names) == N_GUIDES

    tx_feats = load_tsv("transcriptome_features.tsv")
    tx_symbols = [r[1] for r in tx_feats]  # col 2 = gene symbol
    pos_arr, missing = cd.map_gene_axis(tx_symbols, panel_genes)
    gene_to_panel = np.full(len(tx_symbols), -1, dtype=np.int32)
    gene_to_panel[pos_arr[pos_arr >= 0]] = np.flatnonzero(pos_arr >= 0)

    # guide -> target string; "~" bicistronic and non-gene names -> ""
    guide_target = np.empty(N_GUIDES, dtype=object)
    guide_target[:] = ""
    for i, name in enumerate(guide_names):
        stem = name.rsplit("_", 1)[0]
        guide_target[i] = stem
    is_ntc = np.array([g.startswith("non-targeting") for g in guide_target])
    is_request = np.array([g in request_set for g in guide_target])

    # ---- labels: dominant hash per cell ----------------------------------
    def unique_argmax(coo, n_cols):
        """argmax per column requiring a UNIQUE max; -1 where absent/tied."""
        mx = np.zeros(n_cols, dtype=np.int64)
        np.maximum.at(mx, coo.col, coo.data)
        at_max = coo.data == mx[coo.col]
        n_at_max = np.bincount(coo.col[at_max], minlength=n_cols)
        arg = np.full(n_cols, -1, dtype=np.int64)
        uniq = at_max & (n_at_max[coo.col] == 1)
        arg[coo.col[uniq]] = coo.row[uniq]
        return arg, mx

    lab = load_mtx("labels_matrix.mtx").tocoo()  # (7, cells)
    assert lab.shape == (N_LABELS, N_BARCODES), lab.shape
    lab_arg, lab_max = unique_argmax(lab, N_BARCODES)
    labeled = (lab_max >= LABEL_MIN_COUNT) & (lab_arg >= 0)
    cond_rest = labeled & (lab_arg == rest_idx)
    cond_stim = labeled & (lab_arg != rest_idx)

    # ---- guides: dominant guide per cell ---------------------------------
    gui = load_mtx("guides_matrix.mtx").tocoo()  # (guides, cells)
    assert gui.shape == (N_GUIDES, N_BARCODES), gui.shape
    gui_arg, gui_max = unique_argmax(gui, N_BARCODES)
    guided = (gui_max >= GUIDE_MIN_COUNT) & (gui_arg >= 0)
    gui_arg_safe = np.clip(gui_arg, 0, None)
    cell_target = guide_target[gui_arg_safe]
    cell_is_ntc = is_ntc[gui_arg_safe]
    cell_ok = guided & (is_request[gui_arg_safe] | cell_is_ntc)

    # per-condition cell sets
    rest_cells = np.flatnonzero(cond_rest & cell_ok)
    stim_cells = np.flatnonzero(cond_stim & cell_ok)
    print(
        f"[ch{ch}] rest_cells={len(rest_cells)} stim_cells={len(stim_cells)}",
        flush=True,
    )

    # ---- transcriptome: accumulate log1p sums ----------------------------
    tx = load_mtx("transcriptome_matrix.mtx").tocsc()  # (genes, cells)
    assert tx.shape == (len(tx_symbols), N_BARCODES), tx.shape

    conds = {"rest": rest_cells, "stim": stim_cells}
    result = {}
    for cond, cells in conds.items():
        # bucket index = request-target position; index n_targets = NTC
        tgt_bucket = np.full(len(cells), -1, dtype=np.int32)
        for j, c in enumerate(cells):
            if cell_is_ntc[c]:
                tgt_bucket[j] = -2
            else:
                tgt_bucket[j] = target_pos.get(cell_target[c], -1)
        n_buckets = n_targets + 1  # last bucket = NTC
        bucket_of = np.where(tgt_bucket == -2, n_targets, tgt_bucket)
        keep = bucket_of >= 0
        cells = cells[keep]
        bucket_of = bucket_of[keep]
        if not len(cells):
            result[cond] = {
                "sums": sparse.csr_matrix((n_buckets, n_genes)),
                "counts": np.zeros(n_buckets, np.int64),
            }
            continue
        sub = tx[:, cells].tocsr()  # (20606, n_kept)
        sub.data = np.log1p(sub.data.astype(np.float64))
        coo = sub.tocoo()  # row=gene, col=cell
        ppos = gene_to_panel[coo.row]
        sel = ppos >= 0
        sums = sparse.coo_matrix(
            (coo.data[sel], (bucket_of[coo.col[sel]], ppos[sel])),
            shape=(n_buckets, n_genes),
        ).tocsr()  # duplicate (bucket, gene) coords summed by tocsr
        counts = np.bincount(bucket_of, minlength=n_buckets)
        result[cond] = {"sums": sums, "counts": counts}

    np.savez_compressed(
        str(part_path),
        rest_sums_data=result["rest"]["sums"].data,
        rest_sums_indices=result["rest"]["sums"].indices,
        rest_sums_indptr=result["rest"]["sums"].indptr,
        rest_counts=result["rest"]["counts"],
        stim_sums_data=result["stim"]["sums"].data,
        stim_sums_indices=result["stim"]["sums"].indices,
        stim_sums_indptr=result["stim"]["sums"].indptr,
        stim_counts=result["stim"]["counts"],
    )
    (out / f"manifest_ch{ch:02d}.json").write_text(
        json.dumps(
            {
                "channel": ch,
                "gsm": f"GSM795{gsm}",
                "rest_cells": int(len(rest_cells)),
                "stim_cells": int(len(stim_cells)),
                "labeled_cells": int(labeled.sum()),
                "guided_cells": int((guided & cell_ok).sum()),
                "missing_panel_genes_in_tx": missing,
                "elapsed_s": round(time.time() - t0, 1),
            },
            indent=2,
        )
        + "\n"
    )
    volume.commit()
    return {"status": "completed", "channel": ch, "elapsed_s": round(time.time() - t0, 1)}


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(49152, 49152),
    timeout=10800,
    startup_timeout=300,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(VOLUME_ROOT): volume},
)
def combine(run_id: str) -> dict:
    """Combine channel partials into deltas + basal NPZs."""
    import sys
    import time

    import numpy as np
    import pandas as pd
    from scipy import sparse

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))

    _check_run_id(run_id)
    t0 = time.time()
    out = OUT_DIR / run_id
    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    n_genes = len(panel_genes)
    request_targets = _load_request_targets()
    n_targets = len(request_targets)
    n_buckets = n_targets + 1

    def zero_part():
        return (
            sparse.csr_matrix((n_buckets, n_genes), dtype=np.float64),
            np.zeros(n_buckets, np.int64),
        )

    def load_part(path):
        with np.load(path) as d:
            rest = (
                sparse.csr_matrix(
                    (d["rest_sums_data"], d["rest_sums_indices"], d["rest_sums_indptr"]),
                    shape=(n_buckets, n_genes),
                ),
                d["rest_counts"].astype(np.int64),
            )
            stim = (
                sparse.csr_matrix(
                    (d["stim_sums_data"], d["stim_sums_indices"], d["stim_sums_indptr"]),
                    shape=(n_buckets, n_genes),
                ),
                d["stim_counts"].astype(np.int64),
            )
        return rest, stim

    rest_sums, rest_counts = zero_part()
    stim_sums, stim_counts = zero_part()
    n_parts = 0
    for ch in range(1, 17):
        p = out / f"part_ch{ch:02d}.npz"
        if not p.exists():
            raise FileNotFoundError(f"missing {p}")
        (rs, rc), (ss, sc) = load_part(p)
        rest_sums += rs
        rest_counts += rc
        stim_sums += ss
        stim_counts += sc
        n_parts += 1

    outputs = {}
    for cond, sums, counts in (
        ("rest", rest_sums, rest_counts),
        ("stim", stim_sums, stim_counts),
    ):
        sums_d = sums.toarray()
        ntc_sum, ntc_n = sums_d[n_targets], max(int(counts[n_targets]), 1)
        ntc_mean = ntc_sum / ntc_n
        tgt_means = sums_d[:n_targets] / np.maximum(counts[:n_targets], 1)[:, None]
        delta = tgt_means - ntc_mean[None, :]
        covered = counts[:n_targets] >= MIN_CELLS_PER_TARGET
        delta[~covered] = 0.0
        np.savez_compressed(
            str(out / f"deltas_jurkat_{cond}.npz"),
            genes=np.asarray(panel_genes),
            targets=np.asarray(request_targets),
            delta=delta.astype(np.float32),
            covered=covered,
            n_cells=counts[:n_targets].astype(np.int64),
        )
        outputs[cond] = {
            "covered_targets": int(covered.sum()),
            "ntc_cells": int(ntc_n),
            "median_cells_per_target": int(np.median(counts[:n_targets][covered]))
            if covered.any()
            else 0,
        }
        print(f"[combine] {cond}: {outputs[cond]}", flush=True)

    basal = np.asarray(rest_sums[n_targets].toarray()).ravel() / max(int(rest_counts[n_targets]), 1)
    basal = basal.astype(np.float32)
    np.savez_compressed(
        str(out / "basal_jurkat.npz"),
        genes=np.asarray(panel_genes),
        basal=basal,
        n_cells=np.int64(rest_counts[n_targets]),
    )

    manifest = {
        "dataset": "GSE249595 Jurkat E6 genome-wide CRISPRi Perturb-seq",
        "run_id": run_id,
        "channels": n_parts,
        "min_cells_per_target": MIN_CELLS_PER_TARGET,
        "guide_min_count": GUIDE_MIN_COUNT,
        "label_min_count": LABEL_MIN_COUNT,
        "units": "mean log1p(raw counts) target cells - resting/stim NTC mean",
        "coverage": outputs,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (out / "manifest_jurkat.json").write_text(json.dumps(manifest, indent=2) + "\n")
    volume.commit()
    return manifest


@app.local_entrypoint()
def main(run_id: str):
    _check_run_id(run_id)
    handles = [channel_accumulate.spawn(ch, run_id) for ch in range(1, 17)]
    for h in handles:
        print(json.dumps(h.get(), indent=2, default=str))
    print(json.dumps(combine.remote(run_id), indent=2, default=str))
