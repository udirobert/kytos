# Diagnostic numbers removed from public docs (embargo)

Exact non-leaderboard metric values stripped from `docs/` and `AGENTS.md` on
2026-09-23 under the publication embargo (see AGENTS.md top section). Public
docs keep qualitative outcomes; exact values live here until Oct 22.

Sources: `experiments/k022-pipeline-audit/`, `k023-consensus/`,
`k024-promoter-prior/`, `k012-transfer-loo/`, `k012-lineage-score/`,
`k015-essential-transfer/`, `k017-offline-cell-eval/`, `k019-crosslineage/`,
`k021-ceiling/`, `experiments/_embargoed/k025-eval2-gate/`.

## Gate C / paired47-20260921-01 (32 powered eval targets, hESC)

- Borrowed K562 deltas: median cosine **0.268**
- Measured in-context transport (ds=1.0): **0.514**
- Observed split ceiling (fit vs eval cells): **0.701**
- Borrowed beats measured in only **1/32** targets
- Transport null variance ratio on real controls: **1.05**
- Direct-moment arms under-disperse: **~0.28** (not the shipped path)
- Transferability gate: `cos(delta_k562, delta_hesc)` predicts borrowed
  success at **r ≈ 0.22** (0.32 among high-ceiling targets) — falsified

## k023 consensus (consensus5-20260921-03, honest re-run)

- Cross-lineage delta agreement: median pairwise cos **0.02–0.05**
  (up to ~0.10) on the panel axis
- Leaked first-run "k562" arm (consensus5-20260921-01): **0.604**
  (pseudo-ceiling; src rows were in-context hESC deltas)
- Honest arm medians: k562 **0.268** (exact replication of paired47,
  0.2683), consensus_w **0.267**, consensus_w_ctr **0.269**,
  consensus_mean **0.256**, hct116_batch **0.211**
- Consensus pairwise wins: **22/32** targets (median +0.026); aggregate
  median unmoved (≤ +0.001)

## k024 promoter-neighbor prior (pn2-20260921-02)

- Standalone prior on covered targets: median cos **0.270** vs k562 **0.257**
- Post-scale cap improves borrowed arms on **6/7** covered targets
- Per-target gains **+0.002–0.009**; aggregate median unmoved (~0.268)
- DOT1L **−0.003** — the one tightening exception

## k025 Gate B (gate-20260921-01)

- Gate B predicted **+0.033** local avg_score margin for `consensus_w_ctr`
  over champion-equivalent; official delta ~4× smaller (k026 +0.0670 vs
  k011 +0.0596)
- `expr_mse` saturated at 0 for all non-oracle arms

## Earlier diagnostic values (historical appendix / run log)

- k012 LOO transfer eval: raw K562→hESC cosine **~0.13**; fitted scalar
  **s≈0.44**; low-rank map sign acc **0.60** vs **0.32** raw
- Lineage scores: A Jurkat-like **0.649**, B RPE1-leaning **0.369**, C hESC
  **0.379**
- k014 conditional MLP: best held-out cosine **0.0425** vs identity
  **0.1406**; magnitude ratio **0.35**
- k015 low-rank held-out cosine (identity / r128 / r256):
  K562→Jurkat **0.439 / 0.537 / 0.549**; K562→RPE1 **0.330 / 0.607 /
  0.614**; K562→HepG2 **0.355 / 0.541 / 0.548**; norm ratios on paired
  essential data ~0.53–0.59 pred/dst
- H1 delta-level harness (136 train pairs → 47 H1-val targets): raw K562
  identity top-200 cosine **0.403**; rank-64 low-rank + self-median reset
  reaches top-200 **~0.61**, Pearson **~0.39–0.46**. Best composite
  `h1lr64_ds2p0_selfTrainScaled` (top200 **0.610**, Pearson **0.435**, norm
  ratio **0.874**); `h1lr64_ds1p3_selfTrain` top200 **0.614**, norm ratio
  **0.532**
- k017 offline legacy cell-eval (count-level): `h1lr64_ds2p0_selfTrainScaled`
  discrimination **0.613**, overlap **0.233**, Pearson-delta **0.246**;
  `h1lr64_ds1p7_selfTrain` MSE **0.00779**, MAE **0.0554**; identity ds1.7
  baseline: discrimination **0.530**, overlap **0.205**, Pearson-delta
  **0.076**
