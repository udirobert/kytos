# gate-local-20260930-04 — unmodulated 5-source control (j5) vs rmass anchor

Leftover arm from gate-local-20260930-03: score `dm_ctr_agr_tight_j5`
(`variant_consensus_w_ctr_agr_tight_j5.npz` — Jurkat stim added as a plain
5th source at weight 1, `j_agree=1`, otherwise identical to the tight+rmass
build) to isolate the "added-source" effect from the j_agree modifier
measured in round -03. `dm_ctr_agr_tight_rmass` re-run as the drift-control
anchor. Same pinned cell-eval2 pipeline, reused bundle
`gate-20260921-01/bundle`, 47 eval targets, champion dual-moment config
(amp 1.0, bulk_amp 0.5, pool_k 4, bulk_delta space, seed 0).

## Per-arm scores

| arm | mse_norm | pds_cosine | nmae | fid | reach | jaccard | scored avg (from_repl) |
|---|---|---|---|---|---|---|---|
| dm_ctr_agr_tight_rmass (anchor) | 0.9578 | 0.8858 | 0.9825 | 0.5016 | 0.0543 | 0.2108 | **0.246783** |
| dm_ctr_agr_tight_j5 | 0.9657 | 0.8885 | 0.9817 | 0.5030 | 0.0433 | 0.2087 | **0.245500** |

Drift check: anchor reproduces rounds -02/-03 exactly
(0.2467828505371098). Elapsed 2372s on snapflip-vultr.

## Delta j5 − anchor

- **avg −0.00128** (raw scored from_replicate 0.245500 vs 0.246783).
- pds_cosine +0.0028 raw / +0.0057 scored — Jurkat adds a little
  discriminative signal even unmodulated.
- fidelity yield +0.0014 raw / +0.0021 scored; nmae scored −0.0541→−0.0529
  (slightly better).
- **reach is the cost:** raw 0.0543→0.0433 (−20%), scored
  −0.0209→−0.0329 — same direction as the jagr arm (0.0273), i.e. most of
  jagr's reach loss comes from simply adding Jurkat, not from the
  j_agree attenuation.
- jaccard −0.0021 raw; fid +0.0014; mse_norm +0.0079.
- de_proxy 8005 vs 7950 (real 396); bulk_shift norm 0.440 vs 0.497 —
  the 5th source dilutes bulk amplitude toward Jurkat's weaker mean.

## Read

Adding Jurkat as a plain 5th source is a small net negative
(−0.0013 avg), driven by reach. Three-way isolation now reads:

| build | scored avg | delta vs rmass |
|---|---|---|
| 4-source rmass (anchor) | 0.246783 | — |
| 5-source j5 (unmodulated) | 0.245500 | −0.0013 |
| 5-source jagr (modulated) | 0.243208 | −0.0036 |

So the j_agree modifier cost a further −0.0023 on top of the added-source
effect — the dropout-asymmetric attenuation noted in round -03 hurt more
than it helped on Jurkat's shallow (~4 cells/channel) coverage. Neither
Jurkat variant promotes. The within-source sign-agreement hypothesis
itself remains untested at the family level — that is what the k036
X-Atlas per-sample extraction (78–116 voters/target) is for.
