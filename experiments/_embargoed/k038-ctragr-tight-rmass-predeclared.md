# k038-ctragr-tight-rmass — pre-declared probe predictions (written 2026-10-03, BEFORE build/submit)

## Probe

Round 16's local best, never probed officially: deltas =
`variant_consensus_w_ctr_agr_tight_rmass.npz` (gate picks genes, row-norm
restores per-target mass; tight clip constants 0.40/0.80) through the **unchanged
champion generator** (dual_moment amp=1.0, bulk_amp=0.5, pool_k=4,
space=bulk_delta, seed 0, 400 cells/pert, contexts A,B,C).

Two variables move vs k035 (`ctr_agr`, std constants 0.30/0.70): the clip
constants and rmass. This is therefore a *recipe* probe, not a single-variable
ablation — declared explicitly so a win cannot be attributed to either term
alone.

## Input parity (verified pre-build)

| check | value |
|---|---|
| deltas sha256 | `989d1415b2477d107d8e369df69cf48662115e3ff1c94a2ca227122dd21ae252` |
| sha verified across | VPS → Mac → Modal volume (all three identical) |
| npz schema | genes (18533,) / targets (343,) / deltas (343,18533) float32 — matches builder expectations |
| volume path | `/kytos-vol/k035-machinery/variant_consensus_w_ctr_agr_tight_rmass.npz` |
| builder | `tools/run_k027_dual_moment_submit.py` inside Modal (champion path, memory 64 GB) |

Pre-submit gates: `n_targets 300`, `total_cells 360000`, contexts `[A,B,C]`,
`dispatch.real 900`, `uncovered []`, generator = champion config, deltas sha as
above. Any miss → do not submit.

## Declared predictions vs k035 official (+0.1242; pds 0.6113, mse 0.0118, nmae
0.0830, fid −0.0209, reach 0.0591, jac 0.0010)

| component | prediction | basis |
|---|---|---|
| score_reach | **UP — the biggest move**; 0.060 → 0.062–0.072 | round 16 attributes the entire local gain to reach/jac; restoring per-target mass should push more genes past DE thresholds |
| score_jac | up modestly; 0.0010 → 0.0012–0.0022 | same channel |
| score_nmae | **flat, ±0.004 — explicitly NOT up** | the rmass hypothesis that mass loss drives nmae was **falsified locally**; predicting no nmae recovery is the falsifiable part of this probe |
| score_pds | ~flat, possibly a hair down; 0.600–0.618 | tight constants shrink low-agreement genes harder; direction content is unchanged |
| score_mse | flat; 0.008–0.015 | mse tracks `bulk_amplitude`, which this probe does not touch |
| score_fid | flat; −0.018 to −0.025 | never moved across recent recipes |
| **score_avg** | **+0.119 to +0.132** (within ±0.01 of k035) | reach/jac are small-weight channels; a real gain there cannot move avg much |

## Read (decided before submit)

1. **reach + jac up, avg up > +0.005** → the rmass mechanism has official weight
   despite the small channel weights. Promote `ctr_agr_tight_rmass` to the
   reference delta set and stack the next mechanism on it.
2. **nmae up materially (> +0.008)** → the local falsification of the mass→nmae
   hypothesis was wrong, i.e. the Gate B harness misranks mass effects. That
   would undermine confidence in *local* gate readouts generally, not just this
   variant — the more valuable result.
3. **reach flat and avg within noise or down** → the local gain was
   harness-specific. Treat the agreement-gate/constants axis as closed and stop
   spending slots on it.
4. Cross-check vs k037 (champion re-score, same day): both probes land the same
   day, so a shared drift in the panel/scorer would show up as *both* moving
   against their own declared bands. Two independent measurements of drift for
   the price of the same day.

## Cost

2nd of 2 daily slots on Oct 3 (k037 used the first). Modal CPU build+prep at
64 GB — `vcc prep` is not viable on the 31 GB VPS (aborted at 29 GB today).

---

## RESULT (2026-10-03T22:10:54Z published — entry `b8ellZcFjWy58mJkVl31`, rank 489/1299)

`score_avg` **+0.12543882** — **−0.000735 vs k037 (the champion, same day),
+0.001224 vs k035.** A statistical tie with the champion, and the second
consecutive tie on this delta axis.

| component | k037 champion | k035 std gate | **k038 tight+rmass** | declared band | verdict |
|---|---|---|---|---|---|
| score_pds | 0.60321 | 0.61126 | **0.61363** | 0.600–0.618 | CONFIRMED (best pds recorded) |
| score_mse | 0.01483 | 0.01177 | **0.01494** | 0.008–0.015 | CONFIRMED (top of band) |
| score_nmae | 0.08817 | 0.08301 | **0.09033** | flat ±0.004, **explicitly not up** | **FALSIFIED** (+0.0073 vs k035, +0.0022 vs champion) |
| score_fid | −0.01882 | −0.02090 | **−0.02156** | −0.018…−0.025 | CONFIRMED |
| score_reach | 0.06858 | 0.05912 | **0.05408** | **UP** to 0.062–0.072 | **FALSIFIED — wrong direction** (−0.0050 vs k035, −0.0145 vs champion) |
| score_jac | 0.0010618 | 0.0010367 | **0.0012065** | 0.0012–0.0022 | CONFIRMED (bottom of band) |

