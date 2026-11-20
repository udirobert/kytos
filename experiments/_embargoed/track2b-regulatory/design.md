# Track 2b — regulatory-prior direction correction (EMBARGOED until Oct 22)

> Motivated by embargoed findings — do not publish until the final test set.
> Created 2026-09-22.

## Why this track exists

- `expr_mse_unbiased_capped_norm` saturates at 0 for every non-oracle arm
  because our deltas add net error to the bulk mean — **direction accuracy
  is the binding constraint**, not generation, not amplitude.
- Leaderboard #1 runs "customized PromoterAI_precomputed" (Illumina's
  promoter-variant model, Science 2025) — evidence the top of the board is
  using **sequence-derived regulatory information**, not signature
  borrowing.
- k007 STRING propagation failed (-0.016 official), but STRING is
  *undirected functional association*. A signed TF→gene regulatory prior
  is a different hypothesis — STRING's failure does not falsify it.

## Coverage arithmetic (measured 2026-09-22)

- Panel: 75/300 targets (25%) are TFs (Lambert v1.01 list), plus
  chromatin/Polycomb regulators (KMT2A, PHF19, PCGF6, DNTTIP1, MBD4...) —
  most knockdowns propagate through regulatory cascades regardless.
- Gate B eval subset: 9/47 eval targets are TFs (CENPB, DOT1L, JAZF1,
  MAX, NFE2L1, TCF7L2, USF2, ZNF581, ZNF598) — a regulon prior is
  *measurable but diluted* offline (~1/5 of eval targets touched directly).
  A genuine per-target improvement on those 9 may show only modestly in
  the 47-target aggregate. Interpret Gate B accordingly; per-target
  breakdown is the honest read, not just avg_score.

## Feature sources (ordered by acquisition cost)

1. **CollecTRI / DoRothEA signed regulons** (Omnipath, free): signed
   TF→gene edges (activation/repression) — sign propagates naturally
   under knockdown (KD of activator → target down; KD of repressor →
   target up). Direct answer to "direction."
2. **Motif-scanning DIY regulons**: JASPAR TFBS in promoter windows for
   all 18,533 panel genes → per-(TF, gene) binding matrix. Genome-wide,
   tunable stringency, no license friction.
3. **PromoterAI precomputed SNV scores** (Illumina, free academic
   license, email-gated): per-variant promoter impact scores → aggregate
   to per-gene promoter sensitivity/regulatability. Uncertain marginal
   value over (1)+(2); file the request anyway — link below.
4. **Sequence-model embeddings** (Borzoi/Enformer/NT): per-gene promoter
   embeddings as features. Heaviest; only if (1)-(3) show signal.

## Model stages (increasing complexity, each gated through Gate B)

- **Stage 0 — additive regulon prior (no training).** For TF targets:
  δ_final = δ_consensus + β · R[t,·], where R is the signed regulon row
  and β a global amplitude fit on source lineages. Cheapest possible
  test of the hypothesis.
- **Stage 1 — learned blend.** Per-target weight w_t between consensus
  and regulon delta, learned by leave-one-lineage-out CV on the honest
  4-lineage delta matrix (343 targets × 18,533 genes).
- **Stage 2 — feature-conditioned correction.** Model predicts
  per-(target, gene) correction from regulon features + target features,
  supervised on cross-lineage deltas with lineages held out.
- **Stage 3 — context-conditioned correction** (Track 2 proper merge):
  correction depends on context expression features. Only if Stage 1/2
  show the prior carries real direction.

## Leakage rules (non-negotiable)

- The 47-target hESC eval deltas are the Gate B yardstick — **never**
  train or tune on them. Supervision comes only from source corpora
  (K562, HCT116, HEK293T, CD4 honest deltas).
- Regulon priors are static public knowledge — no leak risk, but coverage
  must be audited against the panel axis (gene symbols, not Ensembl).

## Falsification criteria

- Stage 0 fails Gate B (no avg or per-target improvement on the 9 TF
  eval targets) → GRN-prior hypothesis joins STRING in the negative
  results; Track 2b ends.
- Stage 0 passes on TF eval targets but Stage 1 blend adds nothing →
  ship the additive prior only if the aggregate gain clears noise.

## Expected value

- If regulon direction is even moderately right on TF targets: fidelity/
  jaccard improve (the metrics consensus lost), expr_mse may finally move
  off 0 on those targets. Non-TF targets get indirect benefit only.
