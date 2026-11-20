# gate-local-20260930-03 — Atlas sign-agreement oracle + Jurkat per-channel (jagr) gate

Two items in this round: (A) the Atlas per-batch sign-agreement oracle
that motivates the within-source gate hypothesis, and (B) the first
within-source gated variant — Jurkat stim channels as voters — scored
against the `dm_ctr_agr_tight_rmass` anchor. Run on snapflip-vultr with
`tools/run_k025_gate_local.py` (same pinned cell-eval2 pipeline, reused
bundle `gate-20260921-01/bundle`, real subset 93,697 cells / 47 eval
targets / 38,176 controls; champion dual-moment config).

## A. Atlas oracle (`/opt/kytos/runs/atlas-oracle-20260930-01/`)

Question: does per-batch sign-agreement predict replicable signal?
Method: per-(target, batch) pseudobulk log1p deltas vs batch-matched NTC
controls (all 48 batches have controls); per-gene `agree_frac` = fraction
of eligible batches (>=20 cells for that target in that batch) whose
delta sign matches the pooled delta sign; split-half = 48 batches split
into random halves (3 seeds), each half's pooled delta computed
independently.

- 50 eval targets, 48 batches; median 34.5 eligible batches/target;
  41/50 targets have >=3 eligible batches; 731,917 scored (target,gene)
  pairs.
- Spearman(agree_frac, |pooled delta|) = **0.6304** across all targets;
  **0.5991** restricted to the 4 panel-overlap targets (ACLY, HDAC8,
  NFE2L1, SLIRP).
- Split-half replication by agreement bin (mean over 3 splits):

| agree_frac bin | n pairs | mean\|pooled\| | split-half sign agree | split-half cosine |
|---|---|---|---|---|
| [0.00,0.55) | 339,232 | 0.0062 | 0.5009 | -0.0954 |
| [0.55,0.70) | 251,276 | 0.0188 | 0.7182 | 0.4885 |
| [0.70,0.85) | 90,989 | 0.0413 | 0.8337 | 0.8282 |
| [0.85,0.95) | 24,444 | 0.0613 | 0.8491 | 0.9389 |
| [0.95,1.00) | 25,976 | 0.1564 | 0.9333 | 0.9909 |

Verdict: **CONFIRMED.** High-agreement genes replicate across random
batch halves (cosine ~0.94-0.99); sub-0.55 agreement is statistically
coin-flip noise (cosine ~-0.10). The within-source sign-agreement gate
hypothesis is supported for a dense-batch source. Report:
`oracle_atlas_signagree_report.{md,json}` (this dir), arrays at
`/opt/kytos/runs/atlas-oracle-20260930-01/oracle_arrays.npz`.

## B. Jurkat per-channel gate (`jagr`)

Variant `consensus_w_ctr_jagr_tight_rmass`
(`tools/build_consensus_deltas_jagr.py`, VPS repo working tree,
uncommitted): identical to `consensus_w_ctr_agr_tight_rmass` except
Jurkat (stim condition, GSE249595, run `jurkat-20260924-02` — per-channel
partials pulled to `/opt/kytos/data/vol/k031-jurkat-parts/`) is added as
a 5th source (weight 1) whose contribution is scaled per-(target, gene)
by `j_agree[t,g]` = fraction of the 16 channels whose stim delta sign
matches the pooled stim delta sign. The scaled vector enters BOTH the
weighted unit-vector mean and the tight agreement gate's fused numerator
and |contrib| denominator; then ctr centering, clip(0.40,0.80), rmass —
same as v2. Full semantics in `build_manifest_jagr.json`.

**Spec adaptation (documented in manifest):** the specified >=20
cells/target/channel threshold is degenerate — per-channel coverage is
~4.3 cells/target/channel mean (23,472 stim cells over 16 channels x 343
targets; median pooled 60/target), so zero targets would have a voting
channel. Built at >=3 cells/channel instead (342/343 targets get >=1
voting channel, median 12; ZNF714 has none). Threshold sweep and
per-gene histogram in `jagr_report.json`; `j_agree` matrix in
`k035-machinery/jagr_stats.npz`.

j_agree quality: monotone with effect size — mean 0.396 for |pooled|<0.05
→ 0.807 for |pooled|>=0.5. But asymmetric: pooled-negative genes average
0.480 vs pooled-positive 0.199, because ~4-cell pseudobulks are mostly
all-zero -> channel delta sign is -1 from dropout. So the modifier
attenuates Jurkat's up-regulated signal more than its down-regulated
signal — a real caveat on shallow channels.

Unmodulated 5-source control `consensus_w_ctr_agr_tight_j5` (j_agree=1)
was also emitted for a later 3-arm isolation; **not gated in this
round**, so the jagr arm conflates "jurkat added" with "jurkat
modulated".

## Per-arm scores

| arm | mse ratio | pds_cosine | nmae | fid | reach | jaccard | scored avg (from_repl) | mean(from_baseline) |
|---|---|---|---|---|---|---|---|---|
| dm_ctr_agr_tight_rmass (anchor) | 0.9578 | 0.8858 | 0.9825 | 0.5016 | 0.0543 | 0.2108 | 0.246783 | 0.2077 |
| dm_ctr_jagr_tight_rmass | 0.9654 | 0.8918 | 0.9793 | 0.5007 | 0.0273 | 0.2071 | 0.243208 | 0.2047 |

Drift check: anchor reproduces gate-local-20260930-02 exactly
(0.2467828505371098 vs 0.24678285053710975).

Delta jagr − anchor (raw means / scored from_repl):
- pds_cosine +0.0060 / +0.0124 — Jurkat adds in-context discriminative
  signal even attenuated.
- nmae 0.9825→0.9793 raw; scored −0.0541→−0.0490 (improved).
- reach 0.0543→0.0273 raw; scored −0.0209→−0.0503 — the regression
  driver (halved DE direction reach).
- jaccard 0.2108→0.2071; fid ~flat; mse_norm 0.9578→0.9654.
- de_proxy medians 7950 vs 8018 (real 396); bulk_shift norm 0.497→0.421
  (j_agree mean ~0.24 shrinks the jurkat term), cos unchanged 0.063.

Net: **−0.0036 vs anchor** — mildly negative, not a promotion. The reach
loss is consistent with the dropout-asymmetric modifier down-weighting
Jurkat's positive-direction (typically DE-driving) genes.

## C. X-Atlas per-sample re-extract — recommendation: GO

The Atlas oracle confirms within-source sign agreement predicts
replication where per-sample coverage is dense. Jurkat's shallow channels
(~4 cells/target/channel) cannot support a clean per-channel gate —
that is a data limitation, not a falsification of the gate family.
X-Atlas per-sample is the decisive test of whether the modifier helps a
well-powered source. If it is re-run, also gate `dm_ctr_agr_tight_j5`
(unmodulated 5-source) alongside so the modifier effect is isolated from
the added-source effect.
