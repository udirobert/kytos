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

**Cleveland Clinic / GQAI** runs live under
[`experiments/cleveland/`](cleveland/) with `cNNN-*` IDs (see
[`docs/cleveland/`](../docs/cleveland/)). They do not use the Observatory
enrichment path.

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
- `k007-neighbor-prior-validation` — **STRING-neighbor imputation**
  (2026-09-11): the 28 k006 fallback targets are unscreened in every Replogle
  arm; for the 18 with confident STRING partners, deltas are imputed as a
  score-weighted mean of partner signatures (validated in-corpus against
  held-out GWPS genes). Submitted; score **overall -0.0159** (rank 534),
  `nmae` -0.074 → +0.002, `pds` 0.265 → 0.269, `fid` -0.36 → -0.40. Script:
  [`tools/run_k007_neighbor_prior.py`](../tools/run_k007_neighbor_prior.py);
  launcher: [`tools/modal_k007_neighbor_prior.py`](../tools/modal_k007_neighbor_prior.py);
  meta: [`experiments/k007-neighbor-prior-validation/meta.json`](k007-neighbor-prior-validation/meta.json).
- `k008-kd-heterogeneity-validation` — **heterogeneous knockdown** (2026-09-12):
  k007 priors unchanged; the sampler adds per-cell knockdown-strength
  heterogeneity, `perturbed_i = basal_i + eta_i * delta + eps` with
  `eta ~ N(1, 0.4)` truncated at 0 — parameter fit from Atlas measurements
  (median per-target eta std ~1.1), not leaderboard tuning. Submitted; score
  **overall -0.0113** (rank 549), `fid` -0.403 → -0.388, `nmae` +0.007,
  `pds` 0.272. fid responded but modestly — scalar eta models spread along
  the delta axis only. Script:
  [`tools/run_k008_kd_heterogeneity.py`](../tools/run_k008_kd_heterogeneity.py);
  launcher: [`tools/modal_k008_kd_heterogeneity.py`](../tools/modal_k008_kd_heterogeneity.py);
  meta: [`experiments/k008-kd-heterogeneity-validation/meta.json`](k008-kd-heterogeneity-validation/meta.json).
- `k008-kd-s0p7-validation` — **kd_std sweep point** (2026-09-12): identical
  pipeline with `kd_std=0.7` (closer to the Atlas-measured ~1.1 median eta
  spread). Submitted; **first positive overall score: +0.0007** (rank 519),
  `fid` -0.388 → -0.334 (largest single-run fid gain), `nmae` +0.010,
  `pds` 0.282, `reach` 0.067. Script:
  [`tools/run_k008_kd_heterogeneity.py`](../tools/run_k008_kd_heterogeneity.py);
  meta: [`experiments/k008-kd-s0p7-validation/meta.json`](k008-kd-s0p7-validation/meta.json).
- `k008-kd-s1p0-validation` — **kd_std=1.0** (2026-09-13): matches the
  Atlas-measured median eta spread (~1.1). Submitted; score **overall
  +0.0152** (rank 509), `fid` -0.334 → -0.270, `pds` 0.297, `nmae` +0.011,
  `reach` 0.073 — every component improved; the mechanism was not
  exhausted at the median. Meta:
  [`experiments/k008-kd-s1p0-validation/meta.json`](k008-kd-s1p0-validation/meta.json).
- `k008-kd-s1p3-validation` — **kd_std=1.3** (2026-09-13): sweep continues
  upward — **overall +0.0291** (rank 490), `fid` -0.270 → -0.209, `pds`
  0.311, `reach` 0.079, `nmae` +0.011 flat. fid gains still ~0.06/step;
  the heavy right tail in measured eta (global std 2.32) explains why the
  optimum sits above the median. Meta:
  [`experiments/k008-kd-s1p3-validation/meta.json`](k008-kd-s1p3-validation/meta.json).
- `k008-kd-s1p7-validation` — **kd_std=1.7** (2026-09-14): **overall
  +0.0429** (rank 477), `fid` -0.209 → -0.148, `pds` 0.326, `reach` 0.087.
  `nmae` dipped +0.011 → +0.008 — first sign that overspread is blurring
  DE log-FC signal. Meta:
  [`experiments/k008-kd-s1p7-validation/meta.json`](k008-kd-s1p7-validation/meta.json).
- `k008-kd-s2p0-validation` — **kd_std=2.0** (2026-09-14): **overall
  +0.0511** (rank 462), `fid` -0.148 → -0.111 (gain shrinking: +0.037 vs
  +0.061/step), `pds` 0.336, `reach` 0.091, `nmae` +0.004 (still eroding).
  The scalar optimum sits around 2.0–2.3, matching the Atlas global eta
  std (2.32). Next lever is per-target spread, not a bigger scalar. Meta:
  [`experiments/k008-kd-s2p0-validation/meta.json`](k008-kd-s2p0-validation/meta.json).
- `k009-gamma-kd-s1p4-validation` — **gamma kd_std=1.4** (2026-09-15):
  **overall -0.0011** (rank 565), `nmae` **+0.020** (best yet — the
  mean-preserving fix worked) but `pds` 0.204 and `fid` -0.272 regress hard:
  the capped gamma (shape 0.51) piles ~half its mass near eta≈0, producing
  unperturbed-looking cells that cost discrimination. Meta:
  [`experiments/k009-gamma-kd-s1p4-validation/meta.json`](k009-gamma-kd-s1p4-validation/meta.json).
