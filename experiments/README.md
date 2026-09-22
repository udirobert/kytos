# Kytos — experiments

Run outputs live here, one folder per run ID. See
[`docs/run-protocol.md`](../docs/run-protocol.md) for the run layout,
`meta.json`/`facts.json` schemas, and provenance rules.

The **Observatory** ([`docs/observatory.md`](../docs/observatory.md)) renders
each run as a public page from `facts.json` plus committed `visual/`,
`narrative/`, and `literature/` artifacts.

**Cleveland Clinic / GQAI** runs live under
[`experiments/cleveland/`](cleveland/) with `cNNN-*` IDs (see
[`docs/cleveland/`](../docs/cleveland/)). They do not use the Observatory
enrichment path.

## Registry rules

- Saved scores and artifacts are immutable observations. Interpretations may
  be corrected with dated notes; do not silently rewrite history.
- Separate **execution status** from **scientific outcome**. A blocked run is
  not a negative model result.
- Label proxy-only results as proxy-only. Legacy `cell-eval` metrics are not
  official 2026 scores.
- The leaderboard `fid` component is **DE direction fidelity**, not a
  Fréchet distance or direct covariance diagnostic.
- The active plan is [`docs/vcc-two-track-strategy.md`](../docs/vcc-two-track-strategy.md)
  (“VCC strategy — validation first”).

## Run registry

- `k001-mean-shift-baseline` — Observatory Milestone 0 demo (2026-08-22); probe data.
- `k002-vcc2025-validation-mean-shift` — first **real** legacy `cell-eval`
  0.8.2 run (2026-08-22): VCC 2025 validation (H1 hESC, 98,927 cells, 50
  targets), mean-shift floor. DE sig-genes recall 0.0 vs ceiling 0.494;
  `pearson_delta` undefined (constant prediction) vs ceiling 0.667; audit
  clean. Scoring matrix subsampled (200 cells/pert + 3,000 controls, seed 0).
  Process notes: [`docs/k002-retro.md`](../docs/k002-retro.md).
- `k003-mean-shift-validation` — first **VCC 2026** submission (2026-09-05):
  360,000 cells, 300 targets × 3 contexts. Sparse top-300 control-gene
  mean-shift baseline. Overall `score_avg` **-0.948**, equal to the random
  floor. Proved the end-to-end submit pipeline.
- `k004-real-resampling-validation` — full-panel baseline on Modal
  (2026-09-10): real control-cell resampling. Overall **-0.304** (rank 765);
  `pds` near zero because predictions were not target-specific. Meta:
  [`k004-real-resampling-validation/meta.json`](k004-real-resampling-validation/meta.json).
- `k004-layer-a-b-validation` — first target-specific model on Modal
  (2026-09-11): `ContextConditionedTransfer` + `AdditiveTransportSampler`.
  Overall **-0.149** (rank 656), `pds` 0.0019. Meta:
  [`k004-layer-a-b-validation/meta.json`](k004-layer-a-b-validation/meta.json).
- `k005-atlas-prior-validation` — 2025 Atlas prior (2026-09-11): only 4/300
  targets overlapped 2025 validation. `vcc prep` passed; `.vcc` stored on
  Modal Volume, not submitted. Meta:
  [`k005-atlas-prior-validation/meta.json`](k005-atlas-prior-validation/meta.json).
- `k006-replogle-prior-validation` — Replogle K562 GWPS + Atlas prior
  (2026-09-11): real signatures for 272/300 targets. Overall **-0.021**
  (rank 534), `pds` 0.265, `nmae` -0.074. Meta:
  [`k006-replogle-prior-validation/meta.json`](k006-replogle-prior-validation/meta.json).
- `k007-neighbor-prior-validation` — STRING-neighbor imputation for 18 of 28
  fallback targets (2026-09-11). Overall **-0.0159** (rank 534), `nmae`
  +0.002, `pds` 0.269, `fid` -0.40. Meta:
  [`k007-neighbor-prior-validation/meta.json`](k007-neighbor-prior-validation/meta.json).