Raw channels: pds_cosine 0.77699 · expr_mse 0.97367 · lfc_nmae 0.94670 ·
fid_yield 0.50625 · reach_raw 0.12710 · jaccard 0.03074.
Component deltas vs k037 sum to −0.004409 / 6 = **−0.000735**, i.e. exactly the
observed overall movement — no hidden channel effects.

### Which reads fired

**Read 1 did NOT fire.** reach fell instead of rising; avg moved +0.0012 vs
k035, far short of the +0.005 promotion bar. `ctr_agr_tight_rmass` is **not**
promoted; it does not replace `consensus_w_ctr` as the ship recipe.

**Read 2 missed by a hair and is recorded as unproven, not confirmed.** The
declared bar was nmae > +0.008 vs k035; actual **+0.00732**. So the letter of
read 2 is not satisfied. But its *substance* is: round 16 measured rmass as
nmae-flat locally and used that to falsify the mass→nmae hypothesis, and
officially nmae rose to **above the champion's**. A single near-threshold probe
does not overturn a local measurement — it does mean the local
"mass-loss-isn't-the-nmae-driver" falsification should no longer be treated as
settled, and that Gate B's nmae channel is not trustworthy at the ±0.007 scale.

**Read 3 FIRED — this is the operative verdict.** reach did not merely stay
flat, it went the *opposite* way to the local prediction, and avg is inside
noise. The round-16 local gain (attributed entirely to reach/jac) was
harness-specific. **The agreement-gate / gate-constants axis is closed; stop
spending slots on it.**

**Read 4 delivered the cleanest possible version of this result.** k037
rescored the champion's own bytes the same day at +0.126173 (Δ3e-5 from the
September record), so scorer/panel/anchor drift is excluded and k038's
movement is entirely machinery. Two probes, one day, one of them a null: the
drift question is settled rather than assumed.

### The mechanism this day bought: the pds↔reach trade is real and monotone

Three points on one axis (no gate → std gate → tight+rmass):

| | pds | reach | overall |
|---|---|---|---|
| k037 `consensus_w_ctr` | 0.60321 | 0.06858 | +0.12617 |
| k035 `…_agr` (0.30/0.70) | 0.61126 | 0.05912 | +0.12421 |
| k038 `…_agr_tight_rmass` (0.40/0.80) | **0.61363** | **0.05408** | +0.12544 |

Sharpening the cross-source agreement gate raises pds (+0.0041 at this last
step) while cutting reach_raw from 0.1396 to 0.1271 —
the gate suppresses low-agreement genes, and those suppressed genes are exactly
the ones that would have registered as reached DE genes. Because `score_avg`
weights the two channels equally and reach moves harder than pds, every step
along this axis is net-negative or a tie. That is the mechanical explanation
for the whole k028→k038 plateau: we have been re-shuffling between two
anti-correlated channels instead of adding signal.

### Consequences for the remaining days (Oct 4 → Oct 22)

1. **Ship-recipe unchanged:** blind final submission stays the champion
   `consensus_w_ctr` + dual-moment a1.0/b0.5/pk4. Nothing since k027 has beaten
   it, and the gate machinery is now understood as a trade rather than a gain.
2. **Only mechanisms that can raise pds *without* shrinking reach are worth a
   slot.** That means *adding* confidently-signed genes rather than *shrinking*
   the gene set: more independent samples per source (k036's per-sample
   extraction, still the best untested lever), or a second lineage-matched
   source. Reject any further gate-constant, gate-shape, or centering variant.
3. **A gate *loosening* probe is the one cheap falsification left on this axis**
   — if the trade is real, looser constants (0.20/0.60 or no clip) should score
   *at or above* the champion by recovering reach while giving back pds. If a
   loose setting instead beats the champion outright, the trade framing is wrong.
4. **Gate B's authority is now scoped:** its ordering transferred once (k026,
   k027) and has failed to transfer on the last four promotions (k030 inversion,
   k034, rounds 11–12 non-composition, rounds 14–16 → k038). Treat it as a
   leakage/regression screen and drift check only — exactly as the 2026-09-29
   protocol revision said, and now with a measured sign failure to cite.

### Cost

2 of 2 daily slots on Oct 3, both spent; k037 (the null) is what made k038
interpretable. Upload 3.7 GiB in 5m01s; scoring latency ~20 min; k038 had to
queue behind k037 (one in-flight submission per team).