- `k009-gamma-kd-s2p0-validation` — **gamma kd_std=2.0** (2026-09-15):
  **overall +0.0075** (rank 544), `nmae` **+0.022** (best yet), `fid` -0.233,
  `pds` 0.208. More spread helps directionally but the A/B vs trunc-normal
  s2.0 (+0.0511) is conclusive: the leaderboard rewards symmetric dispersion
  centered on eta~1, not a right-skewed density. Next variant:
  mean-corrected trunc-normal — keep the winning shape, divide eta by
  E[N(1,σ)|η>0] to remove the +17% inflation and recover the nmae the gamma
  proved is available. Meta:
  [`experiments/k009-gamma-kd-s2p0-validation/meta.json`](k009-gamma-kd-s2p0-validation/meta.json).
- `k010-mean-corrected-kd-s2p0-validation` — **mean-corrected trunc-normal
  kd_std=2.0** (2026-09-16): **overall +0.0090** (rank 565), `nmae` +0.017
  as predicted but `fid` -0.305, `pds` 0.288 — removing the clipped-mean
  inflation (eta mean 1.40 → 1.00) cost more in fid/pds than it gained in
  nmae. The champion's "bias" was load-bearing. Meta:
  [`experiments/k010-mean-corrected-kd-s2p0-validation/meta.json`](k010-mean-corrected-kd-s2p0-validation/meta.json).
- `k010-mean-corrected-kd-s4p0-validation` — **kd_std=4.0** (2026-09-16):
  **overall +0.0122** (rank 564), `nmae` +0.019, `fid` -0.292. More mean-1
  spread helps marginally but stays far under +0.0511 — conclusive that
  **applied delta magnitude**, not dispersion-at-mean-1, drives the score.
  Borrowed signatures look systematically ~40% weak in the 2026 contexts.
  Next lever: explicit delta-scale calibration. Meta:
  [`experiments/k010-mean-corrected-kd-s4p0-validation/meta.json`](k010-mean-corrected-kd-s4p0-validation/meta.json).
- `k011-delta-scale-x1p3-validation` — **delta_scale=1.3** (2026-09-17):
  **overall +0.0559** (rank 502), new best score. `fid` improved sharply
  (-0.111 → -0.031) but `nmae` flipped negative (+0.004 → -0.023) and
  `pds` slipped (0.336 → 0.304). Explicit magnitude scaling makes the
  champion's hidden inflation interpretable. Meta:
  [`experiments/k011-delta-scale-x1p3-validation/meta.json`](k011-delta-scale-x1p3-validation/meta.json).
- `k011-delta-scale-x1p7-validation` — **delta_scale=1.7** (2026-09-17):
  **overall +0.0596** (rank 486), new best. `fid` nearly closed (-0.006),
  `pds` recovered to 0.339, `reach` 0.104 — but `nmae` cratered to -0.076:
  overscaled DE magnitudes are now the explicit cost. The scale axis is
  still net-positive overall (1.3 → 1.7 gained +0.004); ~2.0–2.3 could
  bracket the optimum, but the real fix is context-appropriate signatures
  (docs/k012-learned-layer-a.md). Meta:
  [`experiments/k011-delta-scale-x1p7-validation/meta.json`](k011-delta-scale-x1p7-validation/meta.json).
- `k011-delta-scale-x2p0-validation` — **delta_scale=2.0** (2026-09-18):
  **overall +0.0566** (rank 515). The curve has bent: `pds` best-yet
  0.356 and `fid` ~0, but `nmae` -0.125 outweighs the gains. Optimum
  ~1.7; the scalar magnitude axis is bracketed and done. Meta:
  [`experiments/k011-delta-scale-x2p0-validation/meta.json`](k011-delta-scale-x2p0-validation/meta.json).
- `k013-lineage-ratios` — **magnitude-ratio measurement** (2026-09-18):
  ||delta_lineage||/||delta_K562|| on 2,055 shared essential targets:
  RPE1 1.57, Jurkat 1.01, hESC ~0.44 (LOO scalar). Also: essential
  screens overlap 0/300 panel targets; figshare GWPS is K562-only.
  [`experiments/k013-lineage-ratios/report.json`](k013-lineage-ratios/report.json).
- `k013-context-scale-validation` — **per-context delta_scale**
  {A:1.7, B:2.65, C:0.75} (2026-09-18): **+0.0312** (rank 560) — clean
  negative; the lineage-ratio redistribution lost to uniform x1.7 on
  every component. Per-context amplitude is a dead end. Meta:
  [`experiments/k013-context-scale-validation/meta.json`](k013-context-scale-validation/meta.json).
- `k012-lineage-score` — **context identity verification** (2026-09-17):
  basal log1p profiles of A/B/C vs five reference controls (K562, RPE1,
  hESC, Jurkat, HepG2). On the top-2000 context-discriminative genes:
  **A is Jurkat-like (0.649)**, B weakly RPE1-leaning (0.369), C
  unresolved/hESC-leaning (0.379). Global Pearson misleads (hESC first
  everywhere — housekeeping + shared-assay inflation). Gate for k013
  per-context prior dispatch. Meta:
  [`experiments/k012-lineage-score/lineage_report.json`](k012-lineage-score/lineage_report.json).
- `k012-transfer-loo` — **learned Layer A LOO eval** (2026-09-17): five
  transfer classes on the 47-pair K562/hESC set. Raw transfer cosine
  ~0.13; no class clears the +0.05 acceptance bar — a publishable
  negative. Fitted scalar s=0.44 (hESC weaker than K562, opposite the
  2026 direction). Low-rank sign accuracy 0.60 vs 0.32 shows coarse
  pathway structure transfers, fine detail doesn't.
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