- `k008-kd-heterogeneity-validation` — heterogeneous knockdown,
  `eta ~ N(1, 0.4)` truncated at 0 (2026-09-12). Overall **-0.0113**
  (rank 549), `fid` -0.388, `nmae` +0.007, `pds` 0.272. Meta:
  [`k008-kd-heterogeneity-validation/meta.json`](k008-kd-heterogeneity-validation/meta.json).
- `k008-kd-s0p7-validation` — `kd_std=0.7` (2026-09-12): **+0.0007**
  (rank 519), first positive score. Meta:
  [`k008-kd-s0p7-validation/meta.json`](k008-kd-s0p7-validation/meta.json).
- `k008-kd-s1p0-validation` — `kd_std=1.0` (2026-09-13): **+0.0152**
  (rank 509). Meta:
  [`k008-kd-s1p0-validation/meta.json`](k008-kd-s1p0-validation/meta.json).
- `k008-kd-s1p3-validation` — `kd_std=1.3` (2026-09-13): **+0.0291**
  (rank 490). Meta:
  [`k008-kd-s1p3-validation/meta.json`](k008-kd-s1p3-validation/meta.json).
- `k008-kd-s1p7-validation` — `kd_std=1.7` (2026-09-14): **+0.0429**
  (rank 477). Meta:
  [`k008-kd-s1p7-validation/meta.json`](k008-kd-s1p7-validation/meta.json).
- `k008-kd-s2p0-validation` — `kd_std=2.0` (2026-09-14): **+0.0511**
  (rank 462). Meta:
  [`k008-kd-s2p0-validation/meta.json`](k008-kd-s2p0-validation/meta.json).
- `k009-gamma-kd-s1p4-validation` — gamma `kd_std=1.4` (2026-09-15):
  **-0.0011** (rank 565), `nmae` +0.020 but `pds`/`fid` regressed. Meta:
  [`k009-gamma-kd-s1p4-validation/meta.json`](k009-gamma-kd-s1p4-validation/meta.json).
- `k009-gamma-kd-s2p0-validation` — gamma `kd_std=2.0` (2026-09-15):
  **+0.0075** (rank 544), `nmae` +0.022. Meta:
  [`k009-gamma-kd-s2p0-validation/meta.json`](k009-gamma-kd-s2p0-validation/meta.json).
- `k010-mean-corrected-kd-s2p0-validation` — mean-corrected trunc-normal
  `kd_std=2.0` (2026-09-16): **+0.0090** (rank 565). Meta:
  [`k010-mean-corrected-kd-s2p0-validation/meta.json`](k010-mean-corrected-kd-s2p0-validation/meta.json).
- `k010-mean-corrected-kd-s4p0-validation` — `kd_std=4.0` (2026-09-16):
  **+0.0122** (rank 564). Meta:
  [`k010-mean-corrected-kd-s4p0-validation/meta.json`](k010-mean-corrected-kd-s4p0-validation/meta.json).
- `k011-delta-scale-x1p3-validation` — `delta_scale=1.3` (2026-09-17):
  **+0.0559** (rank 502). Meta:
  [`k011-delta-scale-x1p3-validation/meta.json`](k011-delta-scale-x1p3-validation/meta.json).
- `k011-delta-scale-x1p7-validation` — `delta_scale=1.7` (2026-09-17):
  **+0.0596** (rank 486), best recorded submission. `pds` 0.339, `fid`
  -0.006, `nmae` -0.076, `reach` 0.104. Frozen comparison control. Meta:
  [`k011-delta-scale-x1p7-validation/meta.json`](k011-delta-scale-x1p7-validation/meta.json).
