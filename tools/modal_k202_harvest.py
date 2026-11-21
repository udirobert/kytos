"""k202 -- manifest-driven L0 evidence harvester (phase 1) on Modal.

Why this job exists
-------------------
``docs/engine-v2-design.md`` milestone k202: a harvester that lands one
new source per invocation into the L0 evidence schema
(``/kytos-vol/k201-evidence/<dataset_id>/<run_id>/``). The catalog below
is seeded from the k039 lineage audit (URLs verified live 2026-10-12)
plus the lineage-score refs; ``docs/evidence-corpus-inventory.md`` tracks
status and the wider phase-1/2 lists.

Extraction contract
-------------------
Per-(target, sample) group-mean deltas vs same-sample controls, then
one-sample Welch-t (the same reducer as k201 via ``tools/evidence_l0.py``).
Sample unit = catalog ``batch_col`` if pinned, else auto-detected obs
batch/sample/gem/donor column, else deterministic pseudo-batches by
barcode hash (manifest flags ``PSEUDOREP`` -- L1 must downweight), else
pooled n=1 (no stats emitted).

``x_kind``: ``raw`` counts -> log1p(clip(0)); ``log1p-norm`` -> already
log-normalized (scPertEval processed), lfc_kind logged accordingly.
Units are never silently mixed -- manifest carries ``lfc_kind`` +
``units_caveat``.

Run:
  modal run -d tools/modal_k202_harvest.py --dataset wessels23
  modal run -d tools/modal_k202_harvest.py --dataset replogle22rpe1
  modal run -d tools/modal_k202_harvest.py --list
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import modal

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/root/kytos")
VOLUME_ROOT = Path("/kytos-vol")
OUT_ROOT = VOLUME_ROOT / "k201-evidence"
PANEL_GENES = REMOTE_ROOT / "data/vcc2026/gene_names.csv"

ROW_CHUNK = 20_000
PSEUDO_BATCHES = 8

SCPERTEVAL = "https://storage.googleapis.com/scperteval/processed"
SCPERTURB = "https://zenodo.org/records/10044268/files"
ALTOSHF = "https://huggingface.co/datasets/altoslabs/primeflow-vcc-datasets/resolve/main"

# Catalog: dataset_id -> spec. scPertEval URLs verified live 2026-10-12
# (k039 audit) BUT the bucket flipped to requester-pays since -- access:
# "requester-pays" entries need a GCP billing project before they harvest.
# Fields:
#   url           download URI
#   access        "open" (plain HTTPS) | "requester-pays" (GCS billing proj)
#   size_gb       approximate download size
#   context       cell line / tissue label for the manifest
#   assay         sc-crnispri | sc-crispa | sc-crisprko | bulk-crnispri
#   x_kind        raw | log1p-norm
#   batch_col     pinned obs sample/batch column (None -> auto-detect)
#   pert_col      pinned obs perturbation column (None -> auto-detect)
#   license/citation  provenance strings
CATALOG = {
    # --- figshare Replogle 2022 GWPS raw arms (open, verified 2026-11-20) ---
    "replogle22rpe1-raw": {
        "url": "https://ndownloader.figshare.com/files/35775606",
        "access": "open",
        "size_gb": 8.7,
        "context": "rpe1",
        "assay": "sc-crnispri",
        "x_kind": "norm",
        "batch_col": "gem_group",
        "pert_col": "gene",
        "sha256": "9b05ef1f81526216fa008d677e9e0d03dce9a2f7a95499a4fb81e505e9d88ef1",
        "citation": "Replogle et al. 2022 RPE1 GWPS raw (figshare rpe1_raw_singlecell_01.h5ad)",
        "license": "public (figshare)",
        "note": "247,914 cells / 2,394 targets / 56 gem_groups; despite "
        "the 'raw' filename X is publisher-normalized expression "
        "(fractional, dense) -- norm-mean-diff units, honor "
        "before mixing with log1p sources",
    },
    "replogle22rpe1-bulk": {
        "url": "https://ndownloader.figshare.com/files/35775581",
        "access": "open",
        "size_gb": 0.1,
        "context": "rpe1",
        "assay": "bulk-crnispri",
        "x_kind": "norm",
        "sample_mode": "row-per-sample",
        "target_source": "obs_name_field",
        "target_field": 1,
        "control_flag_col": "core_control",
        "citation": "Replogle et al. 2022 RPE1 GWPS raw bulk (figshare rpe1_raw_bulk_01.h5ad)",
        "license": "public (figshare)",
        "note": "guide-level normalized expression (2,679 guides x 8,749 "
        "genes; ~1-2 guides/target) -- point-estimate deltas, "
        "stats only where >=3 guides; units caveat recorded",
    },
    # --- scPerturb harmonized arm (Zenodo 10044268; X = raw CSR counts,
    #     obs: perturbation/target/replicate/cell_line, var: gene_symbol;
    #     conventions verified 2026-11-20 via DatlingerBock2017) ---
    "norman19-k562": {
        "url": f"{SCPERTURB}/NormanWeissman2019_filtered.h5ad?download=1",
        "access": "open",
        "size_gb": 0.7,
        "context": "k562",
        "assay": "sc-oe",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Norman et al. 2019 (scPerturb harmonized)",
        "license": "public (zenodo scPerturb)",
        "note": "overexpression interaction screen -- activation units; "
        "do NOT pool into KD consensus",
    },
    "replogle22k562-ess": {
        "url": f"{SCPERTURB}/ReplogleWeissman2022_K562_essential.h5ad?download=1",
        "access": "open",
        "size_gb": 1.6,
        "context": "k562",
        "assay": "sc-crnispri",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Replogle et al. 2022 K562 essential (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "essential screen arm -- second K562 source for LOLO",
    },
    "tian19-ipsc": {
        "url": f"{SCPERTURB}/TianKampmann2019_iPSC.h5ad?download=1",
        "access": "open",
        "size_gb": 0.4,
        "context": "ipsc",
        "assay": "sc-crnispri",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Tian/Kampmann 2019 iPSC (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "Kampmann iPSC CRISPRi screen",
    },
    "tian19-neuron": {
        "url": f"{SCPERTURB}/TianKampmann2019_day7neuron.h5ad?download=1",
        "access": "open",
        "size_gb": 0.3,
        "context": "neuron",
        "assay": "sc-crnispri",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Tian/Kampmann 2019 day-7 neuron (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "differentiated-neuron arm -- lineage diversity",
    },
    "tian21-crnispri": {
        "url": f"{SCPERTURB}/TianKampmann2021_CRISPRi.h5ad?download=1",
        "access": "open",
        "size_gb": 0.3,
        "context": "neuron",
        "assay": "sc-crnispri",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Tian/Kampmann 2021 CRISPRi (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "2021 neuron CRISPRi arm",
    },
    "tian21-crispa": {
        "url": f"{SCPERTURB}/TianKampmann2021_CRISPRa.h5ad?download=1",
        "access": "open",
        "size_gb": 0.2,
        "context": "neuron",
        "assay": "sc-crispa",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Tian/Kampmann 2021 CRISPRa (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "activation arm -- opposite-direction evidence only",
    },
    "shifrut18-tcell": {
        "url": f"{SCPERTURB}/ShifrutMarson2018.h5ad?download=1",
        "access": "open",
        "size_gb": 0.3,
        "context": "tcell",
        "assay": "sc-crisprko",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Shifrut/Marson 2018 T cell (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "primary T-cell KO screen -- immune context",
    },
    "dixit16-dc": {
        "url": f"{SCPERTURB}/DixitRegev2016.h5ad?download=1",
        "access": "open",
        "size_gb": 0.3,
        "context": "dendritic",
        "assay": "sc-crisprko",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Dixit/Regev 2016 DC (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "dendritic-cell Perturb-seq KO screen",
    },
    "datlinger17-jurkat": {
        "url": f"{SCPERTURB}/DatlingerBock2017.h5ad?download=1",
        "access": "open",
        "size_gb": 0.04,
        "context": "jurkat",
        "assay": "crop-oe",
        "x_kind": "raw",
        "batch_col": "replicate",
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Datlinger/Bock 2017 Jurkat CROP-seq (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "TF overexpression screen (NOT knockdown); 6 replicates; "
        "conventions verified 2026-11-20",
    },
    "datlinger21-k562": {
        "url": f"{SCPERTURB}/DatlingerBock2021.h5ad?download=1",
        "access": "open",
        "size_gb": 0.03,
        "context": "k562",
        "assay": "crop-seq",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Datlinger/Bock 2021 (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "2021 CROP-seq arm",
    },
    "adamson16-k562-s1": {
        "url": f"{SCPERTURB}/AdamsonWeissman2016_GSM2406675_10X001.h5ad?download=1",
        "access": "open",
        "size_gb": 0.03,
        "context": "k562",
        "assay": "sc-crnispri",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "perturbation",
        "control_regex": "pBA",
        "target_source": "col_field",
        "target_field": 0,
        "citation": "Adamson/Weissman 2016 K562 10X001 (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "early K562 CRISPRi screen, lane 1",
    },
    "adamson16-k562-s5": {
        "url": f"{SCPERTURB}/AdamsonWeissman2016_GSM2406677_10X005.h5ad?download=1",
        "access": "open",
        "size_gb": 0.14,
        "context": "k562",
        "assay": "sc-crnispri",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "perturbation",
        "control_regex": "pBA",
        "target_source": "col_field",
        "target_field": 0,
        "citation": "Adamson/Weissman 2016 K562 10X005 (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "early K562 CRISPRi screen, lane 5",
    },
    "adamson16-k562-s10": {
        "url": f"{SCPERTURB}/AdamsonWeissman2016_GSM2406681_10X010.h5ad?download=1",
        "access": "open",
        "size_gb": 0.47,
        "context": "k562",
        "assay": "sc-crnispri",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "perturbation",
        "control_regex": "pBA",
        "target_source": "col_field",
        "target_field": 0,
        "citation": "Adamson/Weissman 2016 K562 10X010 (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "early K562 CRISPRi screen, lane 10",
    },
    "papalexi21-pbmc": {
        "url": f"{SCPERTURB}/PapalexiSatija2021_eccite_RNA.h5ad?download=1",
        "access": "open",
        "size_gb": 0.15,
        "context": "pbmc",
        "assay": "sc-crisprko",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Papalexi/Satija 2021 ECCITE-seq (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "PBMC ECCITE-seq arm -- immune context",
    },
    "frangieh21-melanoma": {
        "url": f"{SCPERTURB}/FrangiehIzar2021_RNA.h5ad?download=1",
        "access": "open",
        "size_gb": 1.5,
        "context": "melanoma",
        "assay": "sc-crisprko",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Frangieh/Izar 2021 melanoma (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "melanoma CROP-seq arm",
    },
    "zhao21-brain": {
        "url": f"{SCPERTURB}/ZhaoSims2021.h5ad?download=1",
        "access": "open",
        "size_gb": 0.6,
        "context": "brain-organoid",
        "assay": "sc-crispr",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Zhao/Sims 2021 (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "verify context at peek",
    },
    "schiebinger19-1": {
        "url": f"{SCPERTURB}/SchiebingerLander2019_GSE106340.h5ad?download=1",
        "access": "open",
        "size_gb": 0.4,
        "context": "ipsc-diff",
        "assay": "sc-crisprko",
        "x_kind": "raw",
        "batch_col": None,
        "pert_col": "target",
        "control_col": "perturbation",
        "citation": "Schiebinger/Lander 2019 GSE106340 (scPerturb)",
        "license": "public (zenodo scPerturb)",
        "note": "iPSC reprogramming screen arm 1",
    },
    # --- altoslabs HF mirror (preprocessed h5ad.gz; replaces blocked
    #     scPertEval arm + adds new contexts) ---
    "nadig24-jurkat": {
        "url": f"{ALTOSHF}/nadig24_jurkat_preprocessed.h5ad.gz",
        "access": "open",
        "size_gb": 1.9,
        "context": "jurkat",
        "assay": "sc-crnispri",
        "x_kind": "log1p-norm",
        "batch_col": "gem_group",
        "pert_col": "gene",
        "citation": "Nadig et al. 2024 Jurkat (altoslabs preprocessed)",
        "license": "public (HF primeflow-vcc-datasets)",
        "note": "essential screen; peeked 2026-11-20: CSR log1p-norm "
        "(max~6.1), gem_group n=55, gene w/ 'non-targeting' ctrl",
    },
    "nadig24-hepg2": {
        "url": f"{ALTOSHF}/nadig24_hepg2_preprocessed.h5ad.gz",
        "access": "open",
        "size_gb": 1.3,
        "context": "hepg2",
        "assay": "sc-crnispri",
        "x_kind": "log1p-norm",
        "batch_col": "gem_group",
        "pert_col": "gene",
        "citation": "Nadig et al. 2024 HepG2 (altoslabs preprocessed)",
        "license": "public (HF primeflow-vcc-datasets)",
        "note": "essential screen; liver lineage; same schema as "
        "nadig24-jurkat (pinned, unverified -- audit manifest)",
    },
    "mcfaline23-gxe": {
        "url": f"{ALTOSHF}/mcfaline23_gxe_preprocessed.h5ad.gz",
        "access": "open",
        "size_gb": 3.2,
        "context": "u87mg+a172+t98g",
        "assay": "sc-crnispri-gxe",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "McFaline-Figueroa et al. 2023 sci-Plex-GxE (altoslabs preprocessed)",
        "license": "public (HF primeflow-vcc-datasets)",
        "note": "kinome CRISPRi x drug GxE incl U-87MG (VCC-final context) "
        "-- DMSO arm only is the clean KD evidence",
    },
    "replogle20-k562": {
        "url": f"{ALTOSHF}/replogle20_preprocessed.h5ad.gz",
        "access": "open",
        "size_gb": 0.25,
        "context": "k562",
        "assay": "sc-crnispri",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "Replogle et al. 2020 direct-capture (altoslabs)",
        "license": "public (HF primeflow-vcc-datasets)",
        "note": "direct-capture Perturb-seq, small",
    },
    "feng24-ipsc": {
        "url": f"{ALTOSHF}/feng24_preprocessed.h5ad.gz",
        "access": "open",
        "size_gb": 10.3,
        "context": "ipsc-lines",
        "assay": "sc-crnispri",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "Feng et al. 2024/26 iPSC lines (altoslabs)",
        "license": "public (HF primeflow-vcc-datasets)",
        "note": "genome-scale trans-regulation map across iPSC lines; "
        "natural multi-context batch structure",
    },
    "jiang24-pathway": {
        "url": f"{ALTOSHF}/jiang24_preprocessed.h5ad.gz",
        "access": "open",
        "size_gb": 10.0,
        "context": "mixed",
        "assay": "sc-crispr",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "Jiang et al. 2024 pathway screens (altoslabs)",
        "license": "public (HF primeflow-vcc-datasets)",
        "note": "pathway-signature reconstruction screens",
    },
    # --- figshare k562 arms (same article as rpe1) ---
    "replogle22k562-gwps-bulk": {
        "url": "https://ndownloader.figshare.com/files/35774443",
        "access": "open",
        "size_gb": 0.4,
        "context": "k562",
        "assay": "bulk-crnispri",
        "x_kind": "norm",
        "sample_mode": "row-per-sample",
        "target_source": "obs_name_field",
        "target_field": 1,
        "control_flag_col": "core_control",
        "citation": "Replogle et al. 2022 K562 GWPS raw bulk (figshare 35774443)",
        "license": "public (figshare)",
        "note": "bulk arm of the k562 GWPS -- cross-assay check vs replogle-k562-gwps sc store",
    },
    "replogle22k562-ess-bulk": {
        "url": "https://ndownloader.figshare.com/files/35773070",
        "access": "open",
        "size_gb": 0.1,
        "context": "k562",
        "assay": "bulk-crnispri",
        "x_kind": "norm",
        "sample_mode": "row-per-sample",
        "target_source": "obs_name_field",
        "target_field": 1,
        "control_flag_col": "core_control",
        "citation": "Replogle et al. 2022 K562 essential raw bulk (figshare 35773070)",
        "license": "public (figshare)",
        "note": "essential-screen bulk arm",
    },
    # --- scPertEval processed arm (requester-pays since ~Oct 2026) ---
    "wessels23": {
        "url": f"{SCPERTEVAL}/wessels23_processed_complete.h5ad",
        "access": "requester-pays",
        "size_gb": 0.2,
        "context": "thp-1",
        "assay": "sc-crnispri",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "Wessels et al. 2023 (scPertEval processed)",
        "license": "public (scPertEval portal)",
        "note": "THP-1 myeloid; needs GCP billing project for download",
    },
    "replogle22rpe1": {
        "url": f"{SCPERTEVAL}/replogle22rpe1_processed_complete.h5ad",
        "access": "requester-pays",
        "size_gb": 1.9,
        "context": "rpe1",
        "assay": "sc-crnispri",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "Replogle et al. 2022 RPE1 (scPertEval processed)",
        "license": "public (scPertEval portal)",
        "note": "~2,057 essential-gene targets; prefer the raw figshare "
        "arm (replogle22rpe1-raw) for unit parity",
    },
    "nadig25jurkat": {
        "url": f"{SCPERTEVAL}/nadig25jurkat_processed_complete.h5ad",
        "access": "requester-pays",
        "size_gb": 2.0,
        "context": "jurkat",
        "assay": "sc-crnispri",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "Nadig et al. 2025 Jurkat (scPertEval processed)",
        "license": "public (scPertEval portal)",
        "note": "essential screen; second Jurkat source",
    },
    "nadig25hepg2": {
        "url": f"{SCPERTEVAL}/nadig25hepg2_processed_complete.h5ad",
        "access": "requester-pays",
        "size_gb": 1.2,
        "context": "hepg2",
        "assay": "sc-crnispri",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "Nadig et al. 2025 HepG2 (scPertEval processed)",
        "license": "public (scPertEval portal)",
        "note": "essential screen; liver lineage",
    },
    "kaden25rpe1": {
        "url": f"{SCPERTEVAL}/kaden25rpe1_processed_complete.h5ad",
        "access": "requester-pays",
        "size_gb": 5.6,
        "context": "rpe1",
        "assay": "sc-crispa",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "Kaden et al. 2025 RPE1 (scPertEval processed)",
        "license": "public (scPertEval portal)",
        "note": "CRISPRa activation -- NOT knockdown consensus material; "
        "harvested as opposite-direction evidence only",
    },
    "arch1": {
        "url": f"{SCPERTEVAL}/arch1_processed_complete.h5ad",
        "access": "requester-pays",
        "size_gb": 4.4,
        "context": "h1-hesc",
        "assay": "sc-crnispri",
        "x_kind": "log1p-norm",
        "batch_col": None,
        "pert_col": None,
        "citation": "ARC Institute H1 hESC (scPertEval processed)",
        "license": "public (scPertEval portal)",
        "note": "hESC; 13/300 panel coverage per k039 audit",
    },
}

app = modal.App("kytos-k202-harvest")
volume = modal.Volume.from_name("kytos-vcc", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy==2.2.6",
        "scipy==1.15.3",
        "pandas==2.2.3",
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
        LOCAL_ROOT / "tools/evidence_l0.py",
        str(REMOTE_ROOT / "tools/evidence_l0.py"),
        copy=True,
    )
    .add_local_file(
        LOCAL_ROOT / "data/raw/vcc2026/gene_names.csv",
        str(PANEL_GENES),
        copy=True,
    )
)


@app.function(
    image=image,
    cpu=(4.0, 4.0),
    memory=(32768, 32768),
    timeout=14400,
    volumes={"/kytos-vol": volume},
    ephemeral_disk=524288,
    retries=modal.Retries(max_retries=2, backoff_coefficient=1.0),
)
def harvest(dataset_id: str, run_id: str) -> dict:
    """Download one catalog h5ad -> per-(target,sample) Welch L0 store."""
    import sys

    import anndata as ad
    import numpy as np
    import pandas as pd
    import requests
    from scipy import sparse

    sys.path.insert(0, str(REMOTE_ROOT / "tools"))
    import consensus_deltas as cd
    import evidence_l0 as l0

    spec = CATALOG[dataset_id]
    out = OUT_ROOT / dataset_id / run_id
    if (out / "stats.npz").exists():
        return {"status": "exists", "out": str(out)}
    if spec.get("access") == "requester-pays":
        raise RuntimeError(
            f"{dataset_id}: bucket is requester-pays -- needs a GCP "
            "billing project (gsutil -u <project> or GCS userProject "
            "param). Catalogued but not harvestable without credentials."
        )

    # --- download (sha256 recorded, no pin required for new sources) ---
    gz = spec["url"].endswith(".gz")
    local = Path(f"/tmp/{dataset_id}.h5ad")
    digest = hashlib.sha256()
    if not local.exists():
        import gzip as _gz

        src = Path(f"/tmp/{dataset_id}.h5ad.gz" if gz else local)
        with requests.get(spec["url"], stream=True, timeout=120) as r:
            r.raise_for_status()
            with src.open("wb") as fh:
                for chunk in r.iter_content(1024 * 1024 * 8):
                    fh.write(chunk)
                    digest.update(chunk)
        if gz:
            with _gz.open(src, "rb") as fi, local.open("wb") as fo:
                while True:
                    buf = fi.read(1 << 26)
                    if not buf:
                        break
                    fo.write(buf)
            src.unlink()
    else:
        with local.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 26), b""):
                digest.update(chunk)
    sha = digest.hexdigest()
    if spec.get("sha256") and sha != spec["sha256"]:
        raise RuntimeError(f"{dataset_id}: sha256 mismatch {sha} != {spec['sha256']}")
    with local.open("rb") as fh:
        sig = fh.read(8)
    if not sig.startswith(b"\x89HDF"):
        local.unlink()  # clean slate for the retry attempt
        raise RuntimeError(
            f"{dataset_id}: download is not HDF5 ({local.stat().st_size} "
            f"bytes, head={sig[:8]!r}) -- likely a redirect/error page"
        )

    panel_genes = pd.read_csv(PANEL_GENES).iloc[:, 0].astype(str).tolist()
    n_genes = len(panel_genes)
    x_kind = spec["x_kind"]  # raw | log1p-norm | norm
    raw_x = x_kind == "raw"
    sample_mode = spec.get("sample_mode", "batch-paired")

    adata = ad.read_h5ad(local, backed="r")
    t0 = time.time()
    try:
        obs = adata.obs
        src_genes, gene_axis = l0.pick_gene_axis(adata)

        # --- control rows + target labels ---
        if spec.get("control_regex"):
            # e.g. Adamson16: perturbation = GENE_sgRNA, controls are the
            # pBA-plasmid guides -> control_regex 'pBA'
            ccol = spec.get("control_col") or spec.get("pert_col")
            if ccol not in obs.columns:
                ccol, _ = l0.pick_pert_column(obs)
            is_ctrl = (
                obs[ccol].astype(str).str.contains(spec["control_regex"], case=False).to_numpy()
            )
            pert_col = ccol
            detected = ccol
            ctrl_label = spec["control_regex"]
        elif spec.get("control_flag_col"):
            is_ctrl = obs[spec["control_flag_col"]].astype(bool).to_numpy()
            pert_col = spec["control_flag_col"]
            ctrl_label = "True"
        else:
            # control_col: where control labels live (default = pert_col).
            # scPerturb: 'perturbation' holds 'control' while 'target'
            # holds the gene -> control_col=perturbation, pert_col=target.
            # Pinned cols that are absent in this file fall back to
            # autodetect -- the manifest records what was actually used.
            ctrl_col = spec.get("control_col") or spec.get("pert_col")
            if ctrl_col and ctrl_col not in obs.columns:
                ctrl_col = None
            if ctrl_col:
                vals = obs[ctrl_col].astype(str).str.lower().unique()
                hit = [v for v in vals if v in l0.CONTROL_LABELS]
                if not hit:
                    raise ValueError(f"{dataset_id}: no control label in obs.{ctrl_col}")
                ctrl_label = hit[0]
                detected = ctrl_col
            else:
                detected, ctrl_label = l0.pick_pert_column(obs)
            labels_lower = obs[detected].astype(str).str.lower().to_numpy()
            is_ctrl = np.array([x in l0.CONTROL_LABELS for x in labels_lower])
            pert_col = spec.get("pert_col") or detected
            if pert_col not in obs.columns:
                pert_col = detected
        if spec.get("target_source") == "obs_name_field":
            names = adata.obs_names.astype(str).to_numpy()
            labels = np.array([n.split("_")[spec["target_field"]] for n in names])
        elif spec.get("target_source") == "col_field":
            # e.g. Adamson16 perturbation 'SPI1_pDS255' -> target 'SPI1'
            labels = obs[pert_col].astype(str).str.split("_").str[spec["target_field"]].to_numpy()
        else:
            labels = obs[pert_col].astype(str).to_numpy()

        # target axis is panel genes only: combinatorial labels
        # ('PPP2R1A_MAT2A'), off-panel symbols and junk labels can't be
        # consumed downstream and would explode the (T,G) accumulator
        all_labels = set(labels[~is_ctrl])
        targets = sorted(all_labels & set(panel_genes))
        n_offpanel = len(all_labels) - len(targets)
        if n_offpanel:
            print(
                f"{dataset_id}: {n_offpanel} off-panel/combo labels excluded "
                f"from target axis (e.g. {sorted(all_labels - set(targets))[:3]})",
                flush=True,
            )
        t_pos = {t: i for i, t in enumerate(targets)}
        n_targets = len(targets)

        positions, missing = cd.map_gene_axis(list(src_genes), panel_genes)
        keep_mask = positions >= 0
        pos_keep = positions[keep_mask]
        n_src = len(src_genes)
        mapped_panel = np.flatnonzero(keep_mask)
        S_sel = sparse.csr_matrix(
            (np.ones(len(pos_keep)), (pos_keep, mapped_panel)),
            shape=(n_src, n_genes),
        )
        k_kept = int(keep_mask.sum())

        bucket = np.full(len(labels), -1, dtype=np.int64)
        bucket[is_ctrl] = n_targets
        lab_pos = np.array([t_pos.get(x, -1) for x in labels], dtype=np.int64)
        bucket[~is_ctrl & (lab_pos >= 0)] = lab_pos[~is_ctrl & (lab_pos >= 0)]

        n_obs = adata.n_obs
        X = adata.X
        if sample_mode == "row-per-sample":
            # Each obs row IS a sample (bulk/guide-level files): delta of
            # each row vs the pooled control mean, Welch over rows.
            batch_col = "obs-row (each row is a replicate unit)"
            se_kind = "welch-per-row vs pooled controls"
            sum_x = np.zeros((n_targets + 1, k_kept))
            sum_x2 = np.zeros((n_targets + 1, k_kept))
            cnt = np.zeros(n_targets + 1, dtype=np.int64)
            print(
                f"{dataset_id}: obs={n_obs} targets={n_targets} "
                f"mode=row-per-sample kept_cols={k_kept}",
                flush=True,
            )
            for r0 in range(0, n_obs, ROW_CHUNK):
                r1 = min(r0 + ROW_CHUNK, n_obs)
                b_c = bucket[r0:r1]
                keep_c = b_c >= 0
                if not keep_c.any():
                    continue
                xb = X[r0:r1]
                if sparse.issparse(xb):
                    xp = (xb @ S_sel).toarray()[:, keep_mask]
                else:
                    xp = np.asarray(xb)[:, pos_keep]
                if raw_x:
                    xp = np.log1p(np.clip(np.asarray(xp), 0, None))
                else:
                    xp = np.asarray(xp)
                np.add.at(sum_x, b_c[keep_c], xp[keep_c])
                np.add.at(sum_x2, b_c[keep_c], xp[keep_c] ** 2)
                np.add.at(cnt, b_c[keep_c], 1)
                if (r0 // ROW_CHUNK) % 25 == 24:
                    print(f"rows {r1}/{n_obs} ({time.time() - t0:.0f}s)", flush=True)
            n_batches = 0
        else:
            batch_col, batches = l0.pick_batch_column(obs, forced=spec.get("batch_col"))
            if batch_col is not None:
                n_batches = int(batches.max()) + 1
                se_kind = f"welch-per-{batch_col}"
            else:
                # deterministic pseudo-batches -- PSEUDOREP, manifest flags it
                names = adata.obs_names.astype(str).to_numpy()
                batches = (pd.util.hash_array(names) % PSEUDO_BATCHES).astype(np.int64)
                n_batches = PSEUDO_BATCHES
                batch_col = f"pseudobatch{PSEUDO_BATCHES}-barcode-hash"
                se_kind = f"welch-pseudobatch{PSEUDO_BATCHES} (PSEUDOREP -- L1 downweight)"

            sums = np.zeros((n_targets + 1, n_batches, k_kept))
            cnts = np.zeros((n_targets + 1, n_batches), dtype=np.int64)
            flat = sums.reshape((n_targets + 1) * n_batches, k_kept)
            print(
                f"{dataset_id}: obs={n_obs} targets={n_targets} "
                f"batches={n_batches} ({batch_col}) kept_cols={k_kept}",
                flush=True,
            )
            for r0 in range(0, n_obs, ROW_CHUNK):
                r1 = min(r0 + ROW_CHUNK, n_obs)
                b_c = bucket[r0:r1]
                g_c = batches[r0:r1]
                keep_c = b_c >= 0
                if not keep_c.any():
                    continue
                xb = X[r0:r1]
                if sparse.issparse(xb):
                    xp = (xb @ S_sel).toarray()[:, keep_mask]
                else:
                    xp = np.asarray(xb)[:, pos_keep]
                if raw_x:
                    xp = np.log1p(np.clip(np.asarray(xp), 0, None))
                else:
                    xp = np.asarray(xp)
                np.add.at(flat, b_c[keep_c] * n_batches + g_c[keep_c], xp[keep_c])
                np.add.at(cnts, (b_c[keep_c], g_c[keep_c]), 1)
                if (r0 // ROW_CHUNK) % 25 == 24:
                    print(f"rows {r1}/{n_obs} ({time.time() - t0:.0f}s)", flush=True)
    finally:
        adata.file.close()

    if sample_mode == "row-per-sample":
        ctrl_mean = sum_x[n_targets] / max(int(cnt[n_targets]), 1)
        mean_d = np.full((n_targets, k_kept), np.nan)
        e2_d = np.zeros((n_targets, k_kept))
        n_v = np.zeros(n_targets, dtype=np.int64)
        covered = cnt[:n_targets] > 0
        t_mean = sum_x[:n_targets] / np.maximum(cnt[:n_targets], 1)[:, None]
        # E[(x - c)^2] = E[x^2] - 2c E[x] + c^2
        t_e2 = sum_x2[:n_targets] / np.maximum(cnt[:n_targets], 1)[:, None]
        mean_d[covered] = t_mean[covered] - ctrl_mean[None, :]
        e2_d[covered] = np.maximum(
            t_e2[covered] - 2 * ctrl_mean[None, :] * t_mean[covered] + ctrl_mean[None, :] ** 2, 0.0
        )
        n_v = cnt[:n_targets]
        mean_full = np.full((n_targets, n_genes), np.nan)
        e2_full = np.zeros((n_targets, n_genes))
        n_full = np.zeros((n_targets, n_genes), dtype=np.int16)
        mean_full[:, keep_mask] = mean_d
        e2_full[:, keep_mask] = e2_d
        n_full[:, keep_mask] = n_v[:, None]
        se, p, z = l0.welch_from_moments(
            np.where(np.isfinite(mean_full), mean_full, 0.0), e2_full, n_full
        )
    else:
        mean_full, se, p, z, n_full, covered = l0.group_delta_welch(
            sums, cnts, sums[n_targets], cnts[n_targets], n_targets, n_genes, keep_mask
        )
    lfc = mean_full
    kd_eff = l0.kd_eff_from_self(targets, panel_genes, lfc)
    lfc_kind = {
        "raw": "log1p-sc",
        "log1p-norm": "log1p-norm-mean",
        "norm": "norm-mean-diff",
    }[x_kind]
    units_caveat = {
        "raw": None,
        "log1p-norm": (
            "X is log1p(normalize_total(1e4)) processed, not raw counts -- "
            "deltas are log-normalized-mean differences; honor before mixing"
        ),
        "norm": (
            "X is publisher-normalized expression (not integer counts); "
            "deltas are mean-expression differences in publisher units -- "
            "honor before mixing with log1p sources"
        ),
    }[x_kind]
    manifest = {
        "dataset_id": dataset_id,
        "run_id": run_id,
        "lfc_kind": lfc_kind,
        "units_caveat": units_caveat,
        "se_kind": se_kind,
        "estimation": (
            "per-row deltas vs pooled control mean; one-sample Welch t over rows"
            if sample_mode == "row-per-sample"
            else "per-(target,sample) group-mean deltas vs same-sample controls; "
            "one-sample Welch t over samples"
        ),
        "sample_mode": sample_mode,
        "sample_unit": batch_col,
        "n_batches": int(n_batches),
        "assay": spec["assay"],
        "context": spec["context"],
        "pert_col": pert_col,
        "control_col": spec.get("control_col") or spec.get("control_flag_col"),
        "control_label": ctrl_label,
        "gene_axis": gene_axis,
        "unmapped_panel_genes": len(missing),
        "dataset_url": spec["url"],
        "access": spec.get("access", "open"),
        "sha256": sha,
        "citation": spec["citation"],
        "license": spec["license"],
        "note": spec.get("note"),
        "created": l0.utc_now(),
    }
    res = l0.emit_store(out, panel_genes, targets, covered, lfc, se, p, z, n_full, kd_eff, manifest)
    volume.commit()
    return res


@app.local_entrypoint()
def main(dataset: str = "", run_id: str = "", list_: bool = False, wait: bool = False) -> None:
    if list_ or not dataset:
        for k, v in CATALOG.items():
            print(
                f"{k:22s} {v['size_gb']:5.1f}GB {v['access']:15s} "
                f"{v['context']:8s} {v['assay']:13s} {v['x_kind']:11s} "
                f"{v['url'][:60]}"
            )
        if not dataset:
            return
    if dataset not in CATALOG:
        raise ValueError(f"unknown dataset {dataset!r}; --list to see catalog")
    rid = run_id or time.strftime("h202-%Y%m%d-01", time.gmtime())
    if wait:
        print(json.dumps(harvest.remote(dataset, rid), indent=2))
        return
    call = harvest.spawn(dataset, rid)
    print(json.dumps({"spawned": call.object_id, "run_id": rid, "dataset": dataset}))
