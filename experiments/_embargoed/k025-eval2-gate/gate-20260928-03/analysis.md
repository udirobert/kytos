# Gate B round 12 — composition probes (gate-20260928-03, 2026-09-28)

Three arms: dm_ref drift control, eb2×a1.5/b1.5, nctr×a1.5/b1.5 —
testing whether the round-11 marginal positives compose.

## Results

| arm | mseNorm | fb avg | Δ vs ref |
|---|---:|---:|---:|
| dm_ref | 0.956 | 0.1913 | — |
| eb2_a1p5_b1p5 | 0.955 | 0.1990 | +0.0077 |
| nctr_a1p5_b1p5 | 1.024 | 0.2026 | +0.0113 |

dm_ref reproduced 0.1913 exactly (third identical run — zero drift).
Component detail in scored_*.csv / run_*_agg.csv (pulled).

## Interpretation

- **Compositions do not stack.** eb2 alone at a1.0/b1.0 scored 0.2000
  (round 11) — eb2×a1.5/b1.5 at 0.1990 is a slight regression, not a
  sum. nctr alone was 0.2029 (round 11); nctr×a1.5/b1.5 = 0.2026 — the
  amplitude bump added nothing on the uncentered deltas either. The
  round-11 positives were all ~the same +0.01 pool (direction-quality
  signal), not orthogonal levers.
- nctr bulk_shift norm 1.61 — uncentered deltas carry ~2.7x the bulk
  magnitude of centered ones at the same bulk_amplitude (common
  component is large). Its mseNorm 1.024 > ref — the common-response
  mass that lifts local pds (+0.04) also worsens bulk error. Net local
  +0.012; under the known signature-side attenuation (~4x) expected
  official ≈ +0.003 — below transfer confidence.
- **Verdict: no promotion candidate.** Best local arm is ~+0.011 over
  drift control; the +0.02 bar (k028 lesson) is not met by any arm in
  rounds 11–12. No submission slot spent.
- infra note: two Modal preemptions this round; atomic
  write-then-rename added to pred writes — the `exists()` resume check
  previously mistook a truncated h5ad for complete.

## Standing after rounds 11–12

Local lever space appears exhausted: amplitude (bulk and per-cell),
dispersion, signature shrinkage, centering, regulons, and learned
signatures are each measured within ±0.01 of champion. The mse/reach/pds
gap to top-100 is one constraint (signature direction), not three
independent channels.
