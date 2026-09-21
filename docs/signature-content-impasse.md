# Decision record — the signature-content impasse

Status: **DECIDED** · Written **2026-09-21** · Evidence base: k022 pipeline
audit (`paired47-20260921-01`, `consensus5-20260921-01`, `-03`), k023
extraction (`extract-20260921-01`, `extract-20260921-02-honest`)

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

1. **Promoter-neighbor prior (k024, in flight).** Orthogonal mechanism —
  deterministic CRISPRi local silencing (neighbor genes within 5kb of the
  target TSS), not a reweighting of existing deltas. Coverage is thin: 14/47
  eval targets (7/32 powered). Being evaluated as `promoter_neighbor_only`
  and `*_pncap` arms in `pn2-20260921-01`. Expected value is bounded by
  coverage; it is a correctness prior, not a gap-closer, unless per-target
  gains are large.
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

- Record the impasse. Do **not** submit a consensus or reweighted variant:
  the measured aggregate gain (+0.001 median cosine proxy) is far below any
  plausible leaderboard signal.
- Complete the k024 promoter-neighbor evaluation for completeness — it is
  the last untested mechanism from the rank-82 recipe — then reassess.
- If k024 is also marginal, the honest recommendation is: keep k011 as the
  standing submission, and treat Track-2 (learned transfer) as the only
  remaining route with enough headroom — with a clear-eyed view of its cost
  and prior failure modes.
