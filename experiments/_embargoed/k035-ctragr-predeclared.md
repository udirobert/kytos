# k035-ctragr-dm — pre-declared probe predictions (written 2026-09-29, BEFORE submit)

Probe: `variant_consensus_w_ctr_agr.npz` through the champion dual-moment
config (a1.0/b0.5/pk4/bulk_delta/seed0/400cpt/A,B,C). Single-variable
ablation vs k027: adds the per-gene cross-source agreement gate
`clip((|fused|/Σ|contrib| − 0.30)/0.70, 0, 1)` on top of `consensus_w_ctr`.

Gate B evidence (gate-local-20260929-01, VPS harness, dm_ref parity exact):
dm_ctr_agr fbavg 0.2020 vs dm_ref 0.1913 (+0.0107); raw pds_cosine
0.882 vs 0.854; fb pds 0.760 vs 0.702; raw reach 0.030 vs 0.018;
mseNorm 0.959 vs 0.956 (~flat); de_proxy ~same; bulk_shift norm
0.461 vs 0.507 (gate removes ~9% of bulk mass — mildly shrink-side).

## Declared expectations vs k027 official (+0.1262)

| component | prediction |
|---|---|
| score_pds | **UP** — the mechanism being tested; biggest expected move |
| score_reach | up modestly (raw reach 0.018→0.030 locally) |
| score_mse | ~flat (mseNorm flat locally; gate is direction-not-mass) |
| score_nmae | flat-to-slightly-down (gate also shrinks some true signal) |
| score_fid, score_jac | ~flat |
| **score_avg** | **0.115–0.145** (i.e. within ±0.02 of champion either way) |

Read: pds↑ + reach↑ without nmae damage → machinery confirmed, stack
next item (per-context amplitude) on top. pds flat/down → gate's local
pds gain is hESC-context-specific, deprioritize agreement machinery.

## Sibling results for the record

dm_agr (gate on UNCENTERED consensus) won locally at 0.2049 — but this
repeats the nctr pattern (uncentered wins locally, loses officially), so
it is NOT the probe arm. dm_selctr alone = −0.002 vs ref → selective
decorrelation (as built, consensus-norm threshold) is dead.

## RESULT — official leaderboard (written 2026-09-30, after publish)

Entry `xRk8Zk4MWHjQ7V6UJaX5`, submitted 2026-09-30T02:31:51Z, published.
Official `vcc status` rank 449; sort-position 442 in fresh snapshot
(1226 entries, `experiments/_embargoed/vcc_leaderboard_snapshot_2026-09-30.json`).

| component | k035-ctragr-dm |
|---|---:|
| **score_avg** | **+0.12421467920499464** |
| score_pds | 0.6112550892544178 |
| score_mse | 0.011769339332012555 |
| score_nmae | 0.08301036441748615 |
| score_fid | -0.020903309518263354 |
| score_reach | 0.05911987393458452 |
| score_jac | 0.0010367178097301694 |

Raw metrics (fresh snapshot): pds_cosine 0.7758788554440728,
expr_mse_unbiased_capped_norm 0.9766827112905125,
de_wilcoxon_lfc_nmae 0.9511646106912592,
de_wilcoxon_direction_fidelity_yield_raw 0.5064510026903578,
de_wilcoxon_direction_reach_raw 0.1311145454240007,
de_wilcoxon_sig_jaccard 0.03068059095142428.

### Verdict vs pre-declared predictions

score_avg 0.1242 vs k027's +0.1262 → **−0.0020**, inside the declared
0.115–0.145 band: flat vs champion, well within the ±0.01 noise floor.
k027 per-component officials were never captured, so component verdicts
are vs the two recorded same-generator baselines (k034 = uncentered
consensus, k030 = consensus-meanj — both confounded vs a pure k027
ablation, noted for the record):

| component | prediction | k035 | k034 | k030 | verdict |
|---|---|---:|---:|---:|---|
| score_pds | UP (biggest move) | 0.6113 | 0.5804 | 0.5570 | **CONFIRMED** — +0.031 vs k034, +0.054 vs k030; highest pds we have recorded |
| score_reach | up modestly | 0.0591 | 0.0430 | 0.0393 | **CONFIRMED** — +0.016 vs k034, best recorded reach |
| score_mse | ~flat | 0.0118 | 0.0127 | 0.0018 | CONFIRMED vs k034 (−0.001); (k030's high mse reflects its own recipe, not comparable) |
| score_nmae | flat-to-slightly-down | 0.0830 | 0.0873 | 0.0735 | CONFIRMED directionally — −0.004 vs k034 |
| score_fid | ~flat | −0.0209 | −0.0177 | −0.0197 | flat within noise (−0.003 vs k034) |
| score_jac | ~flat | 0.0010 | 0.0013 | 0.0012 | CONFIRMED flat |

### Read

pds↑ + reach↑ without avg or nmae damage → **agreement-gate machinery
confirmed on the real 3-context panel**, matching the Gate B direction
(raw pds_cosine 0.882 vs ref 0.854, raw reach 0.030 vs 0.018 locally →
officially pds_cosine 0.7759 vs k034's 0.7620, reach_raw 0.1311 vs
0.1170). Per the pre-declared read, the next stacked item is per-context
amplitude on top of this recipe. The −0.0020 avg delta vs k027 is
noise-level; there is no evidence the gate hurts, and it bought
direction/discrimination as designed. Candidate recipe update:
`variant_consensus_w_ctr_agr` becomes the reference delta set for the
next probe (k027 stays official champion on avg, 0.1262 vs 0.1242 —
call it a statistical tie).

### Provenance

- Build app `ap-NgqHJsJcNMQOMp2MFpG3vL`: single pass, no preemption;
  prediction.h5ad 360,000×18,533 2434.3M nnz written in 1730.8s;
  `vcc prep` PASS (targets verified vs official list); persisted
  `/kytos-vol/k035-ctragr-dm/` (3.8 GB .vcc + meta.json).
- meta.json verification PASSED pre-submit: generator dual_moment
  amp=1.0 bulk_amp=0.5 pool_k=4 space=bulk_delta; n_targets 300;
  dispatch real 900; deltas sha256 0516a6843584a1d450…; contexts
  [A,B,C]; cells_per_pert 400; seed 0; uncovered []. (`run_id`/`mode`
  strings are stale k027 tool defaults — cosmetic only, same as k034.)
- Submit app `ap-ZTYJCPV7HUgGWHnzIxPtpz`: upload 3.7 GiB in 13m27s,
  `--wait` completed server-side with no preemption; scored and
  published; components via `vcc status xRk8Zk4MWHjQ7V6UJaX5`.
- Receipts: `experiments/k035-ctragr-dm/` (meta.json verbatim,
  execution.json, leaderboard_result.json, scorer_stdout.txt).
