# k015+ Plan: Path to Top 100

> **STATUS 2026-09-20: HISTORICAL — planning doc kept as the record of options
> considered, not the active plan.** Outcomes since: k020/k020b regressed on
> the leaderboard and k015 also regressed, but implementation and coverage
> confounds mean those results do not falsify transfer learning as a class.
> The k021 diagnostic is exploratory and does not establish a
> signature/modeling headroom split or a `kd_std` mechanism. The active plan
> is `docs/vcc-two-track-strategy.md` (“VCC strategy — validation first”);
> canonical experiment interpretation is `experiments/README.md`.

Status: ~~**planning**~~ (2026-09-18, post-k014 negative result) — **superseded, see banner above**

## Where we are

| Metric | Champion (k011 x1.7) | Top 200 | Top 100 | Gap to close |
|--------|---------------------|---------|---------|--------------|
| overall | +0.0596 | +0.134 | +0.158 | +0.098 |
| pds | 0.339 | ~0.52 | 0.699 | +0.36 |
| nmae | -0.076 | ~+0.13 | +0.145 | +0.22 |
| fid | -0.006 | ~-0.003 | -0.019 | ~solved |

The gap is dominated by **pds** and **nmae**. Both require better per-target
delta predictions.

## Why k014 (conditional MLP) failed

- Only 47 paired K562→hESC examples → no cross-context signal to learn
- Model converged to near-zero predictions (mag_ratio 0.35)
- Identity baseline (raw K562 transplant) was 3× better
- **Lesson**: context conditioning alone can't compensate for lack of
  structural priors about gene-gene relationships

## Strategy: Three parallel levers

### Lever 1: GEARS-style GNN (Track 2, Nebius) — highest ceiling

**Core idea**: Train a graph neural network on gene perturbation data,
using the STRING interaction graph as inductive bias. The GNN learns that
perturbing gene X affects genes in X's neighborhood, enabling generalization
to unseen targets.

**Architecture sketch**:
```
Input: target gene t, context basal vector c
1. Gene encoder: t → embedding z_t (learned, 128d)
2. GNN propagation: message-pass on STRING graph, seeded at z_t
   - K hops (K=2-3), aggregation = mean or attention
   - Produces perturbed neighborhood representation h_t
3. Context adapter: (h_t, c) → context-conditioned representation
   - Simple: concatenate + MLP
   - Better: FiLM conditioning (scale+shift from context)
4. Delta decoder: context-conditioned repr → 18,533-dim delta vector
   - Low-rank: 18533 ← rank-64 ← hidden
```

**Training data**:
- 9,869 Replogle K562 targets (pseudobulk deltas) — primary supervision
- 47 Atlas hESC paired targets — secondary supervision (context transfer)
- STRING graph (score ≥ 0.7, ~2,393 essential-screen targets as additional
  training signal if we can extract their deltas)

**Why this should beat k014**:
- Graph structure provides inductive bias for unseen targets
- 9,869 training examples (vs 47 paired) give much more supervision
- GNN can learn that "genes in the same pathway respond similarly"

**Expected improvement**: If GEARS achieves cosine ~0.3-0.4 on held-out
targets (literature reports ~0.3-0.5 on similar tasks), that's 2-3× better
than identity baseline. Combined with proper magnitude calibration, this
could push pds toward 0.5-0.6 and nmae toward positive territory.

**Implementation plan**:
1. Extract STRING subgraph for the ~18,533 genes in our panel
2. Build PyTorch Geometric data structure (edge_index, node features)
3. Implement GNN (start with 2-layer GCN/GAT, ~1M params)
4. Train on K562 deltas, evaluate on held-out targets
5. Add context conditioning, fine-tune on paired data
6. Export prediction_deltas.npz → Modal builder → submit

**Estimated effort**: 1-2 days of focused implementation on Nebius VM.

### Lever 2: Per-target adaptive scaling (Track 1, Modal) — quick win

**Observation**: Global delta_scale=1.7 is optimal on average, but individual
targets likely need different scales. Some targets have strong effects
(needing less amplification), others weak effects (needing more).

**Approach**: Learn a per-target scale factor based on features:
- STRING degree (hub genes may have larger effects)
- Basal expression level in target context
- Delta magnitude in source context (K562)
- Number of DE genes in source

**Implementation**: Simple linear regression or lookup table mapping
target features → optimal scale. Train on the 47 paired targets where we
know the true hESC delta.

**Expected improvement**: Modest (+0.01-0.03 overall) but free — runs on
Modal with existing infrastructure.

### Lever 3: Better neighbor imputation for 28 uncovered targets (Track 1)

**Current**: Top-5 STRING partners, score-weighted mean of partner deltas.
**Improvement options**:
- Use more partners (top-10, top-20) with decay weighting
- Weight by partner's own prediction confidence
- Use GNN predictions (from Lever 1) as the primary source for these 28
- Ensemble: blend neighbor mean with global mean

**Expected improvement**: Small directly (only 28/300 targets affected),
but removes a systematic weak point.

## Sequencing

| Step | Track | Effort | Expected gain | Dependency |
|------|-------|--------|---------------|------------|
| k015: Per-target scaling | 1 | 2-4 hr | +0.01-0.03 | None |
| k016: GEARS GNN v1 | 2 | 1-2 days | +0.05-0.10 | Nebius VM |
| k017: GEARS + context | 2 | +1 day | +0.02-0.05 | k016 |
| k018: Ensemble/blend | 1+2 | 4 hr | +0.01-0.02 | k016 |

**Realistic path to top 200 (+0.134)**: k015 + k016 should get us there.
**Path to top 100 (+0.158)**: Need k016 + k017 + k018, or a breakthrough
in context transfer (scGPT fine-tune).

## Decision criteria

- Submit k016 result only if held-out cosine > 0.20 (beats the identity
  baseline by a meaningful margin) AND magnitude ratio is in [0.7, 1.5].
- Submit k015 (per-target scaling) if it improves nmae without hurting pds.
- If GEARS cosine < 0.20 after reasonable tuning, pivot to scGPT fine-tune.

## Data requirements for GEARS

| Data | Source | Size | Status |
|------|--------|------|--------|
| STRING graph | repo (k007) | ~20 MB | ✅ local |
| K562 deltas | Modal volume | 698 MB | ✅ staged |
| Atlas hESC deltas | Modal volume | 5.1 MB | ✅ staged |
| Context basals | Modal volume | small | ✅ in paired npz |
| Gene embeddings | learned | — | train from scratch |

All data is already available. No new downloads needed.
