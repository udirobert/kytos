# Kytos — experiments

Run outputs live here, one folder per run ID. See
[`docs/run-protocol.md`](../docs/run-protocol.md) for the run layout, the
`meta.json` and `facts.json` schemas, and the provenance/hygiene rules.

The **Observatory** ([`docs/observatory.md`](../docs/observatory.md)) renders
each run as a visual public page from `facts.json` plus committed `visual/`
(incl. VEED Fabric `briefing.mp4`), `narrative/`, and `literature/` artifacts.

To add a new run after reading the protocol, create `experiments/<run-id>/`,
assemble `facts.json`, run enrichment tools, and commit all artifacts alongside
prediction outputs.

**Run registry:**

- `k001-mean-shift-baseline` — Observatory Milestone 0 demo (2026-08-22); probe data.
- `k002-vcc2025-validation-mean-shift` — first **real** `cell-eval` 0.8.2 run
  (2026-08-22): VCC 2025 validation (H1 hESC, 98,927 cells, 50 targets),
  mean-shift floor. DE sig-genes recall 0.0 vs ceiling 0.494; pearson_delta
  mathematically undefined (constant prediction) vs ceiling 0.667; audit clean.
  Scoring matrix subsampled (200 cells/pert + 3,000 controls, seed 0) —
  full-depth run pending k003. Process notes:
  [`docs/k002-retro.md`](../docs/k002-retro.md).
- `k003-mean-shift-validation` — first **VCC 2026** submission (2026-09-05):
  360,000 cells, 300 targets × 3 contexts (`A`, `B`, `C`), `vcc` 0.2.0.
  Sparse top-300 control-gene mean-shift baseline. Overall `score_avg` -0.948,
  equal to the random `vcc sample` floor, because the prediction does not
  discriminate targets. Proved the end-to-end 2026 submit pipeline; the next
  run needs external 32 GB+ compute for real per-target cell resampling.
  Script: [`tools/run_k003_mean_shift.py`](../tools/run_k003_mean_shift.py).
- `k004-real-resampling-validation` — full-panel VCC 2026 baseline on Modal
  (2026-09-10): 360,000 cells, 300 targets × 3 contexts, real control-cell
  resampling (preserves single-cell dispersion). `vcc prep` + `vcc submit`
  passed. Overall score **-0.304** (rank 765), a large improvement over k003
  (-0.948). `pds` is still near zero because the prediction is not yet
  target-specific. Cost ~$0.43 on a 64 GiB / 4-core Modal Function.
  Script: [`tools/run_k004_real_resampling.py`](../tools/run_k004_real_resampling.py);
  launcher: [`tools/modal_k004_submit.py`](../tools/modal_k004_submit.py);
  meta: [`experiments/k004-real-resampling-validation/meta.json`](k004-real-resampling-validation/meta.json).
- `k004-layer-a-b-validation` — first target-specific Kytos model on Modal
  (2026-09-11): context-conditioned gene transfer (`ContextConditionedTransfer`)
  + log1p transport (`AdditiveTransportSampler`). 360,000 cells, 300 targets
  × 3 contexts. `vcc prep` + `vcc submit` passed. Overall score **-0.149**
  (rank 656), with `pds` turning positive (0.0019). Cost ~$0.75 on a 64 GiB /
  4-core Modal Function. Script: [`tools/run_k004_layer_a_b.py`](../tools/run_k004_layer_a_b.py);
  launcher: [`tools/modal_k004_layer_a_b_submit.py`](../tools/modal_k004_layer_a_b_submit.py);
  meta: [`experiments/k004-layer-a-b-validation/meta.json`](k004-layer-a-b-validation/meta.json).
- `k005-atlas-prior-validation` — **2025 Atlas prior** (2026-09-11): per-target
  log1p mean-shift deltas computed from the VCC 2025 validation (50 targets),
  applied to 2026 control cells with log1p transport. Only **4/300** 2026
  targets overlapped the 2025 validation, so the model is effectively
  k004-layer-a-b plus four real signatures. `vcc prep` passed and the `.vcc`
  is stored on the `kytos-vcc` Modal Volume (not submitted yet). Script:
  [`tools/run_k005_atlas_prior.py`](../tools/run_k005_atlas_prior.py);
  launcher: [`tools/modal_k005_atlas_prior.py`](../tools/modal_k005_atlas_prior.py);
  meta: [`experiments/k005-atlas-prior-validation/meta.json`](k005-atlas-prior-validation/meta.json).
- `k006-replogle-prior-validation` — **Replogle K562 GWPS + Atlas prior**
  (2026-09-11): combined VCC 2025 validation (50 targets) with Replogle K562
  genome-wide Perturb-seq bulk (9,866 targets), covering **272/300** 2026
  targets. Submitted; score **overall -0.021** (rank 534), `pds` 0.265, `nmae`
  -0.074. Script:
  [`tools/run_k006_replogle_prior.py`](../tools/run_k006_replogle_prior.py);
  launcher: [`tools/modal_k006_replogle_prior.py`](../tools/modal_k006_replogle_prior.py);
  meta: [`experiments/k006-replogle-prior-validation/meta.json`](k006-replogle-prior-validation/meta.json).
- `k004-kaggle-smoke` — **Kaggle free-tier smoke** (2026-09-10): small subset
  resampling vs `ContextConditionedTransfer` + `AdditiveTransportSampler`.
  Live **Kaggle Dataset** `udingethe/vcc2026-controls` + **Notebook**
  `udingethe/kytos-k004-kaggle-smoke` (v2, CPU). Scripts:
  [`notebooks/kaggle_k004_smoke.py`](../notebooks/kaggle_k004_smoke.py) /
  [`notebooks/kaggle_k004_smoke.ipynb`](../notebooks/kaggle_k004_smoke.ipynb);
  bundle: [`tools/kaggle_bundle.py`](../tools/kaggle_bundle.py).

```bash
# Dev A — assemble deterministic artifacts
python -m kytos.audit --run experiments/k001-mean-shift-baseline
python -m kytos.eval.facts --run experiments/k001-mean-shift-baseline
```
