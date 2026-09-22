# Decision record — the signature-content impasse

Status: **DECIDED, partially revised 2026-09-22** · Written **2026-09-21** ·
Evidence base: k022 pipeline audit (`paired47-20260921-01`,
`consensus5-20260921-01`, `-03`), k023 extraction (`extract-20260921-01`,
`extract-20260921-02-honest`), k025 Gate B (`gate-20260921-01`)

> **2026-09-22 revision note.** The verdicts below were reached on a median
> cosine proxy. The k025 Gate B run (§6) scored the same arms through the
> pinned `cell-eval2` six-metric path and found the consensus verdict was
> understated: `consensus_w_ctr` is **+0.033 avg_score** over
> champion-equivalent on the real scorer — driven by `pds_cosine` and
> `lfc_nmae`, metrics the direction-cosine diagnostic does not capture.
> The "impasse" framing stands for *direction cosine* specifically; it does
> not stand for overall score.

This record documents what we tried to close the K562→context signature gap
with public data, what each attempt measured, and what remains open. It is a
negative-result record: the value is in which hypotheses are now *measured*,
not conjectured.

## 1. Position

- Champion: `kytos-k011-ds-x1p7`, official score **+0.0596**, observed rank
  ~486 at submission time.
- Ambition: top 100 (~+0.15 at the snapshot).
- Diagnosed bottleneck (k022 `paired47-20260921-01`, 32 powered eval targets,
  hESC context): the generator/transport stack is calibrated; the *borrowed
  signature content* is not.

| Arm (identical splits, seed 0) | Median cosine |
|---|---:|
| observed-fit ceiling (fit cells vs eval cells) | 0.701 |
| measured transport (in-context delta, ds=1.0) | 0.514 |
| **borrowed K562 delta (ds=1.7)** | **0.268** |

The entire post-k011 program has been: close the 0.268 → ~0.5 gap without
using evaluation data.

## 2. What was tried and measured

### 2.1 Uniform tuning — exhausted

The `delta_scale` curve bent at ~2.0 (k011 x2.0 = +0.0566 < x1.7 = +0.0596):
`nmae` erosion now outweighs `fid`/`pds` gains. Per-context amplitude
(k013-ctx-scale, +0.0312) was a clean negative. Uniform scalar magnitude is
exhausted; the gap is directional content, not amplitude.

### 2.2 Per-target transferability gate — falsified

Hypothesis: predict, per target, whether the K562 signature transfers, and
borrow only where it does. Measured: `cos(delta_k562, delta_hesc)` predicts
the transported-borrowed diagnostic score at **r ≈ 0.22** — far too weak to
function as an oracle gate. Receipts in `paired47-20260921-01`.

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

Honest result (`consensus5-20260921-03`):

| Arm | Median cos | Pairwise wins vs k562 |
|---|---:|---:|
| k562 (honest) | 0.268 | ref |
| consensus_w_ctr | 0.269 | 22/32 |
| consensus_w | 0.267 | 21/32 |
| consensus_mean | 0.256 | 19/32 |
| hct116_batch (single) | 0.211 | 11/32 |

Consensus wins most targets pairwise (borderline significant) but moves the
aggregate median by ≤ +0.001 — a ~0% relative improvement on a 0.268 base.
The mechanism is structural: **cross-lineage deltas are near-orthogonal**
(median pairwise cos 0.02–0.05, up to ~0.10), so averaging suppresses noise
without recovering shared signal. There is little shared signal to recover.

### 2.4 The evaluation-context leak (recorded for honesty)

`delta_matrix_src.npz` is atlas-preferred: for the 47 eval targets its rows
are in-context hESC deltas from the same file the audit evaluates
(verified: `cos(src_row, delta_hesc) = 1.0000`). The first consensus run
(`consensus5-20260921-01`) therefore scored a "k562" arm at 0.604 — a
**leaked pseudo-ceiling, not borrowed transfer**. `extract_k562` was fixed to
prefer Replogle `delta_k562` for paired targets; `consensus5-20260921-03` is
the honest record and reproduces paired47's baseline exactly (0.2683).

Consequence: any earlier artifact reporting ~0.6 for a "K562" borrowed arm
on this eval set must be re-read against this finding.

## 3. What the evidence supports — and does not

Supported:

- Borrowed cross-lineage signatures, single or consensus-averaged, sit at
  ~0.21–0.27 median cosine on hESC eval — roughly half of measured
  in-context transport (0.514).
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
  prior alone reaches median cosine **0.270 on covered targets** — slightly
  *above* borrowed K562 on those same targets (0.257), confirming local
  silencing is real signal — and the post-scale cap improves borrowed arms
  on 6/7 covered targets. But per-target gains are +0.002–0.009 and 25/32
  targets have no pair at all, so the aggregate median does not move
  (~0.268). **Verdict: a correctness prior worth keeping in production
  generation (it only tightens, except DOT1L −0.003), not a gap-closer.**
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
  promoter-capped variant: measured aggregate gains (+0.001–0.003 median
  cosine proxy) are far below any plausible leaderboard signal.
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

| Arm | avg_score | pds_cosine | lfc_nmae | fidelity | reach | jaccard |
|---|---:|---:|---:|---:|---:|---:|
| oracle_hesc (leak-by-design ceiling) | 0.823 | 1.012 | 0.696 | 0.770 | 1.006 | 0.829 |
| **consensus_w_ctr** | **0.1417** | **0.642** | -0.148 | 0.204 | -0.008 | 0.159 |
| cons_w_ctr_pncap | 0.1403 | 0.613 | -0.144 | 0.208 | -0.000 | 0.165 |
| k562_ds1p7_pncap | 0.1145 | 0.510 | -0.425 | 0.346 | -0.046 | 0.302 |
| k562_ds1p7 (champion-equivalent) | 0.1085 | 0.488 | -0.432 | 0.343 | -0.050 | 0.302 |
| k562_ds1p0 | 0.0966 | 0.407 | -0.210 | 0.229 | -0.028 | 0.182 |
| null | -0.1093 | -0.067 | -0.106 | -0.312 | -0.067 | -0.104 |

What this revises:

- **Consensus is a real official-metric gain, not marginal.** +0.033
  avg_score over the champion-equivalent path. The cosine proxy measured
  *direction* and found +0.001; the official score rewards *discrimination*
  (`pds_cosine` 0.642 vs 0.488 — consensus suppresses shared noise that
  blurs target ranking) and *amplitude honesty* (`lfc_nmae` -0.148 vs
  -0.432 — consensus norm-shrinkage is informative shrinkage, unlike
  delta_scale inflation which buys direction at nmae cost).
- **The trade is explicit:** consensus_w_ctr *loses* direction fidelity
  (0.204 vs 0.343) and sig-gene jaccard (0.159 vs 0.302). Net is positive
  in Gate B, but a leaderboard submission should be declared with those
  component regressions on the record.
- **The impasse narrows, it does not lift.** Direction content is still
  the gap (0.268 vs 0.514). What changed: *that* gap is not the binding
  constraint on the official score at current operating points —
  discrimination and calibrated magnitude carry more weight.
- **Promoter prior:** +0.006 avg on k562 (worth keeping), ~0 on consensus.

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
predicted +0.033 local; the official delta is ~4× smaller, consistent
with the declared caveats (47/300 eval targets, local bundle ≠ live
anchors, single eval context). The sign survived — Gate B is validated
as a directional promotion gate. The improvement is real but small:
the signature-content impasse stands for top-100 ambitions, and
Track-2 (or a genuinely new signal source) remains the only route with
that much headroom.
