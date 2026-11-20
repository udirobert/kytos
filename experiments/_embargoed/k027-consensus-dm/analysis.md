# k027 leaderboard analysis — EMBARGOED until Oct 22

## Result

`kytos-k027-consensus-dm`: **+0.1262, rank 308/1088** (entry
`fN4wjAp9BUEvHtGWk0az`, submitted 2026-09-22). Consensus_w_ctr deltas +
dual-moment generation (amplitude 1.0, bulk_amplitude 0.5) — the
`cons_dm_a1p0` Gate B arm config.

## Transfer calibration (leaderboard vs Gate B local avg_score)

| change | local delta | official delta | attenuation |
|---|---:|---:|---:|
| signature swap (k026: consensus vs k562 through transport) | +0.032 | +0.0074 | ~4.3x |
| generation swap (k027: transport->dual-moment, same deltas) | +0.060 | +0.059 | ~1.0x |

**Finding:** generation-side improvements transfer to the leaderboard
essentially undamped; signature-side improvements attenuate ~4x.
Interpretation: generation acts on metric mechanics (count realism, DE
call structure, library-depth fidelity) which are context-independent;
signature direction is context-dependent and partially wrong on the
full 300-target/3-context panel vs the 47-target hESC eval subset.

## Canonical Gate B table (recomputed from scored CSVs, from_baseline)

| arm | avg | pds | nmae | fid | reach | jac |
|---|---:|---:|---:|---:|---:|---:|
| oracle_hesc | 0.693 | 1.000 | 0.462 | 0.685 | 0.999 | 0.386 |
| cons_dm_a1p0 | 0.191 | 0.702 | -0.033 | 0.366 | -0.060 | 0.172 |
| cons_dm_a0p6 | 0.190 | 0.705 | -0.035 | 0.362 | -0.055 | 0.161 |
| consensus_w_ctr | 0.131 | 0.635 | -0.098 | 0.182 | -0.007 | 0.074 |
| cons_w_ctr_pncap | 0.129 | 0.606 | -0.096 | 0.185 | -0.000 | 0.077 |
| consensus_w | 0.115 | 0.547 | -0.112 | 0.204 | -0.033 | 0.085 |
| consensus_mean | 0.111 | 0.541 | -0.099 | 0.178 | -0.030 | 0.076 |
| k562_ds1p7_pncap | 0.104 | 0.504 | -0.282 | 0.308 | -0.045 | 0.140 |
| cons_kd1p3 | 0.102 | 0.506 | -0.085 | 0.121 | 0.019 | 0.054 |
| k562_ds1p7 | 0.099 | 0.482 | -0.287 | 0.305 | -0.049 | 0.140 |
| cons_kd1p0 | 0.096 | 0.557 | -0.078 | 0.084 | -0.030 | 0.043 |
| k562_ds1p0 | 0.087 | 0.402 | -0.140 | 0.203 | -0.028 | 0.085 |
| cons_kd0p7 | 0.083 | 0.500 | -0.076 | 0.056 | -0.018 | 0.035 |
| cons_kd1p0_ds1p0 | 0.052 | 0.483 | -0.059 | -0.083 | -0.018 | -0.014 |
| null | -0.088 | -0.066 | -0.070 | -0.278 | -0.067 | -0.048 |

Note: earlier in-flight quick-reads (dm 0.230, transport 0.142) were
overstated — canonical CSV recompute gives dm 0.191 / transport 0.131.
Ranking unchanged. Centering worth ~+0.016 (w_ctr > w); kd_std=2.0 was
the transport optimum; dual-moment needs no kd_std.

## Headroom remaining

- dm a1.0 vs a0.6: +0.002 local — amplitude is near a plateau.
- Oracle ceiling 0.693 local: signature content is still the binding
  constraint; generation took us from 0.131 to 0.191 of a 0.78-range.
- Unmeasurable components: H1 weighting (0/47 coverage), per-context
  dispatch (single-context eval). Leaderboard-only probes.
- Top-100 threshold ~+0.15-0.17: we are at +0.1262 (rank 308) — within
  ~+0.03 of the bar, but the bar will move before Oct 22 and the final
  test set is new cell lines.

