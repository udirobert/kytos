# Decision record — the signature-content impasse

Status: **DECIDED, partially revised 2026-09-22** · Written **2026-09-21** ·
Evidence base: k022 pipeline audit (`paired47-20260921-01`,
`consensus5-20260921-01`, `-03`), k023 extraction (`extract-20260921-01`,
`extract-20260921-02-honest`), k025 Gate B (`gate-20260921-01`)

> **2026-09-22 revision note.** The verdicts below were reached on a median
> cosine proxy. The k025 Gate B run (§6) scored the same arms through the
> pinned `cell-eval2` six-metric path and found the consensus verdict was
> understated: `consensus_w_ctr` is a clear positive over
> champion-equivalent on the real scorer — driven by metrics the
> direction-cosine diagnostic does not capture (breakdown embargoed).
> The "impasse" framing stands for *direction cosine* specifically; it does
> not stand for overall score. (Exact numbers embargoed — see
> `experiments/_embargoed/`.)

This record documents what we tried to close the K562→context signature gap
with public data, what each attempt measured, and what remains open. It is a
negative-result record: the value is in which hypotheses are now *measured*,
not conjectured.

## 1. Position

- Champion at time of writing: `kytos-k011-ds-x1p7`, official score
  **+0.0596**, observed rank ~486 at submission time. Superseded as champion
  by `k026` then `k027` (§6.1, `docs/vcc-two-track-strategy.md`).
- Ambition: top 100 (~+0.15 at the snapshot).
- Diagnosed bottleneck (k022 `paired47-20260921-01`, 32 powered eval targets,
  hESC context): the generator/transport stack is calibrated; the *borrowed
  signature content* is not.

| Arm (identical splits, seed 0) | Median cosine |
|---|---|
| observed-fit ceiling (fit cells vs eval cells) | reference ceiling |
| measured transport (in-context delta, ds=1.0) | ~2× borrowed |
| **borrowed K562 delta (ds=1.7)** | **well below measured** |

Exact values embargoed: `experiments/_embargoed/diagnostic-numbers.md`.

The entire post-k011 program has been: close the borrowed → measured gap
without using evaluation data.

## 2. What was tried and measured

### 2.1 Uniform tuning — exhausted

The `delta_scale` curve bent at ~2.0 (k011 x2.0 = +0.0566 < x1.7 = +0.0596):
`nmae` erosion now outweighs `fid`/`pds` gains. Per-context amplitude
(k013-ctx-scale, +0.0312) was a clean negative. Uniform scalar magnitude is
exhausted; the gap is directional content, not amplitude.

### 2.2 Per-target transferability gate — falsified

Hypothesis: predict, per target, whether the K562 signature transfers, and
borrow only where it does. Measured: `cos(delta_k562, delta_hesc)` predicts
the transported-borrowed diagnostic score only weakly — far too weak to
function as an oracle gate (exact r embargoed). Receipts in
`paired47-20260921-01`.

### 2.3 Multi-source consensus denoising — marginal, not a fix

k023 extracted same-contract deltas (`mean log1p(raw)` perturbed minus
control, panel axis) from four independent lineages:

| Source | Targets covered | Units |
|---|---:|---|
| K562 (Replogle repack) | 315/343 | log1p shift |
| X-Atlas HCT116 | 343/343 | log1p shift |
| X-Atlas HEK293T | 343/343 | log1p shift |
| CD4 (Marson 2025) | 282/343 | publisher log2FC |

Variants: unit-normalized weighted mean (2:1:1:1), optional common-response
centering, optional `min(1, n_cells/100)` cell-count weighting, amplitude
restored to the K562 norm.

Honest result (`consensus5-20260921-03`; exact arm values embargoed in
`experiments/_embargoed/diagnostic-numbers.md`): the consensus variants land
within noise of the honest k562 baseline, and the single-source
`hct116_batch` arm is clearly worse.

Consensus wins most targets pairwise (borderline significant) but does not
move the aggregate median — a ~0% relative improvement.
The mechanism is structural: **cross-lineage deltas are near-orthogonal**,
so averaging suppresses noise
without recovering shared signal. There is little shared signal to recover.

### 2.4 The evaluation-context leak (recorded for honesty)

`delta_matrix_src.npz` is atlas-preferred: for the 47 eval targets its rows
are in-context hESC deltas from the same file the audit evaluates (verified
numerically identical). The first consensus run (`consensus5-20260921-01`)
therefore scored a "k562" arm far above any real borrowed arm — a
**leaked pseudo-ceiling, not borrowed transfer**. `extract_k562` was fixed to
prefer Replogle `delta_k562` for paired targets; `consensus5-20260921-03` is
the honest record and reproduces paired47's baseline exactly.

Consequence: any earlier artifact reporting a high score for a "K562"
borrowed arm on this eval set must be re-read against this finding.

## 3. What the evidence supports — and does not

Supported:

- Borrowed cross-lineage signatures, single or consensus-averaged, reach
  roughly half of measured in-context transport on hESC eval.
- Neither per-target selection nor multi-source averaging closes the gap.
- The gap is therefore not estimation noise; it is missing context-specific
  biology.

Not supported (do not overclaim):