- k019 OOD-proxy gate: identity transplant cos_ood Jurkat **−0.090**, RPE1
  **−0.077**; low_rank **+0.099** / **+0.296**; kernel_rbf **+0.138** /
  **+0.268**; `mean cos(identity,true)=0.11` (k021)
- k020 GNN offline OOD gate: cos_ood **−0.088 → +0.199**, cos_all
  **0.249 → 0.374**, in-dist **0.604 → 0.585**; raw GNN median magnitude
  ratio **A 0.50 / B 0.37**
- k021 ceiling/attribution harness (exploratory): discrimination_l1
  **0.53 → 0.96** (ceiling 0.99, sig_frac 0.93); pearson_delta
  **0.08 → 0.67** (ceiling 0.86, sig_frac 0.75); overlap_at_N
  **0.21 → 0.38** (ceiling 0.65, mod_frac 0.61); precision_at_N
  **0.21 → 0.32** (ceiling 0.65, mod_frac 0.75); `de_nsig_counts_pred`
  **6704** (identity) / **5462** (true@1.0) vs real **3436** — generator
  over-called DE genes ~1.6–2×

## k029 official result (2026-09-24)

- `kytos-k029-consensus-eb2-dm-pk12`: official score_avg **+0.1115**,
  rank 416/1129 — regression of -0.0147 vs k027 champion (+0.1262).
- Local Gate B had cons_eb2 at 0.2081 vs ref 0.1913 (+0.017) — the local
  gain did NOT transfer; second documented direction failure at small
  margins (k028 -0.0023, k029 -0.0147). Implication: Gate B deltas under
  ~0.02-0.03 should not be trusted as official-direction predictors;
  only structurally different signal (new sources / trust gate) is worth
  submission slots.
- Champion remains k027-consensus-dm (+0.1262).

## k033 — State ST trained-signature run (2026-09-26, in flight)

- Training throughput diagnostics (gzip-dataset dataloader starvation):
  wall rate with gzip parts ~0.09–0.12 steps/s at GPU 0% util; after
  recompress to uncompressed parts ~0.85 steps/s wall at resume; lightning
  BatchSpeedMonitor reports ~13 bps (compute-only measure, not wall).
  Model: 127M params, hidden 768, batch 16 cell-sets x 64 cells, L4.
- Loss snapshot at resume: train_loss ~5.02 @2549 → 4.04 @2749 (raw, not
  comparable to published ST curves).
- k033 infer + calibration (checkpoint best, 128 cells/pert, seed fixed):
  315 ST targets emitted (272 panel-covered + paired-eval overlap), 5602 of
  6001 HVG columns land on the 18,533 panel axis. Median raw ST delta L2 norm
  0.673 vs consensus_w_ctr median 1.534 on the shared support → median
  rescale factor **2.215**. So the learned ST signature is systematically
  under-magnitude (~0.44× consensus) before calibration; the `st_norm` arm
  applies per-target L2 matching, `st_raw` ships the model magnitude as a
  diagnostic. The ~2.2× gap is the k020 calibration lesson recurring: a
  scale-invariant training objective gives direction without amplitude.
