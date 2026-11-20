# gate-local-20260930-01 — k035 machinery v2 follow-up (xtight bracket + vagr×tight)

Run on snapflip-vultr (4 vCPU / 31 GB + 32 GB swap) with
`tools/run_k025_gate_local.py` (VPS-only, uncommitted). Same pinned
cell-eval2 pipeline, same reused bundle
(`gate-20260921-01/bundle`, anchor 477d72a6…, bundle 53931b96…), real
subset rebuilt deterministically (93,697 cells / 18,080 genes / 47 eval
targets / 38,176 controls — identical dims to round-13/14). Champion
dual-moment config on every arm: amplitude 1.0, bulk_amplitude 0.5,
pool_k 4, space bulk_delta, seed 0.

## New variants (tools/build_consensus_deltas_v2.py, VPS repo, uncommitted)

Same sources and base as round-14 (panel-scale `extract-20260921-01` npzs
at `/opt/kytos/data/vol/k035-src/`; weighted consensus, common-response
centered; v2 reproduction re-verified vs the v1 `consensus_w_ctr_agr`
artifact at max_abs_diff 2.7e-20).

- `consensus_w_ctr_agr_xtight`: identical to `consensus_w_ctr_agr_tight`
  but with clip constants (0.50, 0.90) — extends the tight end of the
  bracket one step past the round-14 winner (0.40, 0.80).
- `consensus_w_ctr_vagr_tight`: the `consensus_w_ctr_vagr`
  reliability-weighted gate (per-target `rel_s[t] = min(1, n_cells/100)`
  folded into the fused/denominator contributions) evaluated at the
  **tight** clip constants (0.40, 0.80) instead of standard (0.30, 0.70) —
  the n_cells reliability term crossed with the winning constants.

Gate mass (fraction over all T×G entries, same convention as round-14):
agr std 0.704 (19.4% zeroed); tight 0.652 (24.5%); **xtight 0.598
(29.6%)**; vagr 0.714 (18.7%); **vagr_tight 0.663 (23.6%)** — vagr_tight
keeps slightly more mass than plain tight since down-weighting a low-rel
source shrinks the denominator too. |vagr_tight − agr_tight| differs on
9.2% of entries, mean |Δ| 0.237 where different; largest per-target mean
shifts: IL10RB 0.223, UNK 0.217, HMGXB4 0.216, SPATA20 0.195, CDK8 0.183
(the same low-n_cells targets as round-14's vagr diff).

## Drift control: OK (float-epsilon)

`dm_ctr_agr_tight` re-scored as the anchor and reproduces its
gate-local-20260929-02 value exactly: scored avg
0.24562108728979462 vs 0.2456210872897947, every per-metric row identical
to ~1e-16, de_proxy median 7985, bulk_shift 0.45012 / 0.06288 — all
matching round-14. No pipeline or data drift.

## Per-arm scores

| arm | mse ratio | pds_cosine | nmae | fid | reach | jaccard | scored avg (from_repl) | mean(from_baseline) |
|---|---|---|---|---|---|---|---|---|
| dm_ctr_agr_tight (anchor) | 0.9598 | 0.8862 | 0.9821 | 0.5019 | 0.0491 | 0.2093 | 0.245621 | 0.2068 |
| dm_ctr_agr_xtight | 0.9611 | 0.8839 | 0.9831 | 0.5030 | 0.0454 | 0.2094 | 0.244205 | 0.2055 |
| dm_ctr_vagr_tight | 0.9596 | 0.8871 | 0.9818 | 0.5020 | 0.0322 | 0.2091 | 0.242905 | 0.2042 |

(`mse ratio` = mean expr_mse_unbiased_capped_norm; raw metric columns are
`run_*_agg.csv` means; `mean(from_baseline)` = mean of the scored
`from_baseline` column over the six metrics. Round-14 reference values:
dm_ref avg 0.230373 / pds 0.8538; dm_ctr_agr avg 0.240615 / pds 0.8821;
dm_ctr_vagr 0.2421 / 0.8834; dm_ctr_agr_loose 0.2409 / 0.8844.)

vs `dm_ctr_agr` (confirmed recipe, Δ scored avg / Δ raw pds):
xtight +0.0036 / +0.0017; vagr_tight +0.0023 / +0.0050;
(anchor tight +0.0050 / +0.0042).
vs `dm_ctr_agr_tight` itself: xtight −0.0014 / −0.0023;
vagr_tight −0.0027 / +0.0009.

## Reading

- **xtight saturates and slightly reverses.** The gate-tightness curve
  over the bracket is loose 0.2409 < std 0.2406 < tight 0.2456 > xtight
  0.2442 — the local optimum sits at (0.40, 0.80) or marginally inside it,
  not beyond. xtight still beats the confirmed `consensus_w_ctr_agr`
  recipe on both avg and pds, but it is dominated by plain tight on both.
  Constant-fitting past tight is not worth further slots.
- **vagr×tight does not beat plain tight on avg** (0.2429 vs 0.2456)
  despite a slightly higher raw pds (0.8871 vs 0.8862) — the reliability
  term's small avg gain at standard constants (+0.0015 in round-14) flips
  sign at tight constants, with the loss concentrated in reach (0.0322 vs
  0.0491; scored from_replicate −0.0450 vs −0.0266). Reliability
  re-weighting and aggressive clipping are not additive here.
- **Best single-variable probe vs the confirmed `consensus_w_ctr_agr`
  baseline remains `consensus_w_ctr_agr_tight` (0.40/0.80)**: it is the
  only arm that beats ctr_agr on both avg (+0.0050) and pds (+0.0042)
  *and* is not dominated by another measured variant. xtight and
  vagr_tight both beat ctr_agr on avg+pds but lose to agr_tight on avg —
  neither earns a submission slot; the agr clip-constant axis is
  exhausted at tight.
- Caveat per the revised submission protocol (AGENTS.md 2026-09-29): Gate
  B is hESC-only and has inverted orderings before — these are
  measurement values, not a veto/promotion verdict. Any submission would
  need a pre-declared component-level prediction.

Diagnostics (results.json): de_proxy medians 7979–8014 vs real 396 (all
arms ~same over-calling as ref); bulk_shift norms 0.429–0.452, cosine vs
real 0.063–0.065 — xtight trims bulk amplitude further (0.429 vs tight's
0.450) without gaining direction. Harness elapsed 3,400 s (~57 min) for
3 arms + real-subset rebuild.

Artifacts: `variant_consensus_w_ctr_{agr_xtight,vagr_tight}.npz` +
`build_manifest_v2.json` (updated; `written_this_run`/`skipped_existing`
recorded) at `/opt/kytos/data/vol/k035-machinery/`;
`tools/build_consensus_deltas_v2.py` and `tools/run_k025_gate_local.py`
(VPS repo, uncommitted); gate tmux session `k035-gate`, log
`/opt/kytos/logs/gate-local-20260930-01.log`.