- Ceiling check: 25% TF panel coverage means this alone can't reach
  top-100 — it's a component, not the answer. The answer probably needs
  regulatory priors + learned context transfer (Track 2a) together.

## PromoterAI license

Request at https://github.com/Illumina/PromoterAI (license agreement
form → download link emailed). Free for academic/non-commercial use.
File under the user's email — requires agreeing to license terms, so
the user submits it, not the agent.

## Stage 0 result (gate-20260922-04, 2026-09-22) — MIXED

Aggregate (dual-moment a1.0/b0.5, all arms): dm_a1p0_ref-equivalent
baseline 0.1913 (run2 cons_dm_a1p0); reg_w03 0.1924 (+0.001), reg_w08
0.1916 (+0.0003), reg_only 0.1647 (-0.027). Flat at w<=0.8, negative
when regulon fully replaces consensus.

Per-target pds_cosine on regulon-covered eval TFs (ref -> reg03 -> reg08 -> regonly):

| target | edges | ref | w03 | w08 | only |
|---|---:|---:|---:|---:|---:|
| NFE2L1 | 8 | 0.609 | 0.674 | 0.804 | 0.978 |
| DOT1L | 8 | 0.826 | 0.870 | 0.848 | 0.543 |
| TCF7L2 | 114 | 0.239 | 0.174 | 0.087 | 0.022 |
| USF2 | 113 | 0.283 | 0.283 | 0.239 | 0.304 |
| MAX | 47 | 1.000 | sat | sat | sat |
| JAZF1 | 1 | 1.000 | sat | sat | sat |

Reading: dose-responsive in BOTH directions. NFE2L1 regulon direction
is dramatically right (pure regulon = best pds); TCF7L2 regulon is
wrong in-context (developmental/Wnt TF -- context-dependent regulon,
consistent with the context-genericity caveat). MAX/JAZF1 saturated.

Gate check: regulon<->consensus cosine does NOT separate helped from
hurt (NFE2L1 +0.014, TCF7L2 -0.003). Edge count does not either.
Candidate Stage-1 gate: regulon agreement with EACH source lineage's
delta separately (context-stability across K562/HCT116/HEK293T/CD4) --
broadly-active regulators should show consistent agreement; context-
dependent TFs should not. Requires per-lineage delta matrices from the
k023 extraction, not just consensus.

Verdict: NOT a falsification (real positive signal exists) and NOT a
uniform win. Proceeds to Stage 1 only if a context-stability gate
separates helped vs hurt on the 6 eval TFs; otherwise the component is
real but unshippable.

## Stage-1 gate check (2026-09-22) — GATE FAILS

Regulon-vs-lineage delta cosines for the 6 covered eval TFs (honest
deltas_k562 from extract-02; hct116/hek293t/cd4 from extract-01):

| target | k562 | hct116 | hek293t | cd4 | min |
|---|---:|---:|---:|---:|---:|
| DOT1L (helped@w03) | -0.005 | -0.007 | 0.023 | 0.000 | -0.007 |
| NFE2L1 (helped big) | 0.007 | 0.023 | 0.011 | 0.004 | +0.004 |
| TCF7L2 (hurt) | -0.005 | 0.008 | 0.031 | 0.000 | -0.005 |
| USF2 (~flat) | 0.002 | 0.025 | 0.041 | 0.000 | 0.000 |

All |cos| < 0.05 -- the regulon prior is nearly ORTHOGONAL to every
lineage's expression delta. It carries genuinely different information
(which is why NFE2L1 gained so much when right), but no observable
statistic separates helped from hurt: not regulon-consensus agreement,
not edge count, not cross-lineage consistency. A trust model would need
per-(target, context) "did the regulon help" labels -- i.e., measured
in-context deltas, which is the quantity being predicted. Chicken-and-egg.

## Track 2b verdict: PARKED

Stage 0 shows real but unsigned signal (helped NFE2L1 +0.37 pds,
hurt TCF7L2 -0.22, aggregate flat). Shippable only with a trust gate
that cannot be supervised with available data. Same structural wall as
the k022 transferability gate (r=0.22) -- "which targets to trust" is
itself the hard problem.

Options if revisited: (a) restrict overlay to ubiquitously-active
regulators (MAX/NFE2L1/USF2-class bHLH) and exclude developmental TFs --
a hand rule, not learned; could not be validated offline beyond the
6 eval TFs; (b) wait for PromoterAI scores -- per-variant promoter
sensitivity may supply a confidence feature the GRN edge list lacks;
(c) treat as evidence for the top team's mechanism without adopting.
