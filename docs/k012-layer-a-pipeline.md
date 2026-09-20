# k012 — learned Layer A implementation spec

> **STATUS 2026-09-20: HISTORICAL PROPOSAL — not the active plan.** The LOO
> result was a proxy-only negative and does not justify implementation work
> before the validation gates in `docs/vcc-two-track-strategy.md` pass. Kept
> as design history.

Companion to `docs/k012-learned-layer-a.md` (the "why"). This is the "how" —
concrete pipeline for the paired-signature transfer model proposed during the
former Track 1 plan.

## Data extraction (Modal job, ~10 min)

Inputs already on `kytos-vcc` volume / public sources:

- 2025 Atlas `adata_Validation.h5ad` — 50 per-target deltas already
  computed by the existing builder (`atlas=50` in the combined-prior log).
- Replogle K562 GWPS bulk — 9,866 pseudobulk deltas.
- VCC 2026 controls — per-context basal expression vectors
  (18,400 cells × 18,533 genes each).

Produce `paired_transfer_train.npz`:

- `targets`: the ~46–50 genes present in *both* Atlas and Replogle delta
  sets (the training set).
- `delta_src[t]`: K562 delta for target t (gene-intersected).
- `delta_dst[t]`: Atlas delta for target t (same gene order).
- `basal_src`, `basal_ctx{A,B,C}`: control-mean expression per context.
- Keep the full 18,533-gene order; mask non-intersected genes rather than
  re-indexing (keeps the produced delta drop-in compatible with
  `build_context_predictions`).

## Model classes (fit in-corpus, ordered simplest-first)

All classes map `delta_src -> delta_hat_ctx` and are trained on the paired
targets only:

1. `GlobalScalar`: s = <d_dst, d_src> / <d_src, d_src>, pooled over all
   pairs and genes. **Baseline — everything must beat this.**
2. `PerGeneShrunk`: s_g per gene, shrunk toward s by inverse-variance
   weighting across the ~50 pairs (empirical-Bayes style).
3. `BasalRatioModulated`: delta_hat_ctx(g) = s · d_src(g) ·
   f(basal_ctx(g) / basal_src(g)) — tests whether transferred magnitude
   tracks the basal-expression ratio between contexts.
4. `LowRankMap`: delta_hat_ctx = U (Vᵀ d_src), rank 8–16, ridge —
   pathway-level transfer. Highest capacity; needs the strongest LOO
   evidence to ship.

Optional context-conditioning: each class can take per-context basal
vectors, so the *same* source delta transfers differently into A/B/C —
this is what "learned Layer A" means vs. today's raw transplant.

## Validation harness (no leaderboard feedback)

- **LOO over paired targets**: fit on 49, predict the held-out Atlas
  delta; report cosine similarity, DE-logFC Pearson on true-DE genes,
  and ||delta_hat||/||delta_true|| (magnitude calibration — the axis k011
  proved is load-bearing).
- **Acceptance rule**: ship only if the winner beats `GlobalScalar` on
  LOO cosine by a clear margin (>0.05 mean) — else the scalar is the
  model and k011 already probes it.
- No metric ever computed against leaderboard scores; submission comes
  only after the in-corpus winner is frozen.

## Integration point

`build_context_predictions` (tools/run_k007_neighbor_prior.py) gains a
`transfer_fn` hook applied to real/Replogle deltas before delta_scale —
fallback and neighbor tiers keep today's behavior initially. Prediction:

```python
delta = transfer_fn(delta_src, basal_ctx)   # new
delta *= delta_scale                        # existing
```

This composes with the k011 finding: learned transfer replaces (or
shrinks) the scalar we currently apply blindly.

## Deliverables

1. `tools/extract_paired_transfer.py` — Modal-side extraction script.
2. `src/kytos/models/transfer.py` — the model classes + LOO harness
   (unit-testable locally on the small .npz).
3. `tools/run_k012_transfer.py` + `tools/modal_k012_transfer.py` —
   full-panel builder reusing the k011 runner shape.
4. LOO report committed as `experiments/k012-transfer-loo/facts.json`
   *before* any submission decision.

## Honest limits

- ~50 training pairs is thin — classes 2–4 must show real LOO gains to
  justify capacity. Expected outcome may be "scalar + basal modulation
  only", which is still a principled win.
- Atlas is H1 hESC, not the 2026 contexts — the learned map transfers
  K562→hESC; applying it to A/B/C assumes the direction of context
  difference generalizes. Basal-ratio conditioning is the hedge.
- If LOO says no class beats the scalar, that is a publishable negative
  and we pivot effort to lineage-matched corpora (Track 1 item 3).