- `k011-delta-scale-x2p0-validation` — `delta_scale=2.0` (2026-09-18):
  **+0.0566** (rank 515). Meta:
  [`k011-delta-scale-x2p0-validation/meta.json`](k011-delta-scale-x2p0-validation/meta.json).
- `k012-lineage-score` — context identity screen (2026-09-17): A Jurkat-like
  (0.649), B weakly RPE1-leaning (0.369), C unresolved/hESC-leaning (0.379)
  on top-2000 discriminative genes. Proxy evidence only; lineage labels are
  not established identities. Report:
  [`k012-lineage-score/lineage_report.json`](k012-lineage-score/lineage_report.json).
- `k012-transfer-loo` — paired-signature LOO eval (2026-09-17): five transfer
  classes on 47 K562/hESC pairs. Raw transfer cosine ~0.13; no class cleared
  the +0.05 acceptance bar. Proxy-only negative. Reports:
  [`k012-transfer-loo/loo_report.json`](k012-transfer-loo/loo_report.json),
  [`k012-transfer-loo/facts.json`](k012-transfer-loo/facts.json).
- `k013-lineage-ratios` — magnitude-ratio measurement (2026-09-18): RPE1
  1.57, Jurkat 1.01, hESC ~0.44 on shared essential targets. Essential
  screens overlap 0/300 panel targets; public K562 is the only genome-wide
  arm identified in that audit. Report:
  [`k013-lineage-ratios/report.json`](k013-lineage-ratios/report.json).
- `k013-context-scale-validation` — per-context `delta_scale` {A:1.7,
  B:2.65, C:0.75} (2026-09-18): **+0.0312** (rank 560), regression vs
  uniform ×1.7. Meta:
  [`k013-context-scale-validation/meta.json`](k013-context-scale-validation/meta.json).
- `k014-conditional-mlp` — Track-2 conditional MLP (2026-09-18), **execution
  completed; not submitted**. Best held-out cosine 0.0425 vs identity 0.1406;
  magnitude ratio 0.35. Implementation-specific negative; it does not falsify
  all learned transfer. Record: [`docs/track2-nebius-setup.md`](../docs/track2-nebius-setup.md).
- `k015-lowrank-r256` — essential-screen low-rank transfer submission
  (2026-09-19): **-0.02797** (rank 683). Essential-screen data had 0/300
  overlap with the actual 2026 target panel; negative for this implementation,
  not a clean test of all transfer. Result:
  [`k015-essential-transfer/leaderboard_result.json`](k015-essential-transfer/leaderboard_result.json).
- `k016` — **unused/skipped**. The historical GEARS plan reserved this ID for a
  GNN experiment, but the executed GNN submissions were recorded as k020/k020b;
  there is no k016 artifact or result.
- `k017-h1-eval` / `k017-offline-cell-eval` — H1 transfer and dual-moment
  count evaluation (2026-09-19), **proxy-only**. Offline improvements did not
  predict the k018 leaderboard result. Reports:
  [`k017-h1-eval/h1_transfer_eval.json`](k017-h1-eval/h1_transfer_eval.json),
  [`k017-h1-eval/h1_transfer_sweep.json`](k017-h1-eval/h1_transfer_sweep.json),
  [`k017-offline-cell-eval/full_minimal/summary.json`](k017-offline-cell-eval/full_minimal/summary.json).
- `k018-h1-dualmoment` — H1 rank-64 transfer + dual-moment counts for context
  C only (2026-09-19): **+0.04239** (rank 546), regression vs k011. Evidence
  of proxy-to-leaderboard mismatch, not proof that H1 transfer is useless.
  Result:
  [`k018-h1-dualmoment/leaderboard_result.json`](k018-h1-dualmoment/leaderboard_result.json).
- `k019-crosslineage` — OOD-proxy transfer eval (2026-09-19), **proxy-only**
  and confounded as a deployment test: targets were selected using true
  destination responses, and the split did not represent the real 2026 panel.
  Findings remain useful diagnostics but are not a submission gate. Reports:
  [`k019-crosslineage/findings.md`](k019-crosslineage/findings.md),
  [`k019-crosslineage/ood_proxy_report.json`](k019-crosslineage/ood_proxy_report.json).
