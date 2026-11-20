# VCC 2026 post-mortem — what the winners did, why we didn't win, and the path we'd run again

Status: **FINAL** · Written **2026-11-20** · Embargo lifted (competition
concluded, winners announced Nov 19). Component-level numbers are included
verbatim. What happens next: [`kytos-roadmap.md`](kytos-roadmap.md).

> Field size: 5,441 registrants · 1,469 teams · 26,827 validation
> submissions · 805 final entries. Winning score on the three held-out test
> lines: **0.4399** (BioInsight AI Lab / Illumina).
>
> Final standings (top 7, from the wrap-up):

| Rank | Team | Final test score |
|---|---|---|
| 1 | BioInsight AI Lab (Illumina) | 0.4399 |
| 2 | FlowState | 0.3348 |
| 3 | X-team (Xaira) | 0.3263 |
| 4 | Obradovic Lab | 0.3243 |
| 5 | C-team | 0.3193 |
| 6 | Aginglab.com | 0.3175 |
| 7 | TAO | 0.3150 |

Winner component scores (test panel):

| Metric | BioInsight | FlowState | X-team |
|---|---|---|---|
| PDS | 0.8313 | 0.8363 | 0.7346 |
| MSE | 0.6842 | 0.3632 | 0.4681 |
| NMAE | 0.4399 | 0.3286 | 0.3038 |
| FIDELITY | 0.1908 | 0.1695 | 0.0659 |
| REACH | 0.4288 | 0.3128 | 0.3186 |
| JACCARD | 0.0642 | −0.0018 | 0.0667 |

