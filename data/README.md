# data/ — corpora manifest + fetch scripts (Arc Atlas 2025, Replogle/Nadig, Gene Atlas). See docs/architecture.md §3.

## vcc2025 (k002) — restore guide

Local copies were deleted 2026-08-22 to free 12.9GB; everything regenerates:

- **Source** `adata_Validation.h5ad` (6.9GB): Arc public bucket, URL +
  sha256 prefix in `experiments/k002-vcc2025-validation-mean-shift/meta.json`
  (`.inputs` block). Then `.venv-science/bin/python tools/prep_vcc2025_validation.py`
  rebuilds `real_lognorm.h5ad`, `basal_lognorm.h5ad`, `targets.txt`,
  `gene_order.txt`.
- **k002 working set** (prediction, scored 200-cell/pert subsample, scripts,
  logs, raw cell-eval CSVs): HF Dataset
  [`Papajams/kytos-k002-repro`](https://huggingface.co/datasets/Papajams/kytos-k002-repro)
  — `huggingface-cli download Papajams/kytos-k002-repro --repo-type dataset`.
- Committed evaluation outputs (aggregated metrics, facts, audit,
  verification, docs of the subsample) live in the repo under
  `experiments/k002-vcc2025-validation-mean-shift/`.

k003 (full-depth scoring) = re-download source → prep with
`--purge-source --expect-source-sha256 376f0bab27d9f22e` (deletes the source
after verified outputs; writes `prep_manifest.json` with all hashes) →
`run_k002.sh` variant without the subsample step (version included in the HF
bundle).
