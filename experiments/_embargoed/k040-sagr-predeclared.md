# k040-sagr — pre-declared probe predictions (written 2026-10-12, BEFORE submit)

## Probe

Deltas = `variant_consensus_w_ctr_sagr.npz` (built 2026-10-12 by
`tools/build_consensus_deltas_v3.py` on Modal) through the **unchanged
champion generator** (dual_moment amp=1.0, bulk_amp=0.5, pool_k=4,
space=bulk_delta, seed 0, 400 cells/pert, contexts A,B,C) — the same
config as k027/k035/k038.

Single-variable change vs the k027 champion (`consensus_w_ctr`): the two
X-Atlas arms' source deltas are shrunk per-gene by per-sample sign
consistency from the k036 vote stores before consensus,

    cons[t,g] = (max(pos_count,neg_count) + 2) / (n_voting + 4)   (kappa=4)

then unit-normalized inside `consensus_delta` as usual — i.e. each deep
source's mass redistributes onto the genes its own 80-110 voting samples
sign consistently. k562/cd4 keep cons=1 (no per-sample store exists).
This is the first variant that *adds information* to the deltas rather
than re-weighting existing sources: every previous gate variant only
reshuffled the same pooled estimates.

Sagr cons distribution on the 343-target set (both X-Atlas arms): median
~0.55, p10 ~0.04, p90 ~0.84 — the low tail is genes with essentially zero
per-sample response (d≈0 votes neither sign), so the shrinkage is
meaningfully discriminating, not a uniform attenuation.

## Input parity (verified post-build, pre-submit)

| check | value |
|---|---|
| deltas sha256 | `c2c5d7f58a866e7c5c1451dcb765fb16170604d4c703e38f7786e2421651a7fd` |
| npz schema | genes (18533,) / targets (343,) / deltas (343,18533) float32 |
| volume path | `/kytos-vol/k035-machinery/variant_consensus_w_ctr_sagr.npz` |
| builder | `tools/run_k027_dual_moment_submit.py` inside Modal (champion path, memory 64 GB) |

Pre-submit gates: `n_targets 300`, `total_cells 360000`, contexts `[A,B,C]`,
`dispatch.real 900`, `uncovered []`, generator = champion config, deltas sha as
above. Any miss → do not submit.

## Declared predictions vs the champion reference (+0.1262 official;
component reads anchored on the k035 official table: pds 0.6113, mse
0.0118, nmae 0.0830, fid −0.0209, reach 0.0591, jac 0.0010)

| component | prediction | basis |
|---|---|---|
| score_pds | **UP — the headline channel**; +0.01 to +0.05 raw | sagr removes per-sample-inconsistent genes from the two deepest sources; pds measures per-target direction recovery, exactly what denoising should buy |
| score_jac | up modestly | our relative-strength channel; fewer spurious DE calls on noisy genes |
| score_reach | flat to slightly up | ambiguous: shrinkage removes some marginal genes (could cut reach) but concentrates mass on real ones |
| score_nmae | flat, ±0.004 | amplitude path untouched (K562-norm restore unchanged) |
| score_mse | flat to hair up | bulk-mean error improves only if direction improves; bound small |
| score_fid | flat | generation untouched, fid has never moved on delta-side changes |
| **score_avg** | **+0.122 to +0.135** | signature-side official attenuation is ~4x (k026/k027 analysis): even a real local gain lands small |

## Read (decided before submit)

1. **pds up AND avg up > +0.005** → per-sample agreement is real signal that
   transfers. Promote `consensus_w_ctr_sagr` to the reference delta set; the
   same machinery immediately extends to the Oct-22 ship build (stats stores
   are genome-wide already).
2. **pds up but avg flat/down** → direction improvement exists but is a
   small-weight channel; keep sagr for the ship build anyway (no cost), stop
   spending probe slots on delta-side polish.
3. **avg down > −0.005 or pds flat/down** → within-source replication adds
   nothing on this panel: signature content is saturated at the pooled-mean
   level. The entire delta side is then closed; all remaining effort goes to
   generation/distribution realism for Oct 22.
4. Falsifiable-by-construction: a flat result is itself informative (unlike
   the gate probes, sagr injects previously unused data), so this probe has
   value under every outcome.

## Cost

One submission slot + one Modal 64 GB build/prep run (~$0.5-1). The k036
scans and this build are already sunk (~$2).
