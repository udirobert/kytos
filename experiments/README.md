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
- `k004-kaggle-smoke` — **Kaggle free-tier smoke** (2026-09-10): real control-cell
  resampling baseline (preserves dispersion) vs `ContextConditionedTransfer` +
  `AdditiveTransportSampler` (first non-trivial Layer A/B). 10–20 targets × 3
  contexts (12k–24k cells, 140MB–2.4GB) — validates wiring without densifying
  26GB dense. Live **Kaggle Dataset** `udingethe/vcc2026-controls` (632 MB,
  private) + **Notebook** `udingethe/kytos-k004-kaggle-smoke` (v2, CPU). Scripts:
  [`notebooks/kaggle_k004_smoke.py`](../notebooks/kaggle_k004_smoke.py) /
  [`notebooks/kaggle_k004_smoke.ipynb`](../notebooks/kaggle_k004_smoke.ipynb);
  bundle: [`tools/kaggle_bundle.py`](../tools/kaggle_bundle.py).

```bash
# Dev A — assemble deterministic artifacts
python -m kytos.audit --run experiments/k001-mean-shift-baseline
python -m kytos.eval.facts --run experiments/k001-mean-shift-baseline
```
