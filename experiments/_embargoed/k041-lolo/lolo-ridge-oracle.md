# k041 rung 1 — LOLO source-mixing oracle (2026-10-12)

Method: `tools/modal_k041_lolo_ridge.py` on Modal CPU. For each held-out
lineage L and each target covered by L plus >=1 other source, per-target
NNLS over the other lineages' unit deltas (oracle — weights see the
held-out delta) vs the fixed champion-weight consensus over the same
available sources. 19,432 union targets; per-target median 3-4 available
sources.

## Results (median cosine to held-out measured delta)

| held-out | n | oracle ridge | fixed consensus | best single source |
|---|---:|---:|---:|---:|
| hct116 | 18,293 | 0.267 | 0.124 | 0.255 |
| hek293t | 18,310 | 0.278 | 0.123 | 0.263 |
| k562 | 9,751 | 0.100 | 0.030 | 0.092 |
| jurkat_rest | 217 | 0.133 | **-0.020** | 0.130 |
| jurkat_stim | 17,417 | 0.045 | **-0.005** | 0.043 |
| cd4 | 7,262 | 0.044 | 0.025 | 0.039 |

oracle-beats-consensus share: 96-99.9% everywhere.

## Reading

1. **The mixable ceiling is real but modest.** Even the oracle tops out at
   ~0.27 median cos (epithelial pair) and ~0.05 for blood lineages. Learned
   source-mixing cannot exceed this on unit-normalized pooled deltas (the
   absolute floor is set by per-source noise as much as by biology).
2. **best-single ~= oracle ridge almost everywhere.** The oracle's gain
   over fixed consensus comes mostly from *source selection*, not
   blending — one right source captures nearly all available signal. The
   deployable model simplifies to "pick the right lineage to transplant
   from" (or a heavily concentrated mix), not smooth weighting.
3. **Fixed consensus is anticorrelated on held-out Jurkat arms**
   (median cos ~ -0.02/-0.005). If an Oct-22 test line is Jurkat-like,
   today's fixed-weight consensus is not just weak — it is slightly
   harmful on median. Source selection conditioned on the test line's
   basal state is therefore a real, defensible Oct-22 lever.
4. Oracle inflation caveat: NNLS fitting to a noisy y mechanically beats a
   fixed vector; the unbiased evidence for "selection matters" is
   best-single >> consensus, which holds on every arm.

## Decision for rungs 2-3

A neural mixing model is NOT justified by these numbers — with 6 lineage
states, the conditioning question is "does basal-state similarity predict
which source transfers best", answerable by direct lookup, not an MLP.
Next cheap step instead: compute pairwise source-basal similarity vs
measured best-source transfer; if basal similarity ranks the best source
top-2 on held-out arms, a basal-similarity-weighted consensus becomes the
Oct-22 source-weighting rule. Cost: one more small Modal CPU run.

GPU spend so far: ~$0.30 total (this run + sagr build). Remaining ~$49.

## Rung 1b follow-up: basal similarity does NOT predict transfer (2026-10-12)

`tools/modal_k041_basal_transfer.py`: pairwise source basal vectors (full-axis
pearson + spearman on top-2000 variable genes) vs measured per-(s,L) transfer
cosines.

- Global Spearman(basal_sim, transfer_cos) over 30 ordered pairs: **-0.04**
  — no relationship.
- The only pair where basal-nearest = transfer-best: hct116 <-> hek293t
  (basal ~0.88, transfer ~0.24) — the same-assay-family pair. k562 is nearly
  as basal-close (0.81-0.83) but transfers ~0.03.
- Jurkat arms share a basal vector (sim 1.0) yet cross-state transfer is
  ~0/negative (jurkat_rest n=217 is also the noisiest arm — caveat).
- cd4: basal-farthest sources (hek293t, sim 0.09) transfer best (0.028);
  basal-nearest jurkat arms transfer ~0 — a complete inversion.
- Contexts vs sources (spearman, top-var genes): ctxA leads hek293t 0.61 /
  hct116 0.53 / k562 0.48 (note: differs from the discriminative-gene read in
  k039 which had a Jurkat basal leading A — full-axis basal similarity is
  dominated by housekeeping expression and is a different, blunter measure).
  ctxeval leads hek293t/hct116/k562.

**Consequence:** the conditionable signal does not exist — basal state cannot
select the transferring source, oracle mixing only modestly beats fixed
consensus, and even same-lineage cross-state deltas don't transfer. The
learned/conditioned source-mixing axis is CLOSED at rung 1 per the promotion
rule (no feature predicts the winner; ceiling low). Remaining Oct-22 delta
lever = the fixed consensus itself (hct116+hek293t already integrated). All
remaining score risk sits on the generation side.
