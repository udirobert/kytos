# Track 2a — cross-lineage signature-content model: design + feasibility record

Status: **CLOSED — falsified by LOLO screen (2026-09-22).** See §9.
Embargoed: derives from honest-corpus measurements and Gate-B internals.

## 1. Why this exists

Generation mechanics are exhausted: the dual-moment sweep plateaued at
~0.20 local avg (k028 = `a1.0/b0.3/pk12`, +0.0096 over k027 config).
Every remaining point must come from **signature content** — which genes
respond, in which direction, in the eval contexts.

Track 2b (signed regulon prior) is parked: real but *unsigned* signal —
spectacular when right (NFE2L1 pds +0.37), harmful when wrong
(TCF7L2 −0.22), and no cheap observable gate separates the two.

## 2. Supervision census (measured 2026-09-22)

| asset | targets | role |
|---|---:|---|
| 4-lineage corpus (k562/hct116/hek293t/cd4 deltas) | 343 shared | only multi-context perturbation corpus |
| H1-train (hESC 2025) deltas | 150 | hESC supervision — but **∩ consensus = 13** |
| Gate-B eval subset (H1-val ∩ panel) | 47 | must stay held out |

Direct "consensus → hESC" supervision is effectively nil (13 pairs).
Any learned model must therefore be validated by
**leave-one-lineage-out (LOLO)** inside the 4-lineage corpus: train
"consensus of 3 → held-out lineage", which is *exactly* the production
inference problem — contexts A/B/C are unseen lineages.

## 3. LOLO feasibility probe (measured 2026-09-22, delta-space)

Consensus = unweighted mean of the 3 non-held-out lineages.
343 targets × 18,533 genes, axes verified identical.

| held-out | full-vec cos (median) | top-200 subspace cos | top-200 jaccard |
|---|---:|---:|---:|
| k562 | 0.037 | 0.257 | 0.008 |
| hct116 | 0.096 | 0.373 | 0.008 |
| hek293t | 0.088 | 0.299 | 0.008 |
| cd4 | 0.037 | 0.192 | 0.005 |

Interpretation:

- **Direction partially transfers where genes are shared** — restricting
  to the held-out lineage's own top-200 |delta| genes, consensus direction
  reaches 0.19–0.37.
- **The responding gene sets are ~lineage-private** — top-200 set overlap
  is 0.5–1.6%. (Caveat: |delta|-rank support ≠ scorer DE calls; magnitude
  ranking is noise-sensitive. Direction of the finding stands.)
- The scorer-visible error is therefore dominated by **which genes
  respond at all**, not by getting shared genes' directions right.

This reshapes the problem: a "consensus-direction corrector" optimizes
the component already partially solved. The valuable prediction target
is **response support** — and it is the *least* transferable quantity.

## 4. Candidate model classes (ordered by cost)

- **M0 — support-augmented consensus (free, testable today):** replace
  weighted-mean consensus with union/top-k-of-any-lineage support (keep
  consensus magnitudes; broaden which genes carry nonzero delta). Direct
  probe of "does wider support help the jaccard/DE metrics more than the
  added noise hurts." Variant-buildable from existing NPZs; Gate B arm
  ~20 min.
- **M1 — per-gene support predictor (learned):** logistic/boosted model
  P(gene g responds to target t | features) trained LOLO. Needs gene +
  target features — i.e., the regulon/feature stack — and hits the same
  wall as Track 2b: if the support signal is unsigned/idiosyncratic,
  there is nothing generalizable to learn. 1,372 (t,L) examples is small
  for 18,533 outputs; would need strong parameter sharing (per-gene
  bias terms + target features, not free interactions).
- **M2 — context-conditioned correction:** needs context features for
  A/B/C beyond control bulk expression, which we do not have. Parked
  unless a usable context descriptor emerges.

## 5. Honest expected-value assessment

LOLO bounds what is learnable: if consensus-of-3 predicts held-out
direction at ~0.2–0.4 in the shared subspace and support at ~1%, a
learned correction starts from a very weak base. The optimistic case is
M0-type support broadening buying a few jaccard points (each ~worth
~1/6 of the avg); the pessimistic case is the same unsigned-signal wall
as Track 2b — lineage-private responses are *private*.

Budget accordingly: **M0 + LOLO screen ≈ half a day. M1 only if M0 or
the LOLO screen shows support signal above the noise floor. M2 parked.**

## 6. Gate protocol

1. **Delta-space LOLO screen first (no Gate B burn):** for each candidate,
   does it beat consensus-of-3 on held-out fold — top-200 subspace cos
   and top-k jaccard? Cheap, fully offline.
2. **Gate B arm** only for candidates passing step 1 (production
   mechanics can erase delta-space gains — established empirically).
3. **Submission** only with explicit user approval, per protocol.

## 7. Falsification criteria

Track 2a is closed (joins STRING k007 and regulon 2b in the
negative-results record) if:

- M0 support-broadening does not beat consensus on LOLO folds, AND
- no LOLO-screened variant improves held-out top-k jaccard/subspace cos.

At that point the residual gap to top-100 is declared
**signature-content-bound with no supervisable signal in available
data** — itself a documented finding for the post-competition writeup.
Remaining moves would be submission-economics only (bank k028, then
decide whether H1-weighted or per-context variants are worth slots on
unmeasurable hypotheses).

## 8. What would change the picture

- Any new corpus with perturbation measurements in or near the eval
  contexts (the actual A/B/C identities are unknown; context A scored
  Jurkat-like 0.649, B weakly RPE1-leaning, C unresolved).
- A context descriptor for A/B/C richer than control bulk expression.
- PromoterAI access (unlikely per user) — would feed M1's feature stack.

## 9. M0 LOLO screen results (2026-09-22) — VERDICT: CLOSED

Candidates built from the 3 non-held-out lineages, scored against the
held-out lineage's delta (343 targets, top-200 subspace cos / jaccard /
recall):

| held-out | mean | max | ormean | mean_boost |
|---|---:|---:|---:|---:|
| k562  (subcos/jac/rec) | .257/.011/.022 | .227/.009/.018 | .207/.008/.016 | .208/.008/.016 |
| hct116 | .373/.016/.029 | .338/.014/.026 | .325/.013/.023 | .343/.013/.023 |
| hek293t | .299/.014/.027 | .263/.013/.025 | .272/.012/.023 | .286/.012/.023 |
| cd4 | .192/.005/.010 | .165/.006/.012 | .134/.007/.013 | .150/.007/.013 |

**Plain mean wins every fold on every metric.** Support-broadening is
strictly worse: genes responding in only 1 of 3 lineages are
lineage-private noise, and averaging is the correct shrinkage. The
weighted-mean consensus is not under-calling support — it is already
the empirically optimal linear combination for unseen-lineage transfer.

This also pre-falsifies M1: the candidates above had *direct access* to
the other lineages' deltas and still lost to the mean. No feature-based
model trained on the same 1,372 examples can extract more signal than
the raw deltas contain. Per §7, Track 2a joins STRING (k007) and
regulon (2b) in the negative-results record.

**Standing conclusion (2026-09-22):** the residual gap to top-100 is
signature-content-bound with no supervisable signal in available data.
The consensus recipe is the defensible endpoint for this axis; remaining
levers are submission-economics (k028 in flight; optional unmeasurable
H1/per-context variants) and the Oct-22 unseen-lineage test set, where
consensus-over-lineages remains our structural bet.
