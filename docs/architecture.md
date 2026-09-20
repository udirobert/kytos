# Kytos — architecture and decision record

Status: **ACTIVE** · Updated **2026-09-20** · Owner: udingethe

This document separates the architecture that currently exists from research
proposals. It should not be read as a claim that every model family discussed
below has been implemented or cleanly evaluated.

## 1. Current champion — k011 frozen control

The best recorded submission is `kytos-k011-ds-x1p7`, produced by
`tools/run_k011_delta_scale.py`:

- overall score **+0.059575**, observed rank **486** at publication;
- source priors: 2025 Atlas effects where available, Replogle K562 effects,
  STRING-neighbor imputation, and the existing fallback chain;
- dispatch recorded in the run metadata: **816 real**, **54 neighbor**, and
  **30 fallback** target-context assignments;
- fully assembled delta is scaled by `delta_scale=1.7`, including
  self-knockdown, before transport;
- sampler: `HeterogeneousTransportSampler` with
  `eta = clip(N(1, kd_std=2.0), 0)`, `mean_correct=False`, and
  `noise_scale=0.05`.

k011 remains the frozen comparison control. Candidate changes should be
evaluated as controlled modifications of this path, not as wholesale
replacements by default.

## 2. Implemented pipeline safeguards

`tools/run_k014_trained_model.py` is the shared consumer for trained-effect
artifacts. The current implementation is intentionally conservative:

- strict artifact schema: scalar `schema_version=1`, scalar
  `effect_space="additive_log1p"`, unique `gene_names`, explicit `contexts`,
  explicit `vcc_targets`, finite `(C,T,G)` deltas, and a boolean `(C,T)`
  coverage mask;
- gene names may be reordered, but must exactly cover the consumer axis;
- unknown contexts, unknown targets, malformed axes, and missing metadata
  fail closed;
- trained effects are overlaid on the combined baseline prior:
  `real = {**combined_deltas, **overrides}`;
- uncovered targets retain the baseline backfill chain: combined real prior,
  neighbor prior, then fallback;
- existing `prediction.h5ad` and `meta.json` cannot be overwritten;
- metadata records dispatch by context, override counts, input hashes, code
  hashes, effect space, and artifact schema.

Verified on synthetic fixtures:

- exact no-op parity with k011;
- A-only trained overrides leave B/C unchanged;
- malformed or legacy artifacts are rejected.

Not yet verified: full-panel real-data parity or official-score equivalence.
Legacy MLP/GNN `.npz` artifacts intentionally fail the new schema until an
audited producer/conversion exists.

## 3. Diagnostic infrastructure

### k022 pipeline audit

`tools/run_k022_pipeline_audit.py` is a diagnostics-only harness. It uses
disjoint fit/evaluation cells, the champion transport path, direct cell and
bulk moments, null arms, split manifests, and code/input hashes.

It does **not** compute:

- official 2026 scores;
- Wilcoxon DE metrics;
- a six-metric leaderboard surrogate;
- a promotion gate.

Synthetic smoke passed: `experiments/k022-pipeline-audit/smoke/summary.json`.

The real Modal pilot `pilot-20260920-01` completed preflight and stopped
safely on `source_gene_axis_incomplete`. Atlas was `98,927 × 18,080`; the
source axis was `47 × 18,533`. Three Atlas labels were absent from source:

- `HSPA14-1`
- `TBCE-1`
- `TMSB15B-1`

No diagnostic subprocess ran, no predictions were generated, and no official
score was computed. Do not strip suffixes or infer equivalence without
feature-ID evidence. Receipts:
`experiments/k022-pipeline-audit/pilot-20260920-01/preflight.json` and
`execution.json`.

### Official scorer contract

The public `cell-eval2` implementation and `vcc2026` preset were identified at
revision `5e64833518a6603a0301cbe28185d49c30f4a986` (package version `0.16.0`).
The preset contains six metrics:

- `pds_cosine`
- `expr_mse_unbiased_capped_norm`
- `de_wilcoxon_direction_fidelity_yield_raw`
- `de_wilcoxon_direction_reach_raw`
- `de_wilcoxon_sig_jaccard`
- `de_wilcoxon_lfc_nmae`

Contract notes are in
`experiments/k022-pipeline-audit/scorer_contract.json`.

Important: this scorer is **identified, not installed or integrated**. CPU DE
backend behavior and reference-anchor compatibility remain unverified. The
older local `cell-eval 0.8.2` `vcc` profile is a legacy three-metric suite and
is not equivalent to the 2026 leaderboard scorer.

