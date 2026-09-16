# k012 — learned Layer A: context-conditioned signature transfer

Status: **design** (not yet implemented). Written 2026-09-16 after the
k009/k010 mean-shape experiments isolated *applied delta magnitude* as the
load-bearing score axis and marker analysis revealed the 2026 contexts are
not H1 hESC.

## Why this is the lever

Leaderboard component analysis (984 published entries, 2026-09-16):

| | us (best +0.051) | #100 (+0.158) | #1 (+0.292) |
|---|---|---|---|
| pds | 0.336 | 0.699 | 0.830 |
| nmae | +0.004 | +0.145 | +0.220 |
| fid | -0.111 | -0.019 | +0.085 |
| reach | 0.091 | 0.124 | 0.347 |

The gap to top-100 is concentrated in `pds` and `nmae` — signature accuracy
metrics, not distribution shape. Lookup + transport has a ceiling; crossing
it needs signatures that are both strong and context-appropriate.

## What we learned about the contexts (2026-09-16)

The control h5ads carry no cell-type metadata (only `target_gene=non-targeting`,
`context`, `ntc_id`), but marker-gene rank analysis of basal expression:

- **Context A**: T-cell markers high (CD3D/CD3E/CD8A/TRAC rank ~0.84) —
  Jurkat-like
- **Context B**: fibro/epithelial + RPE1-ish elevated (THY1/VIM ~0.63,
  S100A6/TUBA1A ~0.71) — fibroblast/RPE1-like
- **Context C**: intermediate, epithelial-ish, less resolved

Implication: the signatures we transplant (K562 GWPS, and Atlas H1 hESC for
4/300 targets) are being applied to *different lineages*. The transfer error
is systematic, which is consistent with the leaderboard evidence that
applied delta magnitude is under-scaled (champion's ~40% clipped-mean
inflation is load-bearing — borrowed signatures are too weak).

## Options, in order of expected value

### 1. Lineage-matched public corpora (cheapest, highest ceiling)

Before learning a transfer map, check whether nearer-lineage Perturb-seq
exists for the inferred contexts:

- **Context B (RPE1-like)**: Replogle RPE1 GWPS arm is already downloaded
  once (figshare 35774443-adjacent; ~95 MB pseudobulk). It was useless for
  the 28 unscreened genes but covers ~9,871 genes — for the 2026 panel it
  may cover most targets with *in-context-lineage* signatures. If context B
  is really RPE1, this alone could lift a third of the panel.
- **Context A (Jurkat-like)**: Schraivogel TAP-seq targeted essential genes
  in Jurkat; Schmidt et al. 2022 did genome-scale Perturb-seq in primary
  T cells. Worth a coverage check for the 300 targets.
- **Context C**: unresolved lineage; hold.

Validation: correlation between context basal expression and candidate
lineage reference profiles (e.g., K562 vs RPE1 vs Jurkat controls from the
same Replogle data), not just marker ranks.

### 2. Paired-signature transfer learning

Training set: targets screened in *both* K562 GWPS and Atlas H1 hESC
(~46–50 paired deltas). Learn f: delta_K562 -> delta_context, validate
leave-one-out on the pairs. Candidate classes, simplest first:

- **Global scalar**: s = <d_ctx, d_k562>/<d_k562,d_k562> pooled. Baseline;
  k011 probes this axis directly.
- **Per-gene scalar with shrinkage**: s_g shrunk toward global s by
  per-gene variance across the ~50 pairs.
- **Basal-ratio modulation**: scale each gene's transferred delta by
  f(basal_ctx(g)/basal_src(g)) — test whether delta magnitude tracks
  basal expression ratio between contexts.
- **Low-rank linear map**: delta_ctx = U (V^T delta_K562), rank ~8–16,
  ridge-regularized — captures correlated pathway-level transfer.

Selection criterion: LOO cosine similarity and DE-logFC recovery on the
paired set, then a small panel submission only if the winner clearly beats
the global scalar.

### 3. Residual covariance (Layer B) — orthogonal

The fid -0.111 residual on the champion is off-direction structure: fit
per-target or pooled residual covariance of Atlas perturbed cells after
removing the delta-mean, sample correlated residuals in transport.
Independent of Layer A and can stack.

## Compute / cost

- Pair extraction + LOO validation: small (subset of Atlas + GWPS bulks),
  Modal ~minutes.
- If lineage-matched corpus found: one Modal build, same pipeline —
  swap the prior source per context (build_context_predictions already
  dispatches per-target; needs a per-context delta-source dict).

## Risks / honest notes

- Context identity is inferred from ~30 marker genes — could be wrong.
  Verify with broader lineage scoring (e.g., against bulk reference
  expression) before investing in lineage-matched corpora.
- ~50 training pairs is thin; transfer classes must stay low-capacity.
  Leaderboard-overfit risk: tune on LOO-in-corpus, not on submissions.
- Final eval is 3 *new* unseen cell lines — whatever transfer we learn must
  condition on the *provided control cells*, not on identity guesses.
  Design for "infer context state from its controls" from the start.
