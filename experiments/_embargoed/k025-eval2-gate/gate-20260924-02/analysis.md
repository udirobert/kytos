# Gate B round 9 — generator-structure arms (run gate-20260924-02)

Local-only (embargoed until Oct 22). 8 arms, consensus_w_ctr deltas, dm a1.0/b0.5
(k027 champion recipe), 47 H1-val targets, 400 cells/pert, reused bundle
gate-20260921-01. Run spanned a client DNS kill at ~00:00; resumed detached
(ap-xL69YfLMAXF8sEMmxAW4hZ) and completed.

## Scores (from_baseline, six official metrics + avg)

| arm | pds | nmae | mse | fid | reach | jac | avg6 |
|---|---|---|---|---|---|---|---|
| dm_ref | 0.7024 | -0.0333 | 0.0000 | 0.3662 | -0.0597 | 0.1723 | **0.1913** |
| dm_soft0p02 | 0.7599 | -0.0389 | 0.0000 | 0.3583 | -0.0328 | 0.1731 | **0.2033** |
| dm_soft0p05 | 0.7797 | -0.0525 | 0.0000 | 0.3454 | -0.0632 | 0.1678 | 0.1962 |
| dm_mass | 0.6864 | -0.0321 | 0.0028 | 0.3639 | -0.0440 | 0.1705 | 0.1913 |
| dm_mass_soft0p05 | 0.7335 | -0.0526 | 0.0000 | 0.3450 | -0.0514 | 0.1642 | 0.1898 |
| dm_nb_pk1 | 0.5311 | -0.0696 | 0.0000 | 0.3806 | -0.0084 | 0.2324 | 0.1777 |
| dm_nb_pk4 | 0.5527 | -0.0582 | 0.0000 | 0.2675 | -0.0199 | 0.1114 | 0.1422 |
| dm_nb_pk4_soft0p05 | 0.4454 | -0.0701 | 0.0000 | 0.2358 | -0.0257 | 0.0997 | 0.1142 |

Drift check: dm_ref = 0.1913, identical to the round-5/8 champion reference —
gate is stable across the bundle reuse.

## de_proxy (median per-target Welch |t|>4.5 DE calls; real = 396)

ref 7954 · nb_pk4 **326** · nb_pk1 6279 · soft0p02 8001 · soft0p05 8183 ·
mass 7962 · mass_soft0p05 8173 · nb_pk4_soft0p05 194

## Reading

1. The DE over-call mechanism hypothesis is CONFIRMED mechanically and
   REFUTED monetarily: NB gamma-Poisson emission at pool_k=4 calibrates DE
   counts 20x -> 0.82x of real, yet avg6 collapses 0.1913 -> 0.1422. Per-cell
   variance costs more on pds/fid/mse than the DE-count calibration buys on
   reach/jac (jac actually fell, 0.172 -> 0.111 — the scorer's jaccard
   evidently rewards the deterministic arm's *signal-set* overlap, not count
   calibration; nb_pk1 gets jac 0.232 best but pds 0.531).
2. Soft-threshold 0.02 is the only arm above reference (+0.012 avg6), driven
   by pds 0.70 -> 0.76 and reach -0.060 -> -0.033. It does NOT fix DE
   over-call (8001), so its win is "trim delta noise", not the mechanism it
   was designed to test. This is knob-class tuning — same class as eb2/pk12
   which failed to transfer officially (k028/k029 regressions).
3. Mass-centering is exactly neutral (0.1913) — composition-shift hypothesis
   dead.

## Verdict

No promotion candidate from this round. The generator-structure search (NB
dispersion) is falsified on the official metric mix even though the mechanism
worked as designed. soft0p02's +0.012 is below the gate-transfer confidence
band for knob changes; spending a slot on it is not recommended.

Note: three `scored_cons_ctxw*.csv` files appeared in the same volume dir from
a parallel session's context-weighted round — not part of this analysis;
their results.json (if any) lives in that session's bookkeeping.

## Addendum — parallel session's context-weighted arms (same run dir)

cons_ctxw1_eb2_ctr and cons_ctxw2_eb2_ctr: avg6 0.2096 (+0.018 vs dm_ref
0.1913); cons_ctxw2_ctr: 0.2059 (+0.015). Best Gate B recipe-class deltas
recorded, concentrated in reach (-0.060 -> ~0.000) and jaccard (0.172 ->
0.205-0.215) — the k021-flagged modeling-bound metrics.

Transfer-calibration read (k027 table: signature-class attenuates ~4.3x):
+0.018 local -> ~+0.004 official expected — marginal, and the eb2 component
already failed officially once (k029). Recommendation: do not spend a slot
without a second corroborating gate round or a slot we can spare; this is
below the promotion bar the calibration table implies.