## 4. Effect representations are not interchangeable

Do not describe all response vectors as one generic “delta”. These are
distinct quantities:

| Representation | Meaning | Where it appears |
|---|---|---|
| raw-count log shift | log-scale change applied in count/transport code | k007/k011-style transport |
| additive log1p effect | exported artifact contract for trained-effect overrides | k014 consumer |
| mean single-cell log expression shift | `mean(log expression)` difference across cells | k021-style measured effect |
| bulk-log expression effect | `log(mean expression)` difference | bulk/pseudobulk signatures |
| per-cell probability moments | cell-level expression probability moments | dual-moment generator |
| pooled/bulk probability moments | aggregated moments for a perturbation group | dual-moment generation/evaluation |

`mean(log expression)` is not `log(mean expression)`. Supplying one
representation where a generator expects another invalidates attribution of
the remaining error.

## 5. Implemented model components

### Layer A — effect signatures

`src/kytos/models/layer_a.py` currently implements:

- `MeanShiftTransfer`
- `ContextConditionedTransfer`

The current API is `predict_delta(target_gene, context: BasalContext)`. The
implemented model uses target basal rank and mean expression to determine
direct knockdown and secondary effects. It is not the full learned
context-transfer model proposed in older design documents.

The deployed champion primarily uses data-derived source signatures plus
neighbor/fallback dispatch, not a trained neural Layer A replacement.

### Layer B — count generation

Implemented components include:

- `AdditiveTransportSampler`
- `HeterogeneousTransportSampler`
- `src/kytos/models/dual_moment.py`

The champion uses `HeterogeneousTransportSampler`. k021 used the dual-moment
generator, so its results are not a controlled diagnosis of the champion's
generator.

## 6. Proposed research, gated

These are hypotheses, not current architecture:

1. **Partial common-response adjustment** — estimate and partially correct
   response components shared across source perturbations while protecting
   target-specific signal.
2. **Uncertainty-aware shrinkage** — attenuate unreliable gene effects where
   replicate or guide-level support exists.
3. **Small residual corrections** — learn strongly regularized corrections
   that shrink toward the baseline under weak support.
4. **Complementary data audit** — assess panel coverage, assay, effect space,
   replicate quality, access, and eligibility rather than assuming coverage
   is exhausted.
5. **Future transfer/generative models** — only revisit after Gate A–C
   evidence identifies a concrete limitation that the model can address.

Flow-matching/diffusion, GEARS-style GNNs, and foundation-model fine-tunes are
historical proposals. They are not the active architecture and remain paused
for spending purposes.

## 7. Compute boundary

The 8 GB arm64 Mac is for code, docs, small fixtures, and the Observatory
build. Full panels, Atlas-scale data, official scorer validation, and any
training require external compute and explicit approval.

## 8. Observatory

The Observatory remains the public accountability layer: run IDs, immutable
artifacts, metrics, audit flags, provenance, and generated narration. It is
separate from the inference path and can proceed independently of the
validation bottleneck.

---

## Historical Phase-0 proposal

The text below preserves the original architecture proposal that informed the
first implementation. It is not the current experiment sequence.

### Original input/output contract

Cell-eval compares **two cell × gene AnnData matrices** (`adata_pred` vs
`adata_real`), runs differential expression on each independently, and scores
a panel of metrics. The perturbation identity lives in an **obs column**
(`target_gene` by default), and a `non-targeting` label denotes basal cells.
Gene identity is the **var axis**.

The consequence remains true: the prediction is a generated single-cell
distribution per perturbation plus controls, not just a gene-level delta
vector.

### Original two-layer frame

- **Layer A:** map knocked gene → gene-wise response field, conditioned on
  basal context.
- **Layer B:** draw synthetic post-perturbation cells from target basal cells
  and the response field.
- Ensemble at evaluation, not per-metric.

The original proposal favored a gene-projection/ICL-style Layer A and a
flow-matching Layer B. Those choices were never established as the deployed
architecture.

### Original sequencing

- Observatory Milestone 0;
- install the legacy cell-eval harness;
- run baseline and ceiling checks;
- build sparse then real-resampling baselines;
- add Atlas/Replogle priors;
- explore learned transfer and generative Layer B.

That sequence produced the current historical run set, but the active plan is
now `docs/vcc-two-track-strategy.md` (“VCC strategy — validation first”).