- Gate B round 10 (`gate-20260928-01`, arms dm_ref/st_norm_dm/st_raw_dm/
  st_mix_dm, bundle reused from gate-20260921-01, 47 eval targets, 400
  cells/pert, seed 0, elapsed 1.6h): **all three ST arms lose to dm_ref**.
  avg_score (from_replicate): dm_ref **0.2304**, st_mix_dm 0.2225,
  st_norm_dm 0.1035, st_raw_dm 0.1013. The decisive metric is pds:
  pds_cosine from_replicate dm_ref 0.711 → st_norm 0.036 / st_raw 0.046 —
  the learned ST deltas' per-target *direction* is essentially uncorrelated
  with the measured hESC responses (≈5% of the consensus arm's value); the
  50/50 blend recovers to 0.680 but still sits below reference. Secondary:
  lfc_nmae -0.050→-0.092 (norm) worse, fidelity -0.037 worse, jaccard
  slightly worse, reach marginally better (-0.060→-0.039 mix). Note dm_ref
  here (0.2304) vs the 0.1913 lineage in earlier rounds is a different
  aggregation (from_replicate vs from_baseline) — within-run comparisons are
  the valid read. Verdict: **no promotion, no submission slot.** The trained
  state model does not beat transplanted consensus means on direction
  recovery; k027 remains champion. Promotion margin rule respected: this is
  not even a marginal case — the sign survived cleanly.

## k040 official result (2026-10-12)

- `kytos-k040-sagr-dm` (entry `0CfRKgZPxSFzOh59fAXN`): official score_avg
  **+0.1286**, rank 627 — **new best** (vs k027 champion +0.1262, k038
  +0.1254). Rank lower despite higher score: field densification.
- Components: pds 0.6175, mse 0.0167, nmae 0.0910, fid -0.0187,
  reach 0.0641, jac 0.0011.
- vs k035 official (+0.1242): pds +0.006, mse +0.005, nmae +0.008,
  fid +0.002, reach +0.005, jac ~0 — every component up or flat.
- Pre-declared read (`k040-sagr-predeclared.md`): pds UP confirmed (+0.006
  vs k035 official read); avg +0.0024 vs champion is below the +0.005
  promotion margin -> read rule 2: direction improvement is real but
  small-weight. sagr becomes the Oct-22 ship delta set (per-sample
  agreement exists genome-wide for all ~18k targets, a genuine advantage
  on the unseen final panel); no further probe slots on delta-side polish.

## k042 gate-20261012-01 — dual-moment response-heterogeneity round (2026-10-12)

eval2 hESC paired transfer, 47 targets, 400 cells/pert, cell-eval2 official-style.
from_baseline scores + 6-metric avg (mean of the six scored metrics; reach is
locally negative for all arms — known gate blind spot):

| arm | lfc_nmae | mse_norm | fidelity | reach | jaccard | pds_cos | avg |
|---|---|---|---|---|---|---|---|
| dm_ref | -0.0333 | 0.0000 | 0.3662 | -0.0597 | 0.1723 | 0.7024 | 0.1913 |
| sagr_dm | -0.0320 | 0.0000 | 0.3644 | -0.0378 | 0.1712 | 0.7203 | 0.1977 |
| sagr_eta1p0 | -0.0317 | +0.0077 | 0.3664 | -0.0265 | 0.1724 | 0.7166 | 0.2008 |
| sagr_eta1p5 | -0.0339 | +0.0069 | 0.3666 | -0.0504 | 0.1745 | 0.7137 | 0.1962 |
| sagr_eta2p0 | -0.0373 | 0.0000 | 0.3671 | -0.0430 | 0.1766 | 0.7109 | 0.1957 |
| sagr_esc30 | -0.0299 | 0.0000 | 0.3655 | -0.0451 | 0.1714 | 0.7203 | 0.1970 |
| sagr_esc50 | -0.0283 | 0.0000 | 0.3651 | -0.0286 | 0.1706 | 0.7203 | 0.1998 |
| sagr_rn | -0.2775 | 0.0000 | 0.3524 | -0.0016 | 0.2003 | 0.1488 | 0.0704 |

Deltas vs sagr_dm avg: eta1p0 +0.0031, esc50 +0.0022, esc30 -0.0006,
eta1p5 -0.0014, eta2p0 -0.0020, rn -0.127 (catastrophic: pds collapses
0.72->0.15, nmae -0.28). sagr_dm vs dm_ref +0.0064 — the sagr delta set
confirms better in-gate, consistent with the k040 official read.

Diagnostics: de_proxy median ~7950 for all sagr arms vs real 396 (unchanged
over-call except sagr_rn 1518); bulk_shift norm scales with eta_std
(0.51->0.83 at eta2.0) at UNCHANGED direction cos 0.076 — scalar eta adds
magnitude spread, not new direction information; esc arms' pds identical
to sagr_dm (escaped cells contribute nothing to pds); rn bulk-shift cos
halved to 0.039 (measured sample-mean dispersion does not transplant to
per-cell scale).

Verdict per pre-declared rules (experiments/_embargoed/k042-response-het-
predeclared.md): best arm +0.003 << +0.02 promotion margin. Scalar eta is
non-monotone (1.0 helps hair, 1.5/2.0 hurt) — knob noise, not a mechanism.
escape flat. rn falsified. **Directional response-heterogeneity axis
CLOSED at gate level; no submission slot spent.** The dual-moment
bulk-vs-cell reconciliation already saturates the useful heterogeneity
budget (consistent with the depth-coupled spread found in synthetic
probes). Generation side is now fully explored under this method class.
