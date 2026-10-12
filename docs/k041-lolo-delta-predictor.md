# k041 — leave-one-lineage-out (LOLO) delta predictor spec

Status: **executed at rung 1, axis CLOSED** (2026-10-12). The oracle
mixing bound (rung 1) beat fixed consensus ~everywhere but best-single-
source ≈ oracle — the win is selection, not blending — and the basal
similarity follow-up showed **no feature exists to select with**
(pairwise ρ ≈ 0; only the same-assay-family hct116↔hek293t pair obeys
basal distance; same-lineage jurkat rest↔stim deltas don't transfer).
Per the promotion rule below, rungs 2-3 are not funded. Exact numbers:
`experiments/_embargoed/k041-lolo/`. The document is kept for the
reasoning trail.

## Why now (what changed since the k014/k033 negative results)

Both prior learned-model attempts failed for structural reasons, not because
"learned signatures" are dead:

- **k014 conditional MLP**: trained on 9,906 samples but only **47 paired
  cross-context rows** — the model never saw how a delta changes across
  lineages. Held-out cosine below the identity transplant.
- **k033 State ST**: trained on a *single* lineage (Replogle K562). It
  learned a K562 model; Gate B showed its deltas are uncorrelated with the
  measured hESC responses (pds collapsed ~5% of reference). Nothing in the
  objective taught cross-lineage transfer.

Since then the data situation changed: the k034 genome-wide delta stores
give **five measured lineages** on the same 18,533-gene axis —

| source | targets | per-sample stats |
|---|---:|---|
| k562 (Replogle GWPS) | 9.9k | pooled only |
| hct116 (X-Atlas) | 18.3k | k036: 109 voting samples |
| hek293t (X-Atlas) | 18.3k | k036: 223 voting samples |
| jurkat | ~18k | pooled only |
| cd4 | 7.3k | pooled only |

That is ~60-70k (target × lineage) delta observations — orders of magnitude
more paired cross-lineage signal than k014 had, with k036 sign-agreement as
per-(target,gene) training weights.

## The actual deliverable

Not "a better delta" in the abstract — a **context-conditioned source-mixing
model** whose actionable output for the Oct-22 test set (three *unknown*
cell lines) is: given a new line's basal-state features, predict the source
combination whose consensus best approximates that line's response. That is
the one artifact that directly addresses unseen-line generalization — the
property the final test set actually measures.

## Model ladder (build bottom-up; each rung must beat the one below)

1. **Per-target nonnegative ridge (closed form).** For each target `t` in
   held-out lineage `L`, fit `delta_L[t] ≈ Σ_s w_s[t] · u_s[t]` over the
   other lineages' unit-normalized deltas, `w ≥ 0`. Upper bound on what
   source-mixing can ever deliver; also the honest ablation for "do we even
   need features". Free (pure numpy).
2. **Global linear map, lineage-conditioned.** `delta_pred[t,L] =
   W · f(t,L)` where `f` concatenates the available source deltas for `t`
   (masked) + a lineage embedding vector `z_L` (basal expression of
   marker/DE genes, or a learned 16-d code). One small weight matrix;
   hours of CPU.
3. **Small MLP.** inputs: masked source deltas (optionally PCA-reduced to
   ~512 components) + `z_L` + target embedding (gene2vec-style or
   random-projection baseline); output: predicted delta in lineage `L`.
   Single A10G, well under $10.

## Evaluation protocol — leave-one-lineage-out

For each lineage `L` in turn: train on the other four, predict `L`'s
deltas, score:

- `cos(pred_L[t], delta_L[t])` vs the same cosine for the **transplanted
  consensus mean** (the thing we ship today) — the predictor must beat the
  transplant baseline on *held-out* lineages, all of them, by a clear
  margin. In-sample or same-lineage wins do not count (k033 lesson).
- Weighted version: cosines weighted by k036 sign-agreement where available.
- Exact values → `experiments/_embargoed/k041-lolo/`.

**Promotion rule:** a rung earns GPU spend for the next rung only if it
beats the transplant consensus on every held-out lineage, median cos
margin ≥ the rung's noise floor. If the per-target ridge (rung 1) cannot
beat transplant, the axis is dead — stop, do not escalate to the MLP.

## If it passes

1. Re-fit on all five lineages → produces the mixing/conditioning map.
2. For Oct 22: featurize the three test lines' basal states, predict
   per-lineage source mixes → per-context consensus deltas → existing
   champion generator. The deltas npz stays the submission contract —
   `run_k027_dual_moment_submit.py` is unchanged.
3. Gate: local Gate B variant + one probe slot if band clears the
   pre-declared margin.

## Budget & staging

- All inputs already on `kytos-vol` (k034-final-prep deltas, k036 stats,
  context basal vectors). No new extraction.
- Rungs 1-2: Modal CPU or VPS, <$1.
- Rung 3: one A10G session, cap $10; abort if dataloader/starvation issues
  recur (k033 lesson: uncompressed parts).
- Total planned spend ≤ ~$15 of the ~$50 — remainder reserved for a second
  probe submission or an Oct-22 buffer.

## Explicitly out of scope

- **Generative cell models** (conditional diffusion/flow over cells): the
  leaderboard component gaps (mse/fid/reach) say this is where the top-10
  gap actually lives, but it is a $50-200+ build with days of iteration —
  not fundable. Revisit only if the LOLO predictor transfers cleanly AND
  budget appears.
- Re-extracting any source; adding new lineages (audit closed, k039).
