# k034-nctr-dm — official leaderboard result — EMBARGOED until Oct 22

Single-variable ablation vs champion k027: identical dual-moment generator
(amplitude 1.0, bulk_amplitude 0.5, pool_k 4, bulk_delta space, seed 0,
400 cells/pert, contexts A/B/C, dispatch real 900, 0 uncovered) but deltas =
`variant_consensus_w.npz` (sha256 c0fff9dd28da) — the UNCENTERED weighted
consensus; the `*_ctr` per-gene-median-across-targets centering removed.

## Official result (entry SkPX8WRYGVfEFEcQ3WzI, submitted 2026-09-28T16:36:20Z)

| component | k034-nctr-dm |
|---|---:|
| **score_avg** | **+0.11783623928991634** |
| rank | 455 (official `vcc status`; sort-position 448 in fresh snapshot, 1202 entries) |
| score_pds | 0.5803574616759354 |
| score_mse | 0.012704621974919061 |
| score_nmae | 0.08729358859060325 |
| score_fid | -0.017717181848454864 |
| score_reach | 0.04303877487555712 |
| score_jac | 0.0013401704709381547 |

Raw metrics on the fresh snapshot entry: pds_cosine 0.7620104050538834,
expr_mse_unbiased_capped_norm 0.9757903755394124,
de_wilcoxon_lfc_nmae 0.9486655844235463,
direction_fidelity_yield_raw 0.5074139998103859,
direction_reach_raw 0.11698863988423555,
sig_jaccard 0.030794478494650827.

## Comparison vs k027 official

k027 (`fN4wjAp9BUEvHtGWk0az`, 2026-09-22): **score_avg +0.1262, rank
308/1088** — per-component officials were NEVER captured (leaderboard page
showed only overall at capture; the entry is no longer retrievable via the
API or `vcc status`). Only the overall delta is verifiable:

- **score_avg: 0.1178 − 0.1262 = −0.0084 — REGRESSION vs champion.**

## Closest full-component baseline (k030, same generator, different deltas)

k030 (`A1N2nYKZ07jKewReEUMp`, consensus-meanj + dual-moment, same
amp/bulk/pk/seed; NOT an ablation-matched control — deltas recipe differs):

| component | k034-nctr | k030 | diff |
|---|---:|---:|---:|
| score_avg | 0.1178 | 0.1088 | +0.0090 |
| pds | 0.5804 | 0.5570 | +0.0233 |
| mse | 0.0127 | 0.0018 | +0.0109 |
| nmae | 0.0873 | 0.0735 | +0.0138 |
| fid | -0.0177 | -0.0197 | +0.0020 |
| reach | 0.0430 | 0.0393 | +0.0038 |
| jac | 0.0013 | 0.0012 | +0.0002 |

## Pre-declared prediction check (pds up, mse slightly down, rest ~flat vs k027)

- **Verdict vs k027: overall REGRESSION (−0.0084).** Per-component
  attribution vs k027 is impossible (components never captured).
- Uncentered deltas did NOT lift overall. Whatever pds/direction gain the
  missing centering produced was outweighed elsewhere.
- Local Gate B had centering worth ~+0.016 avg (w_ctr 0.131 > w 0.115,
  pds 0.635 vs 0.547 on hESC eval). The official result (−0.0084) is
  directionally consistent with that local ordering — centering helps, it
  does not delete signal.
- Interpretation: keep `variant_consensus_w_ctr` as the ship recipe.
  k027 stays champion. This closes the open "which recipe ships blind —
  k027 champion vs the uncentered variant" question from the strategy doc
  §final-phase readiness: ship the centered k027 recipe.
- Caveat: single draw from the official scorer; local↔official noise floor
  is ~±0.01 (k028 lesson), so −0.0084 is within noise of flat — but there
  is no evidence the uncentered variant is better, and every available
  comparison favors centering.

## Provenance

- Build app `ap-miF8rjf4PwdNKj6yuysnzS` (preempted once at ~37 min, auto-
  retried; second attempt completed: prediction.h5ad 360,000×18,533
  2433.9M nnz in 1873.7s → `vcc prep` PASS → persisted
  `/kytos-vol/k034-nctr-dm/prediction.prep.vcc` 3.8 GB + meta.json).
- Submit app `ap-osIvDvB5xWg6O5q7wxB2Qb`: upload 3.7 GiB in 13m58s;
  preempted during `--wait`; retry declined ("submission already in
  progress") because entry was already queued. Scored server-side,
  published; components read via `vcc status SkPX8WRYGVfEFEcQ3WzI`.
- meta.json verification PASSED: generator dual_moment amp=1.0
  bulk_amp=0.5 pool_k=4 space=bulk_delta; n_targets 300; dispatch real
  900; deltas_npz=/root/variant_consensus_w.npz sha256 c0fff9dd28da;
  contexts [A,B,C]; cells_per_pert 400; seed 0; uncovered [].
  (meta.json `run_id`/`mode` strings are stale k027 tool defaults —
  cosmetic only.)
- Fresh leaderboard snapshot: `experiments/_embargoed/vcc_leaderboard_snapshot_2026-09-28.json`
  (1202 entries). Note: only the newest published entry per team appears —
  k030/k027 not present.
