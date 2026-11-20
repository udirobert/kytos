# gate-local-20260929-02 — k035 machinery v2 round (variance-aware agreement + agr bracket)

Run on snapflip-vultr (4 vCPU / 31 GB + 32 GB swap) with
`tools/run_k025_gate_local.py` (VPS-only, uncommitted). Same pinned
cell-eval2 pipeline, same reused bundle
(`gate-20260921-01/bundle`, anchor 477d72a6…, bundle 53931b96…), same real
subset (93,697 cells / 18,080 genes / 47 eval targets / 38,176 controls —
`real_eval2.h5ad` + `controls_eval2.h5ad` copied verbatim from
gate-local-20260929-01). Champion dual-moment config on every arm:
amplitude 1.0, bulk_amplitude 0.5, pool_k 4, space bulk_delta, seed 0.

## New variants (tools/build_consensus_deltas_v2.py, VPS repo, uncommitted)

Sources: panel-scale `extract-20260921-01` npzs staged at
`/opt/kytos/data/vol/k035-src/` (343 targets × 18,533 genes; pulled from the
Modal `kytos-vcc` volume — the genome-wide k034 npzs do **not** retain
`delta_batch`, and the panel npzs already carry the panel axis so no
`subset_deltas_npz.py` pass was needed).

- `consensus_w_ctr_vagr`: identical base to `consensus_w_ctr_agr` (weighted
  consensus, common-response centered — v2 reproduction verified against the
  v1 artifact at max_abs_diff 2.7e-20), gated by
  `clip((|fused|/sum|contrib| - 0.30)/0.70, 0, 1)` where each source's
  contribution is additionally weighted by per-target reliability
  `min(1, n_cells/100)` (the `*_ncell` convention; k562 has no `n_cells` →
  rel=1; uncovered targets → rel=0). `delta_batch` in these npzs is a pooled
  batch-paired delta, not a per-sample matrix, so no per-sample
  sign-consistency term was computed — n_cells reliability is the only
  within-source term (documented in `build_manifest_v2.json`).
- `consensus_w_ctr_agr_loose` / `consensus_w_ctr_agr_tight`: same base +
  standard agr gate with clip constants (0.20,0.60) / (0.40,0.80)
  bracketing the confirmed (0.30,0.70).

Gate mass: agr mean 0.704 (19.4% zeroed); vagr mean 0.714 (18.7% zeroed);
loose 0.755; tight 0.652. |agr−vagr| differs on 9.1% of (target,gene)
entries, mean |Δ| 0.024, concentrated in low-n_cells targets (largest
per-target mean shifts: IL10RB 0.213, UNK 0.212, SPATA20 0.202).

## Drift control: OK (float-epsilon)

dm_ref reproduces gate-local-20260929-01 / the Modal gate exactly:
pds_cosine mean 0.8538390379278445, expr_mse_unbiased_capped_norm
0.9560311144846585, scored avg 0.2303733902020999, de_proxy median 7954,
bulk_shift 0.50747 / 0.07409. dm_ctr_agr reproduces its round-01 value
(avg 0.240615 vs 0.240615) — anchor to round-01 holds.

## Per-arm scores

| arm | mse ratio | pds_cosine | nmae | fid | reach | jaccard | scored avg (from_repl) | mean(from_baseline) |
|---|---|---|---|---|---|---|---|---|
| dm_ref | 0.9560 | 0.8538 | 0.9800 | 0.5039 | 0.0182 | 0.2105 | 0.230373 | 0.1913 |
| dm_ctr_agr | 0.9587 | 0.8821 | 0.9813 | 0.5017 | 0.0305 | 0.2084 | 0.240615 | 0.2020 |
| dm_ctr_vagr | 0.9586 | 0.8834 | 0.9805 | 0.5018 | 0.0341 | 0.2086 | 0.2421 | 0.2033 |
| dm_ctr_agr_loose | 0.9578 | 0.8844 | 0.9803 | 0.5024 | 0.0248 | 0.2086 | 0.2409 | 0.2021 |
| dm_ctr_agr_tight | 0.9598 | 0.8862 | 0.9821 | 0.5019 | 0.0491 | 0.2093 | 0.2456 | 0.2068 |

(`mse ratio` = mean expr_mse_unbiased_capped_norm; raw metric columns are
`run_*_agg.csv` means; `mean(from_baseline)` = mean of the scored
`from_baseline` column over the six metrics.)

vs `dm_ctr_agr` (Δ scored avg / Δ pds): vagr +0.0015 / +0.0014;
agr_loose +0.0003 / +0.0023; agr_tight +0.0050 / +0.0042.
vs `dm_ref`: ctr_agr +0.0102, vagr +0.0117, loose +0.0105, tight +0.0152.

## Reading

- **All three new arms beat `dm_ctr_agr` on both raw pds_cosine and scored
  avg / mean(from_baseline).** Ordering by scored avg: tight > vagr > loose
  > ctr_agr > ref. By pds: tight > loose > vagr > ctr_agr > ref.
- `vagr` adds a small consistent gain over `agr` (+0.0015 avg, +0.0014 pds)
  — reliability-weighting the agreement denominator neither hurts nor
  dramatically helps; it is a surgical change (9% of gate entries move).
- The constants bracket is monotone locally: **tighter gating
  (0.40/0.80) is best on avg, pds and reach** (reach 0.0491 vs 0.0305),
  loose is ~flat on avg despite higher pds. This is the same direction as
  the agr gate itself (shrinking disagreeing genes helps) — the local gate
  keeps rewarding more aggressive suppression, at small cost to nmae
  (0.9821 vs 0.9800 ref) and mse ratio (0.9598 vs 0.9560 ref).
- Caveat per the revised submission protocol (AGENTS.md 2026-09-29): Gate B
  is hESC-only and has inverted orderings before — these are measurement
  values, not a veto/promotion verdict. Any submission would need a
  pre-declared component-level prediction.

Diagnostics (results.json): de_proxy medians 7950–7985 vs real 396 (all
arms ~same over-calling as ref); bulk_shift norms 0.450–0.507, cosine vs
real 0.063–0.074 — tight trades a little bulk-direction cosine for the
reach/pds gains. Harness elapsed 5,621 s (~94 min) for all 5 arms.

Artifacts: `variant_consensus_w_ctr_{vagr,agr_loose,agr_tight}.npz` +
`build_manifest_v2.json` at `/opt/kytos/data/vol/k035-machinery/`;
`tools/build_consensus_deltas_v2.py` (Mac + VPS repo, uncommitted); source
npzs `/opt/kytos/data/vol/k035-src/`.