- `k020-gnn-crosslineage` — GEARS-style GNN submission (2026-09-20):
  **-0.114** (rank 811). `pds_cosine` 0.528. Implementation-specific
  negative; source review found baseline-preservation, inference-graph,
  missing-target, and output-axis confounds. Reports:
  [`k020-gnn-crosslineage/gnn_eval.json`](k020-gnn-crosslineage/gnn_eval.json),
  [`k020-gnn-crosslineage/gnn_meta.json`](k020-gnn-crosslineage/gnn_meta.json).
- `k020b-gnn-norm-match` — norm-matched GNN submission (2026-09-20):
  **-0.098** (rank 802). Magnitude damage decreased but `pds_cosine` did not
  improve (0.521 reported). Same confound caveats as k020; paused for
  spending, not a class-wide falsification.
- `k021-ceiling` — exploratory ceiling/attribution diagnostic (2026-09-20),
  **not an official score**. Used dual-moment generation rather than the
  champion sampler and mixed mean-single-cell-log effects with a bulk-log
  generator interpretation. Its signature/modeling fractions are exploratory,
  not causal. Summary:
  [`k021-ceiling/summary.json`](k021-ceiling/summary.json).
- `k022-pipeline-audit` — diagnostics-only pipeline audit (2026-09-20):
  disjoint fit/evaluation cells, champion-path transport, direct cell/bulk
  moments, null arms, manifests, and hashes. Synthetic smoke passed:
  [`k022-pipeline-audit/smoke/summary.json`](k022-pipeline-audit/smoke/summary.json).
  Real pilot `pilot-20260920-01` **stopped safely at preflight** because three
  Atlas labels were absent from the source axis (`HSPA14-1`, `TBCE-1`,
  `TMSB15B-1`); no predictions or official scores were produced. Receipts:
  [`pilot-20260920-01/preflight.json`](k022-pipeline-audit/pilot-20260920-01/preflight.json),
  [`pilot-20260920-01/execution.json`](k022-pipeline-audit/pilot-20260920-01/execution.json).
  The metadata-only axis audit (`axis-20260921-01`) proved the three labels
  are `make_unique` duplicate-symbol artifacts with no stable IDs and
  expression profiles distinct from their base symbols — suffix mapping
  would fabricate effects, so they are dropped from the diagnostic axis
  under an explicit `--allow-axis-drop` flag and recorded in each run
  manifest:
  [`axis-20260921-01/axis_report.json`](k022-pipeline-audit/axis-20260921-01/axis_report.json).
  `pilot-20260921-01` exercised that path end to end and failed inside the
  diagnostic on a backed-AnnData view-of-a-view defect (fixed; receipt:
  [`pilot-20260921-01/execution.json`](k022-pipeline-audit/pilot-20260921-01/execution.json)).
  `pilot-20260921-02` then **completed** the 3-target diagnostic
  (ACLY/ANXA6/ARPC2, 400 cells + 1600/1600 controls) on the aligned
  18,077-label axis. Proxy findings: transport null is calibrated on
  controls (variance ratio 1.05); measured-delta transport preserves
  direction moderately (cosines 0.33–0.87); borrowed K562 signatures are
  strongly target-dependent (cosines -0.01 to 0.76); direct-moment arms
  under-disperse (~0.28 variance ratio). Diagnostics only — not a
  six-metric leaderboard surrogate:
  [`pilot-20260921-02/summary.json`](k022-pipeline-audit/pilot-20260921-02/summary.json),
  [`pilot-20260921-02/execution.json`](k022-pipeline-audit/pilot-20260921-02/execution.json).
  The full paired-panel run `paired47-20260921-01` evaluated 32/47 paired
  targets (15 dropped for <800 cells). Findings: borrowed K562 deltas
  reach median cosine 0.268 vs 0.514 for measured in-context deltas —
  signature content is the quantified bottleneck — and a precomputable
  transferability gate is **falsified**: `cos(delta_k562, delta_hesc)`
  predicts borrowed-signature success at r≈0.22 (0.32 among high-ceiling
  targets). Uniform levers and gate-based selection are exhausted;
  remaining routes are context-matched signatures or a learned transfer
  model. Receipts:
  [`paired47-20260921-01/summary.json`](k022-pipeline-audit/paired47-20260921-01/summary.json),
  [`paired47-20260921-01/execution.json`](k022-pipeline-audit/paired47-20260921-01/execution.json).
  Scorer contract:
  [`k022-pipeline-audit/scorer_contract.json`](k022-pipeline-audit/scorer_contract.json);
  pinned `cell-eval2` 0.16.0 smoke report:
  [`k022-pipeline-audit/eval2_contract_smoke.json`](k022-pipeline-audit/eval2_contract_smoke.json).
