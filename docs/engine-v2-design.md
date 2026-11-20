# Engine v2 — design

Status: **DESIGN** · Written **2026-11-20** · Owner: udingethe ·
Parent docs: [`vcc-postmortem.md`](vcc-postmortem.md) (why),
[`kytos-roadmap.md`](kytos-roadmap.md) (where it fits), build in public —
run records land on the Observatory as `k2NN-*`.

This document specifies the engine-v2 stack concretely enough that each
layer is independently implementable and independently testable. It is
also drafted to serve as the technical appendix for grant proposals —
each section maps to a deliverable an external reviewer can verify
against the public repo.

## Requirements (what 2026 proved)

From the post-mortem and the winners' published methods:

- **The evidence unit must be a statistic, not a point estimate.**
  Every podium team carried LFC + SE + significance per gene; our pooled
  mean shifts couldn't express "this source is noisy" or "these sources
  disagree."
- **Source breadth is available for free.** FlowState podium'd on
  public data — 222 datasets, ~half bulk. Once the unit is a statistic,
  bulk and single-cell pool trivially.
- **DE-set membership is a first-class estimation problem.** Two-thirds
  of the score (jac/reach/fid/nmae) lives in "which genes actually
  respond," and even the winners over-called 3–20×. Nobody solved this —
  it is the open margin.
- **Calibration targets the scorer's regime.** 400 predicted cells →
  log-pseudobulk; effect sizes must be shrunk to what survives that
  sampling noise.
- **Context adaptation is a tiebreaker** (organizer-measured slope
  0.02–0.13 vs replicate 1.02). Build it last.

## Architecture

Four layers, each with a defined interface so any layer can be
developed and scored independently:

```
┌─────────────────────┐   ┌──────────────────────┐
│ L0  evidence stores │──▶│ L1  meta-analysis    │
│ per-dataset DE stats│   │ weighted consensus   │
└─────────────────────┘   │   + disagreement     │
                          └─────────┬────────────┘
                                    ▼
                          ┌──────────────────────┐   ┌─────────────────┐
                          │ L2  DE-set predictor │──▶│ L3  synthesis   │
                          │ + noise-floor calib. │   │ dual-moment     │
                          └──────────────────────┘   │ (unchanged)     │
                                                      └─────────────────┘
                          (L4 context adaptation — deferred, §6)
```

Interfaces: L0 emits **evidence tables** (§1). L1 consumes them and emits
**consensus estimates** `(lfc_hat, se_hat, tau2, n_sources)` per
target×gene (§4). L2 emits **calibrated effects + DE probabilities**
(§5). L3 consumes `(lfc_cal, de_prob)` per target×gene where the old
generator consumed a delta vector (§7).

## 1. L0 — evidence store schema

One evidence store per source dataset. Unit: **(target, gene, dataset) →
effect estimate + uncertainty + provenance.**

Physical layout (as built in k201):
`/kytos-vol/k201-evidence/<dataset_id>/<run_id>/` with
`manifest.json` + `stats.npz`. Per-dataset dense T×G matrices — within a
dataset the panel axis is measured for nearly every target, so sparsity
lives in *coverage* (which targets a dataset covers), handled by a
`covered` bool per target rather than a long-format table. Same on-disk
convention as the existing k035/k036 stores, so L1 reads them with the
same tooling.

`stats.npz` arrays:

| field | shape | semantics |
|---|---|---|
| `genes` | (G,) str | measured gene symbols, panel axis |
| `targets` | (T,) str | perturbed gene symbols (dataset's own axis) |
| `covered` | (T,) bool | target has estimable stats |
| `lfc` | (T,G) f32 | effect vs controls in the dataset's units + `lfc_kind` flag |
| `se` | (T,G) f32 | standard error (NaN where not estimable) |
| `p` | (T,G) f32 | raw p-value, two-sided |
| `q` | (T,G) f32 | BH-adjusted within (dataset, target) |
| `z` | (T,G) f32 | signed z = sign(lfc)·Φ⁻¹(1−p/2) — unitless, cross-assay |
| `n_voting` | (T,G) i16 | samples contributing to the estimate |
| `kd_eff` | (T,) f32 | knockdown-efficiency proxy (−self lfc, clip 0) |

`manifest.json`: dataset_id, citation, context (cell line / tissue /
disease), assay (sc CRISPRi / sc CRISPRko / bulk CRISPRi / siRNA /
shRNA / compound), chemistry (10x Flex, L1000, …), n_cells, depth
median, covariates available, license, download URI, extraction
protocol + date, control semantics (NTC guides vs untreated), and
`lfc_kind` (`log1p-sc`, `log2fc-bulk`, `zscore`) — **units are never
silently mixed**; CD4 publisher log2FC vs computed log1p shifts is the
existing precedent (`tools/consensus_deltas.py` docstring).

Why z as the cross-assay unit: LFC scales differ systematically between
bulk and single-cell (dynamic range, normalization), but significance
does not. z lets bulk vote on *which* genes respond while sc sources set
magnitude — this is the design decision that makes bulk harvestable
without pretending bulk LFCs are single-cell LFCs.

Migration from existing stores (§A.1 of roadmap): the k036 per-sample
X-Atlas stores (`pos_count`, `neg_count`, `mean_sample_delta`,
`e2_sample_delta`, `n_samples_voting`) already contain everything a
per-sample Welch-t needs — sample-count votes, mean and second moment of
per-sample deltas. The L0 schema is a generalization, not a rebuild.

## 2. Corpus inventory & harvest order

Ordered by (coverage × signal quality ÷ effort). Each harvest lands as
an L0 store + Observatory run record.

**Phase 0 — re-extract what we own (weeks 0–2).** Replogle K562, X-Atlas
HCT116 + HEK293T, CD4, 2025 VCC validation H1. Already on the panel axis;
the k036 machinery generalizes directly. Jurkat re-admitted *as a source*
with its own weight — the 2026 exclusion was about the consensus recipe,
not the data.

**Phase 1 — genome-wide single-cell screens (weeks 2–6).**
scPerturb's 44 harmonized datasets (sanderlab portal, .h5ad, licenses on
file), Adamson, Nadig/Replogle-Nadig, HipSci, VIPerturb-seq, IGVF,
X-Atlas/Orion remainder, McFaline-Figueroa U-87MG kinome screen
(context-relevant: 21 test-panel targets), Parse-PBMC, and — as a
held-out reserve — Tahoe-100M (harvest last so it can serve as clean
evaluation).

**Phase 2 — bulk screens (weeks 6–12).** ENCODE K562/HepG2 KDs, LINCS
L1000 (consensus signatures have p-values already), PerturbAtlas,
KnockTF, ARCHS4. z-unit only; no LFC magnitude contribution.

**Phase 3 — long tail / challenge-relevant.** Whatever the 2027 panel
implies once targets are known; the harvest order re-ranks itself from
target coverage like k039 did.

Per-dataset effort estimate: 1–2 days each for sc .h5ad sources with
existing extraction paths; 2–4 days for bulk portals with idiosyncratic
formats. Phase 0+1 ≈ 50–60 stores; Phase 2 ≈ 100+; total plausibly the
same ~200 FlowState used — now carrying statistics instead of votes.

## 3. Per-dataset estimation

Per dataset, estimate `lfc, se, p` per target×gene vs its own controls:

- **sc screens with replicates/samples**: covariate-adjusted negative-
  binomial or quasi-likelihood regression where the design allows
  (edgeR/DESeq2-style; per-sample pseudobulk for datasets with true
  biological replicates — pseudoreplication is the known failure mode
  and the k036 vote stores are the guard against it). Where covariates
  are thin, per-sample Welch-t on log1p means — what k036 already
  computes implicitly.
- **Bulk screens**: take the published DE tables directly (LINCS/ENCODE
  ship LFC+SE+p); where only counts exist, standard voom/limma.
- **Centering**: per dataset, center LFCs across perturbations to
  correct screen-wide inflation (BioInsight's step; our
  common-response-centering was the same idea at the delta level).

Non-negotiable invariants: every store keeps `lfc_kind` and `se`
defined; a store without SEs is a defect to fix, not a variant to ship.

## 4. L1 — precision-weighted meta-analysis

Per (target, gene), combine across the datasets that measured it:

- **Core**: random-effects model — inverse-variance weights within
  study, between-study variance `tau²` estimated (DerSimonian–Laird to
  start; REML if bias shows). Outputs `lfc_hat, se_hat, tau2, I²,
  n_sources`.
- **Weight multipliers** (fitted, not hand-set): dataset noise level,
  KD efficiency, control-cell expression similarity to the prediction
  context, n_cells, assay-type prior (sc > bulk for magnitude; equal
  for direction votes), per-study influence cap (X-team used caps;
  prevents one huge atlas dominating).
- **Disagreement is signal**: `tau²` and vote disagreement feed the
  DE-set predictor — targets where sources genuinely conflict are
  exactly where shrinkage should be strongest.
- **Fitting protocol**: hyperparameters fit by leave-one-line-out on
  our own held-out contexts (the k041 machinery repurposed as a
  fitting harness — oracle selection failed as a *strategy* but is the
  right *estimator* of transfer weights).

## 5. L2 — DE-set predictor + calibration

The layer we never built. Two outputs per target×gene:

1. **`de_prob`** — probability the gene is truly DE in the target
   context. Features: `z` per source, cross-source vote count, `tau²`,
   control-expression level (unexpressed genes can't be DE),
   target-gene degree in prior networks (mild). Model: gradient-boosted
   trees (X-team's choice — tabular, CPU, interpretable), trained on
   held-out contexts so it never sees the line it scores.
2. **`lfc_cal`** — calibrated effect size: `lfc_hat` shrunk toward zero
   as a function of `se_hat` and the 400-cell pseudobulk sampling
   noise floor of the evaluation regime — the noise-floor calibration
   X-team described. Significance threshold set so predicted DE counts
   land near the measured regime (~22–44/target median from the
   wrap-up), not by fixed p-cutoff.

## 6. L4 — context adaptation (deferred)

Only after L0–L3 post real benchmark numbers. Options in order of
expected value: SVD of cross-dataset response patterns + ridge
correction from control expression (BioInsight); per-gene context heads
(FlowState's strength/direction/magnitude); control-cells-as-prompt
conditioning. Organizers' slope measurement caps the prize at
~0.1 of line-specificity — build it for the tiebreaker, not the thesis.

## 7. L3 — synthesis interface

Keep `src/kytos/models/dual_moment.py` — cell generation was
competitive (organizers priced it at ±0.004) and ours is engineered
(streamed, library-capped, seeded). Interface change: the generator
consumes `(lfc_cal, de_prob)` per gene instead of a dense delta —
non-DE genes get zeroed cleanly instead of carrying residual deltas
(the implicit-DE-knob failure mode the post-mortem names).

## 8. Evaluation harness

- **Pinned scorer**: cell-eval2, locally, against held-out contexts
  where we have ground truth — 2025 VCC H1 splits, Replogle holdouts,
  and eventually Tahoe-100M contexts held out of the corpus (§2
  reserves it).
- **LOLO protocol**: every layer's hyperparameters fit by
  leave-one-line-out; reported metrics always name the held-out set.
- **Reference points** (VCC 2026 test panel, wrap-up):

  | | our 2026 val | podium band | target (public-data path) |
  |---|---|---|---|
  | PDS | 0.62 | 0.73–0.84 | ≥0.75 |
  | MSE | 0.02 | 0.36–0.68 | ≥0.30 |
  | NMAE | 0.09 | 0.30–0.44 | ≥0.25 |
  | FIDELITY | −0.02 | 0.07–0.19 | ≥0.10 |
  | REACH | 0.06 | 0.31–0.43 | ≥0.25 |
  | JACCARD | 0.001 | −0.002–0.067 | ≥0.05 (≈field best) |

  Interim sanity target before leaderboard comparisons mean anything:
  predicted DE-count median near the measured 22–44/target, and
  reach-curve fidelity above ~25 genes.
- **Anti-overfit rules carry over**: no context-fit constants without a
  held-out receipt; pre-declared component predictions on probes;
  scores are observations, targets are the LOLO harness.

## 9. Milestones (k2NN run plan)

| Run | Artifact | Done when |
|---|---|---|
| k201 | `k201-evidence/{hct116,hek293t,k562,cd4,h1}/` on `kytos-vcc` (L0 phase 0) | schema validates; self-KD sign audit; `tools/modal_k201_validate.py` |
| k202 | Corpus inventory doc (`docs/evidence-corpus-inventory.md`) + harvester (`tools/modal_k202_harvest.py`, shared lib `tools/evidence_l0.py`) | manifest-driven catalog; one new source lands per invocation |
| k203 | Phase-1 sc harvest (10–20 stores) | each store passes invariant checks |
| k204 | L1 meta-analysis v0 (IV-weights only) | LOLO-consistency: held-out line reconstruction |
| k205 | DE-set predictor v0 | DE-count median in 22–44 band on held-outs |
| k206 | L3 interface swap (delta → calibrated effects) | cell-eval2 score on held-out ≥ k040-equivalent |
| k207+ | weight learning, bulk harvest, context layer | per phase gates |

Each lands as an Observatory run — same provenance contract as the
k-series (facts.json + flags + reproduce command).

## 10. Explicit non-goals

- No foundation model training (Arc State weights suffice as oracle).
- No private-data acquisition — the program's premise is public data
  done properly.
- No leaderboard probing during development — standing benchmarks only.
- No context-adaptive components before L0–L3 have measured baselines.

## 11. Grant-appendix mapping

- **EOSS**: §1 + §2 as "infrastructure" (a public evidence layer is
  exactly EOSS scope); Observatory as demonstrated community interface.
- **AI-Meets-Biology GPU RFA**: §5 predictor + §6 heads as the
  compute line item.
- **NIH PAR-26-040**: §4 + §8 as the methods + evaluation plan;
  the embargoed diagnostics tree as preliminary data.
- **Fast Grants / New Science**: §3 + the post-mortem as
  "unusually concrete plan + demonstrated execution."
