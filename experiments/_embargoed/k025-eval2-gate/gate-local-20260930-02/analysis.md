# gate-local-20260930-02 — k035 machinery v2 follow-up (rmass row-norm restoration)

Run on snapflip-vultr (4 vCPU / 31 GB + 32 GB swap) with
`tools/run_k025_gate_local.py` (VPS-only, uncommitted). Same pinned
cell-eval2 pipeline, same reused bundle
(`gate-20260921-01/bundle`, anchor 477d72a6…, bundle 53931b96…), real
subset rebuilt deterministically (93,697 cells / 18,080 genes / 47 eval
targets / 38,176 controls — identical dims to round-13/14/15). Champion
dual-moment config on every arm: amplitude 1.0, bulk_amplitude 0.5,
pool_k 4, space bulk_delta, seed 0.

## New variant (tools/build_consensus_deltas_v2.py, VPS repo, uncommitted;
## identical edit mirrored to the Mac repo working tree)

- `consensus_w_ctr_agr_tight_rmass` ("restore mass"): the tight
  agreement gate `agr_tight` (clip 0.40/0.80) decides WHICH genes carry
  effect (a 0..1 keep-mask); each target row is then rescaled so the
  gated row recovers the full ungated `ctr` row L2 norm:

      gated[t]  = ctr[t] * agr_tight[t]
      rmass[t]  = gated[t] * (||ctr[t]|| / ||gated[t]||)   (0 if gated==0)

  Rationale: the known gate cost is mass loss (gating shrinks true
  delta mass → slight nmae/mse erosion). rmass treats the gate as
  feature selection rather than amplitude attenuation, concentrating
  each target's total delta mass on the agreed genes.

Artifact self-checks: all 343 rows restored to ||ctr[t]|| within 4e-8;
per-row direction bit-identical to the gated variant (min cosine
0.9999999999999987 vs `variant_consensus_w_ctr_agr_tight`); rescale
factors min/median/max 1.005 / 1.122 / 1.734 (the tight gate had removed
~11% of median row mass, up to ~42% on the most-gated targets). v2 base
reproduction re-verified (max_abs_diff 2.7e-20 vs v1 ctr_agr). Manifest
updated at `k035-machinery/build_manifest_v2.json`.

## Drift control: OK (float-epsilon)

`dm_ctr_agr_tight` re-scored as the anchor and reproduces its
gate-local-20260929-02/0930-01 value exactly: scored avg
0.24562108728979473 vs 0.24562108728979462/…947, per-metric rows
identical, de_proxy median 7985, bulk_shift 0.45012 / 0.06288 — all
matching. No pipeline or data drift.

## Per-arm scores

| arm | mse ratio | pds_cosine | nmae | fid | reach | jaccard | scored avg (from_repl) | mean(from_baseline) |
|---|---|---|---|---|---|---|---|---|
| dm_ctr_agr_tight (anchor) | 0.9598 | 0.8862 | 0.9821 | 0.5019 | 0.0491 | 0.2093 | 0.245621 | 0.2068 |
| dm_ctr_agr_tight_rmass | 0.9578 | 0.8858 | 0.9825 | 0.5016 | 0.0543 | 0.2108 | 0.246783 | 0.2078 |

(`mse ratio` = mean expr_mse_unbiased_capped_norm; raw metric columns are
`run_*_agg.csv` means; `mean(from_baseline)` = mean of the scored
`from_baseline` column over the six metrics. Round-15 reference values:
dm_ctr_agr_tight 0.245621, dm_ctr_agr_xtight 0.244205,
dm_ctr_vagr_tight 0.242905; round-14: dm_ref 0.230373 / pds 0.8538,
dm_ctr_agr 0.240615 / 0.8821.)

Δ rmass − tight (raw means / scored from_repl):
reach +0.0053 / +0.0057 (0.0491→0.0543; −0.0266→−0.0209),
jaccard +0.0014 / +0.0032 (0.2093→0.2108; 0.1711→0.1726),
nmae +0.0004 worse (0.98211→0.98248; from_repl −0.0535→−0.0541),
mse ratio −0.0020 (0.9598→0.9578; scored 0.0 both),
pds −0.0005 (0.88622→0.88575; from_repl 0.77729→0.77634),
fid −0.0003 (0.5019→0.5016).
Net: scored avg +0.00116 — **new local best** (0.246783 > tight's
0.245621).

## Reading

- **rmass wins on avg but NOT via the hypothesized mechanism.** The
  pre-registered motivation was nmae/mse recovery: gating was supposed
  to shrink true mass, so restoring row norm should recover DE-error.
  Instead nmae moved marginally the wrong way (0.98211→0.98248) and
  mse_ratio eroded slightly (0.9598→0.9578). Mass loss was not the
  nmae driver — the gate's keep-mask, not its shrinkage, carries the
  value.
- **Where the gain actually comes from is reach** (+0.0053 raw, +0.0057
  scored — by far the largest single-metric move this round). Restored
  amplitude pushes more kept genes past the scorer's DE-direction count
  threshold per target. jaccard follows it (+0.0014) and pds/fid are
  flat — direction content is unchanged (rmass is a pure per-row rescale
  of the tight-gated delta; bulk_shift cosine vs real identical at
  0.063) while bulk norm rises 0.450→0.497 toward the ungated amplitude.
- **de_proxy actually fell** (7950 vs 7985 vs real 396): concentrating
  mass on agreed genes slightly shrinks the DE-call set rather than
  inflating it — consistent with "same total mass, fewer genes" rather
  than "more amplitude everywhere".
- **Net effect +0.0012 avg over the best variant — real but small.**
  rmass is the only round-16 arm and it strictly improves on tight on
  avg; whether a submission slot is warranted needs a pre-declared
  component-level prediction per the 2026-09-29 protocol (Gate B is
  hESC-only; ordering has inverted before). The reach-pds trade here is
  nearly neutral (reach up, pds flat-to-down) — a cleaner profile than
  most "free mass" probes.
- What this rules out: per-gene full-mass restoration is NOT where the
  remaining nmae/mse gap lives; the residual deficit vs `dm_ref` is
  direction content (per-sample within-source agreement is the untested
  lever — see feasibility note).

Diagnostics (results.json): de_proxy medians 7950 (rmass) / 7985
(tight) vs real 396; bulk_shift norms 0.497 / 0.450, cosine vs real
0.063 both. Harness elapsed 2,373 s (~40 min) for 2 arms + real-subset
rebuild.

Artifacts: `variant_consensus_w_ctr_agr_tight_rmass.npz` +
`build_manifest_v2.json` (updated) at `/opt/kytos/data/vol/k035-machinery/`;
`tools/build_consensus_deltas_v2.py` and `tools/run_k025_gate_local.py`
(VPS repo, uncommitted; builder edit mirrored in the Mac working tree);
gate tmux session `k035-gate`, log `/opt/kytos/logs/gate-local-20260930-02.log`.