- `k023-source-coverage` — metadata-only coverage audit (2026-09-21):
  X-Atlas HCT116 and HEK293T each cover **300/300** panel targets
  (genome-wide, ≥140 median cells/pert), CD4 Marson-2025 covers **291/300**
  (251 with quality-pass rows), H1-2025 train overlaps **13/300**. The 0/300
  essential-screen blocker does not apply — a 4-lineage consensus ensemble
  is data-feasible. Report:
  [`k023-source-coverage/coverage_report.json`](k023-source-coverage/coverage_report.json).
- `k025-eval2-gate` — production-equivalent `cell-eval2` 0.16.0 evaluation
  harness (`tools/modal_k025_eval2_gate.py`): prediction generation →
  `run` → `baseline` → `prep-real-bundle` → `score --real-bundle`, 47
  paired hESC targets, 400 cells/pert. **All metric outputs embargoed
  until Oct 22** — receipts in `experiments/_embargoed/k025-eval2-gate/`
  (local-only, gitignored).
- `k026-consensus-w-ctr` — submitted 2026-09-22: consensus deltas through
  the k011 transport generator. Official **+0.0670**, rank 512/1086.
  Receipts: [`k026-consensus-w-ctr/`](k026-consensus-w-ctr/).
- `k027-consensus-dm` — submitted 2026-09-22: same consensus deltas
  through `build_prediction_dual_moment`. Official **+0.1262**, rank
  308/1088 — **champion**. Receipts: [`k027-consensus-dm/`](k027-consensus-dm/).
- `k004-kaggle-smoke` — Kaggle free-tier smoke (2026-09-10): small subset
  resampling vs `ContextConditionedTransfer` + `AdditiveTransportSampler`.
  Scripts: [`notebooks/kaggle_k004_smoke.py`](../notebooks/kaggle_k004_smoke.py) /
  [`notebooks/kaggle_k004_smoke.ipynb`](../notebooks/kaggle_k004_smoke.ipynb);
  bundle: [`tools/kaggle_bundle.py`](../tools/kaggle_bundle.py).

## 2026-09-20 validation reset

Implemented safeguards now verified on synthetic fixtures:

- strict prediction-artifact schema and effect-space declaration;
- exact gene-axis coverage with explicit reordering;
- trained effects overlaid on the combined baseline prior;
- uncovered target/context baseline backfill;
- no-op parity with k011;
- A-only context isolation;
- output-overwrite protection;
- input/code/provenance hashes.

Not yet established: full-panel real-data parity, official six-metric scorer
integration, CPU DE-backend equivalence, or a new submission candidate.

```bash
# Dev A — assemble deterministic artifacts
python -m kytos.audit --run experiments/k001-mean-shift-baseline
python -m kytos.eval.facts --run experiments/k001-mean-shift-baseline
```