- "Public data cannot solve this." Only the *tested* routes failed. The
  X-Atlas corpus, CD4 stats, and Replogle K562 were used as global
  pseudobulk deltas; feature-space, cell-state, or learned-mapping uses of
  the same corpora are untouched.
- "0.27 is a hard ceiling for borrowed signatures." It is the ceiling for
  *these* borrowed signatures on *this* diagnostic.

## 4. What remains open

1. **Promoter-neighbor prior (k024) — measured, marginal-positive,
  coverage-bound.** The kaipengm2 CRISPRi local-silencing prior was ported
  to delta space (`pn2-20260921-02`): neighbor genes within 5kb of the
  target TSS get a deterministic repression ceiling `log1p(r·M) − log1p(M)`.
  Coverage: 85 pairs, 7/32 powered eval targets. Result: the standalone
  prior alone performs comparably to borrowed K562 on covered targets —
  slightly *above* it, confirming local
  silencing is real signal — and the post-scale cap improves most covered
  borrowed arms. But per-target gains are small and 25/32
  targets have no pair at all, so the aggregate median does not move.
  **Verdict: a correctness prior worth keeping in production
  generation (it only tightens, with one recorded exception), not a
  gap-closer.** Exact values embargoed:
  `experiments/_embargoed/diagnostic-numbers.md`.
  Receipts: `experiments/k024-promoter-prior/pn2-20260921-02-analysis.json`.
2. **Track-2 learned context transfer.** The only remaining route that could
  *learn* the K562→context map rather than borrow it. Prior attempts
  (k014 conditional MLP, k020 GNN) had implementation confounds and never
  established a trustworthy offline win; this route costs GPU time and
  carries the 47-pair supervision limit unless H1-2025 (150 targets) or
  X-Atlas is folded in.
3. **Submission posture.** No submission is justified by current evidence:
  every tested variant is within noise of the champion or worse. Submit only
  if a diagnostic arm clears k011's contract with margin, or if a genuinely
  new information source is added.

## 5. Decision

- Record the impasse. Do **not** submit a consensus, reweighted, or
  promoter-capped variant: measured aggregate gains on the median-cosine
  proxy are far below any plausible leaderboard signal.
- The honest recommendation is: keep k011 as the standing submission, fold
  the promoter-neighbor cap into the production generator as a
  correctness prior (costless, only tightens), and treat Track-2 (learned
  context transfer) as the only remaining route with enough headroom —
  with a clear-eyed view of its cost and prior failure modes (k014, k020).

## 6. Revision — Gate B scored the same arms on the real metrics (2026-09-22)

The §2.3 "marginal" verdict and the §5 "no submission" posture were derived
from the k022 median cosine diagnostic. `gate-20260921-01` (k025) then
generated production-shaped predictions for the same honest variants
(HeterogeneousTransportSampler kd_std=2.0, `library_cap="median"`, 400
cells/pert, int32 counts) and scored them through pinned `cell-eval2`
0.16.0 (`vcc2026`, `target_gene`, 5 anchor splits) on the 47 paired hESC
eval targets:

*Full metric tables embargoed until the Oct 22 final test set — see
`experiments/_embargoed/k025-eval2-gate/` (local-only).*

What this revises:

- **Consensus is a real official-metric gain, not marginal.** A clear
  positive avg_score margin over the champion-equivalent path — the
  median-cosine proxy understated it because direction is only part of
  what the official score rewards.
- **The impasse narrows, it does not lift.** Direction content is still
  the gap (borrowed ≈ half of measured); the official score weights other components
  heavily enough that consensus nets positive anyway.
- **Per-metric mechanism, component regressions, and the promoter-prior
  interaction are embargoed** — `experiments/_embargoed/k025-eval2-gate/`
  and `experiments/_embargoed/k027-consensus-dm/analysis.md`.

Standing caveats (unchanged): local real bundle is not the live competition
anchor bundle; 47 hESC targets only — no Jurkat/RPE1-like context and no
300-target panel breadth test; `expr_mse` saturated at 0 for all
non-oracle arms; leaderboard scale is not directly mappable.

Updated posture: `consensus_w_ctr` is a **defensible submission
candidate** — the first arm with production-equivalent evidence of
improvement over k011. Gate E requirements (panel coverage check,
declared component changes, explicit approval) are in
`docs/vcc-two-track-strategy.md`. Track-2 learned transfer remains the
only route with headroom toward top-100; consensus is an incremental
improvement, not a signature-content solution.

Receipts: `experiments/k025-eval2-gate/gate-20260921-01/` (execution.json,
results.json, per-arm agg + scored CSVs, anchors).

### 6.1 Leaderboard outcome (2026-09-22)

`kytos-k026-consensus-w-ctr` submitted: **score_avg +0.0670, rank
512/1086** — new champion by score (+0.0074 over k011 +0.0596). Gate B
predicted a local margin roughly 4× larger than the official delta,
consistent
with the declared caveats (47/300 eval targets, local bundle ≠ live
anchors, single eval context). The sign survived — Gate B is validated
as a directional promotion gate. The improvement is real but small:
the signature-content impasse stands for top-100 ambitions, and
Track-2 (or a genuinely new signal source) remains the only route with
that much headroom.