## expr_mse saturation analysis (2026-09-22)

`expr_mse_unbiased_capped_norm` scores the predicted bulk mean-expression
vector vs real (log1p-normalized comparator, on-target gene excluded).
Raw norm values (lower=better): oracle 0.355, null ~1.07 (baseline),
consensus_w_ctr 1.210, k562_ds1p0 1.335, k562_ds1p7 2.075. All non-oracle
arms are WORSE than the null baseline -> score clamps to 0. Deltas add
net error to the bulk mean (||wrong_delta - true_delta|| > ||true_delta||
at our direction accuracy and applied amplitude). Correction-cap bite is
~0.0002 for all arms -- no generation-side lever. Only accurate signature
direction (or amplitude shrinkage toward null, which trades away the DE
metrics) moves it. Deprioritized.

---

## Gate B rounds 3–5 (2026-09-22) — dual-moment micro-sweep + k028 decision

All runs on `consensus_w_ctr` deltas, dual-moment generator, 47-pair hESC eval,
cell-eval2 0.16.0 vcc2026, 5 anchors. Canonical avg = mean of six
`from_baseline` scores. Run-to-run drift verified zero (`dm_a1p0_ref` re-score
0.1913 == round-2 value).

### Round 3 (gate-20260922-03) — axis isolation, bulk=0.5/pk=4 default

| arm | avg | note |
|---|---:|---|
| dm_a1p0_pk8 | 0.1997 | pool_k=8 lifts fid +0.015, jac +0.026 |
| dm_a1p0_b0p3 | 0.1967 | lower bulk weight slightly better |
| dm_a1p5_b0p5 | 0.1955 | amplitude plateau (0.8–1.5 within ~0.005) |
| dm_a0p8_b0p5 | 0.1942 | |
| dm_a1p3_b0p5 | 0.1941 | |
| dm_a1p0_b0p7 | 0.1932 | |
| dm_a1p0_log2fc | 0.1903 | log2fc space no better than bulk_delta |
| dm_a1p0_pk2 | 0.1004 | pool_k=2 catastrophic (fid −0.04, jac 0.011) |

### Round 4 (gate-20260922-04) — regulon overlay (Track 2b Stage 0)

| arm | avg |
|---|---:|
| reg_w03 | 0.1924 |
| reg_w08 | 0.1916 |
| dm_a1p0_ref | 0.1913 |
| reg_only | 0.1647 |

Per-target (pds): NFE2L1 0.609→0.978 at full strength (regulon right);
DOT1L 0.826→0.870 at w03; TCF7L2 0.239→0.022 (regulon badly wrong);
MAX/JAZF1 saturated. No cheap gate separates winners from losers
(regulon↔consensus agreement, edge count, regulon↔lineage agreement all
noise-level). Verdict: real but unsigned signal — parked.

### Round 5 (gate-20260922-05) — pk/bulk combination

| arm | avg | pds | nmae | fid | jac |
|---|---:|---:|---:|---:|---|
| dm_a1p0_b0p3_pk12 | 0.2009 | 0.706 | −0.033 | 0.382 | 0.203 |
| dm_a1p0_b0p5_pk12 | 0.2004 | 0.703 | −0.033 | 0.382 | 0.203 |
| dm_a1p0_b0p3_pk8 | 0.1996 | 0.703 | −0.033 | 0.382 | 0.198 |

pk8→pk12 flat (+0.001); b0p3≈b0p5. Generation tuning plateaued at ~0.20.

### k028 decision

Config: `amplitude=1.0, bulk_amplitude=0.3, pool_k=12` (+0.0096 over the
k027 config 0.1913). Build launched via
`tools/modal_k028_dm_pk12_submit.py` (same consensus deltas, sha 336f2cbc).
If generation transfer stays ~1:1, expected official ≈ +0.13–0.135.
Marginal gain is small; submission justified because the slot is cheap
and every banked point matters at the margin for top-100.

---

## k028 official result (2026-09-23)

`kytos-k028-consensus-dm-pk12` — submitted 2026-09-23 00:05 UTC
(delayed server-side submit after daily-allowance reset).