Field-wide, >90% of finalists beat the context mean on PDS and REACH, ~60%
on FIDELITY, ~40% on MSE, and only ~1/3 on JACCARD — the winning entry's
best-in-field JACCARD was 0.07. Across the 638 teams on both boards,
validation↔test Spearman was 0.78. Metrics preprint (Dobin):
[bioRxiv 2026.11.17.767214](https://www.biorxiv.org/content/10.64898/2026.11.17.767214);
scorer: [cell-eval2](https://github.com/ArcInstitute/cell-eval2).

## Our final state

| Entry | Panel | Score | Rank at submit |
|---|---|---|---|
| `kytos-k027-consensus-dm` (champion recipe) | validation A/B/C | +0.1262 | 308/1088 |
| `kytos-k040-sagr-dm` (ship recipe) | validation A/B/C | **+0.1286** | 529/1457* |
| `kytos-k043-final-sagr-dm` (`Ov4qNbLHMb1dRRyqxDn8`) | **test D/E/F** | hidden→revealed Nov 19 | see leaderboard† |

*rank floats as the board densifies — 529/1457 per the 2026-11-20 public
snapshot (`experiments/_embargoed/vcc_leaderboard_snapshot_2026-11-20.json`),
627/1299 at submission time; the score itself is stable (k037 byte-identical
rescore reproduced +0.1262 to Δ3e-5 eleven days later).
†the public leaderboard API publishes only the validation board; the final
test board needs the credentialed `vcc status` path (snapflip-vultr
unreachable as of 2026-11-20 — fill in when retrieved).

Champion component officials (k037 rescore, validation panel):

| pds | mse | nmae | fid | reach | jac | avg |
|---|---|---|---|---|---|---|
| 0.6032 | 0.0148 | 0.0882 | −0.0188 | 0.0686 | 0.0011 | +0.1262 |

Ship recipe (k040/k043): `consensus_w_ctr_sagr` deltas — weighted
cross-lineage consensus (Replogle K562 : X-Atlas HCT116 : X-Atlas HEK293T :
CD4 = 2:1:1:1), common-response centered, per-gene sign-agreement shrinkage
from X-Atlas per-sample vote stores — through the dual-moment count
generator (amplitude 1.0, bulk_amplitude 0.5, pool_k 4, 400 cells/pert).
Final-panel coverage: all four sources cover the 300-target test panel
(277/298/298/265; only ANG uncovered union-wide). Post-submit audit clean:
all deltas finite, no zero rows, self-gene knockdown negative on 299/300
targets; the one flagged outlier (DPY30, K562-only, ~9× median norm) is the
recipe working as designed.

## What the winners actually did

All three podium entries were **modular transfer pipelines**, not end-to-end
models: estimate pseudobulk effects for each knockdown from measured
responses in other cell types → adapt to the new line using only its control
cells → synthesize 400 cells from the line's own controls.

| | BioInsight AI Lab (1st, Illumina) | FlowState (2nd, independent) | X-team (3rd, Xaira) |
|---|---|---|---|
| Evidence unit | Per-dataset LFC + SE + significance (covariate-adjusted regression) | Per-gene change + uncertainty, harmonized across assays | Measured reference effects + model deltas |
| Combination | Random-effects meta-analysis; per-gene/per-pert weights from control similarity, noise, KD efficiency | Learned shared response programs from **222 datasets / 86 contexts** (half bulk: ENCODE, LINCS, PerturbAtlas, KnockTF, ARCHS4) | Reference pooling weighted by cell count + control similarity, per-study caps; X-Cell model gates per-gene carry-in |
| Context adaptation | SVD response patterns + ridge from control expression → LFC correction | Control cells as model prompt; heads trained on held-out contexts | Confidence- and direction-gated transfer |
| DE modeling | Explicit detectable-response estimation | Response-strength head | GBM classifier for significant DE genes |
| Cell synthesis | Distribute LFCs across line's control cells | Adjust counts of supplied control cells | Sampled control cells; effect sizes calibrated to 400-cell pseudobulk noise; count redistribution preserving pseudobulk |
| Data | Private Illumina Billion Cell Atlas + 3 public atlases | **Public data only** | In-house Perturb-seq (X-Atlas/Pisces) + external |
| Compute | 8×H200 + LLM research agents; CPU inference | — | Trained masked-diffusion model on 37M cells |

Organizers' cross-cutting findings:

- **Everyone predicted the cross-line average.** Among significant genes,
  predicted responses agreed across lines at cosine 0.77–0.89 vs measured
  0.55; the line-specific component had slope 0.02–0.13 vs replicate 1.02.
  Nobody solved context specificity — the winning margin was elsewhere.
- **Everyone over-called DE.** Real median 22–44 significant genes/target;
  X-team called 122–136, BioInsight ~500, rest of top ten 340–4,200.
- **Cell generation mattered**: redrawing cells under the same pseudobulk
  prediction moved scores by up to 0.004 — more than the 3rd↔4th gap.
- The field lost ~0.025 PDS on the 171 new-panel targets (validation
  hill-climbing cost); U-87MG (broadest responses, median 102 genes) was the
  hardest line (field median 0.066).

## Why we didn't win

We were in the right family — reference transfer + control-cell synthesis —
and our PDS (0.60–0.62) carried real signal. The gap from 0.13 to 0.44 is
in the statistical depth of every other stage.

### 1. We were a one-metric model; they were six-metric models

Four of six metrics sat at the context-mean baseline: **jac 0.001, reach
0.07, fid −0.02, mse 0.015**, nmae 0.09. Every winner built an explicit
model of *which genes are DE* — X-team's GBM classifier plus 400-cell
noise-floor calibration, BioInsight's detectable-response estimation,
FlowState's response-strength head. We had no DE-set estimator; our calls
fell out of dispersion knobs (`kd_std`, dual-moment params), and the k021
diagnostic already showed ~1.6–2× over-calling while missing the real sets.
Reach, jaccard, fidelity, and nmae — two-thirds of the score — live in that
layer.

### 2. Weighted average vs meta-analysis

BioInsight's core was measurement-grade statistics: per-dataset
covariate-adjusted regression → per-gene LFC **with SE and significance** →
random-effects meta-analysis that also estimates between-dataset
disagreement, so no noisy source dominates. Our consensus was pooled mean
log1p shifts with a fixed 2:1:1:1 weight — no SEs, no per-dataset precision
or KD-efficiency terms (our npz stores were pooled, not per-sample, until
the late k036 re-extraction). The eb2 shrinkage and agreement gates we tried
instead hit the pds↔reach tradeoff wall (k035/k038) and never cleared it.

### 3. Source breadth: 5 genome-wide screens vs 222 datasets

Our k039 audit correctly found no *single-cell genome-wide KD* corpus in the
missing lineages — and we closed the axis there. FlowState podium'd on
public data alone, half of it **bulk** screens (ENCODE, LINCS, PerturbAtlas,
KnockTF, ARCHS4). Once the evidence unit is "LFC + SE per gene," bulk pools
trivially. We treated genome-wide single-cell as a hard requirement and left
~200 usable datasets unharvested.

### 4. Context adaptation — a tiebreaker, not the gap

We shipped the same signature per target in every context (k041: basal
similarity doesn't predict source transfer → axis closed). Winners all had a
small explicit adaptation layer (SVD+ridge correction, context-conditioned
heads, per-gene carry-in gating). The organizers measured that even their
context-specific component is tiny (slope 0.02–0.13) — so this was worth
points, not the podium. Our "no conditionable signal" conclusion was
locally correct but we shipped zero adaptation where winners shipped a
small positive one.

### 5. Calibration to the scorer's statistical regime

X-team diagnosed that their model's per-cell log-norm output carried a
systematic bias under the challenge's log-transformed-pseudobulk evaluation,
and calibrated effect sizes against the sampling noise of a 400-cell
pseudobulk. We hit the same bulk-vs-cell lesson repeatedly (k020 expr_mse
blowup, transport→dual-moment switch) but never calibrated against the
noise floor — `delta_scale=1.7` was a leaderboard probe, not a fitted
constant, and we knew it cost nmae and shipped it anyway.

## What we got right

- **The core bet was correct.** The organizers' own analysis: carrying
  measured responses into new controls "recovers a large part of the
  perturbation-specific signal." Our signature-content diagnosis
  (`docs/signature-content-impasse.md`) was the right bottleneck.
- **Cell-generation engineering was competitive.** kd_std/dual-moment/
  library-cap work and the streamed 2 GB generator are comparable in spirit
  to all three winners' count-manipulation steps — and organizers priced
  that stage at ±0.004.
- **sagr was real signal.** Per-sample sign-agreement shrinkage was the one
  delta variant that *added information* rather than re-weighting, and it
  scored our best (+0.1286) with every component up-or-flat.
- **Probe discipline worked.** Pre-declared component predictions, no
  context-fit constants shipped blind, pinned scorer, byte-identical
  rescoring for a stable baseline — exactly the protocol the organizers'
  "hill-climbing cost" finding argues for.
- **Gate B was correctly demoted.** Four consecutive local-ordering
  failures proved the hESC-only eval couldn't arbitrate recipes; it stayed
  on as a leakage/regression screen.

## The path we'd run again

Same architecture, deeper statistics — and all inside our actual constraints
(solo, CPU VPS + Modal, occasional L40S). FlowState is the proof this is a
methods gap, not a resources gap.

1. **Extract DE statistics, not mean shifts.** Per-dataset LFC + SE +
   BH-significance per gene per target — the BioInsight representation.
   Agreement gating, reliability weighting, and DE calling all fall out of
   SEs for free.
2. **Harvest bulk.** ~200 public screens (ENCODE, LINCS, PerturbAtlas,
   KnockTF, ARCHS4) pooled per gene onto the panel axis. CPU ETL; this was
   the biggest single difference between our 5 sources and FlowState's 222.
3. **Precision-weighted meta-analysis fit by LOLO.** The k041 oracle
   machinery reused as a *fitting* harness: inverse-variance/random-effects
   weights (n_cells, SE, KD efficiency, cross-source disagreement) fit by
   leave-one-line-out on our own sources.
4. **Explicit DE-set layer.** Significance predictor (sign votes + SEs +
   control-expression filter) and effect sizes shrunk toward the 400-cell
   pseudobulk noise floor so DE counts land near the real ~22–44/target.
   This is where jac/reach/fid/nmae — the missing two-thirds — live.
5. **Optional context heads.** FlowState's strength/direction/magnitude
   heads are a per-gene regression problem, trainable on one L40S — worth
   the tiebreaker, not the ticket.

**What to cut:** Track 2 entirely (k014 MLP, k020/k020b GNN, k033 State —
~3 weeks + GPU budget, all negatives the k022 audit already implied), and
the dispersion/gate sweep loop (k008–k011 variants, k035/k038 — a dozen
slots proving one anticorrelated pds↔reach tradeoff).

**Expected shape:** pds ~0.6 already holds; a real DE layer plausibly lifts
jac/reach/fid/nmae/mse into the 0.2–0.4 band → avg ~0.35–0.43, top-5 to
podium range. First place additionally needed a private billion-cell atlas
and agent-driven iteration at Illumina scale — second was reachable on
public data alone.

## One-sentence version

We won the part of the problem we modeled (PDS 0.6 is real signal) and
never made DE-set estimation and precision-weighted evidence combination
first-class problems — where two-thirds of the score lived.

## Appendix — submission history

| Run | Score | Rank | Note |
|---|---|---|---|
| pipe-test random | −0.948 | — | pipeline test |
| k003-mean-shift | −0.948 | — | sparse baseline |
| k004-real-resampling | −0.304 | 765 | real dispersion |
| k004-layer-a-b | −0.149 | 656 | first pds signal |
| k006-replogle-prior | −0.021 | 534 | K562 priors, 272/300 |
| k007-neighbor-prior | −0.0159 | 534 | STRING imputation |
| k008-kd sweep (0.7→2.0) | +0.0007 → +0.0511 | 519→462 | heterogeneity axis |
| k009-gamma (1.4/2.0) | −0.0011 / +0.0075 | 565/544 | shape negative |
| k010-mc (s2.0/s4.0) | +0.0090 / +0.0122 | 565/564 | mean-correction |
| k011-ds x1.3/x1.7/x2.0 | +0.0559/+0.0596/+0.0566 | 502/486/515 | scale axis bent |
| k013-ctx-scale | +0.0312 | 560 | per-context amp: negative |
| k015-lowrank-r256 | −0.028 | 689 | OOD essential map |
| k018-h1lr-dm-c | +0.042 | 546 | H1 transfer, ctx C only |
| k020 GNN / k020b | −0.114 / −0.098 | 811/802 | Track 2: negative |
| k026-consensus-w-ctr | +0.0670 | 512 | first Gate-B-backed ship |
| **k027-consensus-dm** | **+0.1262** | 308 | dual-moment champion |
| k028-dm-pk12 | +0.1239 | — | pool_k probe |
| k029-consensus-eb2 | +0.1115 | 416 | eb2 regression |
| k030-consensus-meanj | +0.1088 | 442 | Jurkat arm: negative |
| k034-nctr-dm | +0.1178 | ~455 | uncentered: negative |
| k035-ctragr-dm | +0.1242 | ~449 | agreement gate: tie |
| k037-k027-rescore | +0.12617 | 483/1299 | scorer stable; canonical components |
| k038-ctragr-tight-rmass | +0.1254 | 489 | gate axis closed (pds↔reach) |
| **k040-sagr-dm** | **+0.1286** | 627 | best validation score |
| **k043-final-sagr-dm** | final | — | k040 recipe, test panel D/E/F |

Runs with no slot spent: k033 State trained-signature (Gate B loss),
k034 rehearsal, k039/k041/k042 audits (axes closed without submission).
