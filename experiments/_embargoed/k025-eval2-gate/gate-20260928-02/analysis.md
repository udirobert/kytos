# Gate B round 11 — bulk-amplitude (MSE-channel) sweep + reach probes

Run `gate-20260928-02` (2026-09-28). Prompted by the leaderboard
decomposition: every top-100 entry has score_mse >= 0.145 and
score_reach >= 0.15; k028 official components had mse 0.000, reach
score ~0.07 — mse+reach ≈ 60% of the top-100 gap.

Prior finding revised: earlier analysis read "all arms worse than null"
from the transport-arm numbers. Raw expr_mse_unbiased_capped /
expr_distance_unbiased (ratio of agg means) shows dm arms already beat
the control point (1.0): dm_ref 0.956 vs null 1.07.

Raw means and from_baseline (fb) scores per arm:

| arm | mseNorm | pds | nmae | fid | reach | jac | fb avg |
|---|---:|---:|---:|---:|---:|---:|---:|
| dm_ref (a1.0 b0.5) | 0.956 | 0.702 | -0.033 | 0.366 | -0.060 | 0.172 | 0.1913 |
| dm_b1p0 | 0.959 | 0.700 | -0.032 | 0.366 | -0.051 | 0.173 | 0.1926 |
| dm_b1p5 | 1.010 | 0.702 | -0.033 | 0.366 | -0.049 | 0.174 | 0.1931 |
| dm_b2p0 | 1.094 | 0.700 | -0.034 | 0.365 | -0.048 | 0.173 | 0.1927 |
| dm_b3p0 | 1.368 | 0.690 | -0.034 | 0.360 | -0.023 | 0.166 | 0.1933 |
| dm_a1p5_b1p5 | 1.013 | 0.701 | -0.043 | 0.368 | -0.022 | 0.181 | 0.1974 |
| eb2_b1p0 | 0.942 | 0.712 | -0.041 | 0.366 | -0.022 | 0.175 | 0.2000 |
| nctr_b1p0 | 0.964 | 0.742 | -0.035 | 0.369 | -0.037 | 0.179 | 0.2029 |

bulk_shift diagnostic (median ||s_t|| / median cos to real bulk shift,
self-gene zeroed):

| arm | norm | cos |
|---|---:|---:|
| real | — | — |
| dm_ref | 0.507 | 0.074 |
| dm_b1p0 | 1.012 | 0.075 |
| dm_b1p5 | 1.516 | 0.075 |
| dm_b2p0 | 2.019 | 0.075 |
| dm_b3p0 | 3.021 | 0.075 |
| dm_a1p5_b1p5 | 1.516 | 0.075 |
| eb2_b1p0 | 0.632 | 0.066 |
| nctr_b1p0 | 1.071 | 0.063 |
| st_norm_dm | 0.448 | 0.001 |
| st_raw_dm | 0.181 | 0.000 |
| st_mix_dm | 0.342 | 0.047 |

## Findings

- mseNorm is controlled by bulk_amplitude alone (amplitude 0.8-1.5
  invariant in round 3; a1p5_b1p5 ≈ b1p5 here). Feasible-bound
  projection confirmed saturating at high bulk_amp — direction cos stays
  ~0.075 while ||shift|| grows linearly, so the bulk moment does track
  the requested amplitude until the U turns.
- Inverted-U optimum ≈ b0.7-1.0 (~0.95 raw); min gain vs ref is ~0.01
  raw → ≈ +0.01 official score_mse at best. **The mse channel is
  direction-bound, not amplitude-bound**: bulk-shift cosine ~0.075 vs
  real on the 47 hESC eval targets. Top-100 mse (raw ~0.84) needs
  direction ~0.4. Same signature-content wall as pds — no cheap lever.
- reach: raw reach 0.018 (ref) → 0.052-0.053 at b3.0 / a1p5_b1p5 /
  eb2_b1p0, but fb reach stays negative everywhere; baseline arm
  out-reaches all submissions on this eval subset.
- Unhandled small positives: nctr_b1p0 (uncentered consensus) +0.0116,
  eb2_b1p0 +0.0087, dm_a1p5_b1p5 +0.0061 — all below the +0.02 local
  confident-transfer bar. nctr gain is fb pds (+0.04) — hypothesis:
  centering removed shared-response signal that local pds rewards.
  Caveat: hESC-only eval; cannot arbitrate source recipes (k030).
- Composition test queued: gate-20260928-03 (dm_ref + eb2_a1p5_b1p5 +
  nctr_a1p5_b1p5).
- Leaderboard calibration: official mse zero point ≈ raw 0.99, anchor ≈
  raw 0.04 (inferred from score/raw pairs on public leaderboard entries;
  k028 official mse 0.000 ↔ local 0.956 < baseline).

Files: scored_*.csv + run_*_agg.csv pulled 2026-09-28; results.json
pending (st_* arms still scoring when pulled).