- **Overall: 0.1239 — rank 352/1115**
- Components (from scorer email, NOT public — leaderboard shows only
  overall): pds 0.6058, mse 0.0000, nmae 0.0876, fid −0.0182,
  reach 0.0655, jac 0.0028

vs k027 official +0.1262 (rank 308/1088): **−0.0023 regression.**
The +0.0096 local gain (pk4/b0.5 → pk12/b0.3) did not transfer.

Interpretation:

- Sub-0.01 local Gate-B differences are at/below the official-transfer
  noise floor. The generation sweep's tail-end gains are not
  leaderboard-meaningful; a candidate needs ~+0.02 local to be a
  confident official improvement.
- Generation axis doubly confirmed exhausted — the best local arm
  regressed officially. No further generation sweeps justified.
- expr_mse component still exactly 0.0000 — consistent with the
  metric analysis (signature-direction-bound, no generation lever).
- Rank drift 308→352 partly reflects leaderboard growth (1088→1115),
  but k027 remains the champion; k028 is recorded as a completed
  experiment, not a regression to chase.

Strategic state after k028: all local levers exhausted or falsified
(generation swept to plateau, Track 2a LOLO-falsified, Track 2b parked
unsigned). Remaining options are unmeasurable hypotheses only.

---

## Gate B rounds 6–7 (2026-09-23) — per-gene agreement shrinkage (EB)

New axis: exploit cross-lineage *variance*, not just the mean. Variant
`consensus_eb_ctr`: unit-normalized per-lineage deltas → per-gene
reliability lam = snr^γ/(snr^γ+1) with snr = mean²/var → K562-norm
rescale → common-response centering. Builder: `tools/build_eb_consensus.py`.

LOLO screen (delta-space, held-out fold vs consensus-of-3):
- γ sweep monotone-improving held-out top-200 subspace cosine:
  wmean 0.233 → eb0.5 0.275 → eb1 0.285 → eb2 0.291 → eb4 0.292
  (fold-mean); jac ~flat 0.023→0.025.
- Per-target best-source oracle +0.08–0.15 subcos over consensus —
  headroom exists but requires a per-target trust gate (same wall as 2b).

Gate results (dm a1.0/b0.5/pk4 = k027 config; ref = dm_a1p0_ref 0.1913):

| arm | avg | pds | nmae | fid | reach | jac | mse |
|---|---:|---:|---:|---:|---:|---:|---:|
| cons_eb_dm (γ1) | 0.1969 | 0.734 | −0.040 | 0.366 | −0.045 | 0.167 | 0 |
| cons_eb2_dm (γ2) | 0.2039 | 0.719 | −0.039 | 0.365 | +0.004 | 0.174 | 0 |
| cons_eb4_dm (γ4) | 0.2015 | 0.704 | −0.042 | 0.366 | +0.002 | 0.179 | 0 |
| dm_a1p0_ref      | 0.1913 | 0.702 | −0.033 | 0.366 | −0.060 | 0.172 | 0 |

- γ=2 is the optimum (eb4 past peak). New local best 0.2039 (+0.0126
  over ref); reach positive for the first time in a non-oracle arm.
- Mechanism: shrinkage denoises direction (pds +0.017–0.031) and
  recovers DE-set recall, at small nmae/jac cost.
- Round 8 in flight: cons_eb2 × dm pk12/b0.3 (compose the two
  independent winners; round-5 best gen config was 0.2009).

### Round 8 (gate-20260923-03) — composition

`cons_eb2_dm_pk12` (eb2 deltas × dm a1.0/b0.3/pk12): **avg 0.2081** —
new local best. pds 0.716, nmae −0.040, fid 0.381, reach −0.020,
jac 0.212, mse 0. Winners partially compose (+0.0168 over ref vs
+0.0126 eb2-alone, +0.0096 pk12-alone). Selected as k029:
`kytos-k029-consensus-eb2-dm-pk12`, build via
`tools/modal_k029_eb2_dm_pk12_submit.py`.

Expected official is uncertain: pk12 already failed to transfer once
(k028 −0.0023) and signature-side changes historically attenuate ~4×.
Submission justified as best-available candidate with positive EV —
k027's standing is unaffected either way.
