# VCC two-track strategy — top 200 on Modal, top 100 on rented GPU

Status: **active plan** (agreed 2026-09-17 after k011 x1.3/x1.7 set new
best scores of +0.0559 / +0.0596, rank ~486).

## Scoreboard reality (live leaderboard, 984+ entries)

| | us (best) | top 200 | top 100 | #1 |
|---|---:|---:|---:|---:|
| overall | +0.060 | +0.134 | +0.158 | +0.292 |
| pds | 0.339 | ~0.52 | 0.699 | 0.830 |
| nmae | -0.076 | ~+0.13 | +0.145 | +0.220 |
| fid | -0.006 | ~-0.003 | -0.019 | +0.085 |

`pds` (perturbation discrimination) and `nmae` (DE log-FC accuracy) are the
gating metrics for both tiers. `fid` is effectively solved on our current
config. The remaining gap is **signature quality**, not sampling shape.

## Track 1 — top 200 on Modal (current infra)

Goal: ~+0.13 overall. Stays on the existing Modal pipeline (64 GiB CPU
Functions, `kytos-vcc` Volume, `submit_from_volume` flow). Ordered by
expected value per engineering hour:

1. **Bracket delta_scale** — x2.0 staged on the volume
   (`/kytos-vol/k011-delta-scale-x2p0/`); x1.3→x1.7 gained +0.004, so the
   optimum is near. Also consider **per-source scaling** (Replogle bulk
   vs Atlas sc signatures may need different scales) and **per-target
   scaling** conditioned on |delta| — same code path, one more param.
2. **Learned Layer A — paired-signature transfer** (spec:
   `docs/k012-learned-layer-a.md`, implementation spec below). Train on
   the ~50 targets screened in both K562 GWPS and Atlas H1 hESC; LOO
   validation in-corpus; submit only if it beats the global scalar.
3. **Lineage-matched corpora** — marker analysis suggests context B is
   RPE1-like; the Replogle RPE1 GWPS arm is a cheap swap-in for those
   targets. Context A looks Jurkat-like (Schmidt et al. 2022 primary
   T-cell Perturb-seq is the candidate source).
4. **Residual covariance (Layer B)** — pooled/target residual covariance
   from Atlas perturbed cells. Stacks with any of the above.

Compute: all of 1–4 run on Modal CPU (paired-transfer fitting is a small
matrix problem; corpus swaps reuse the existing builder). Estimated
ceiling for this track: plausibly +0.10–0.14 — i.e., top 200 is
reachable, top 100 probably is not.

## Track 2 — top 100 on rented GPU (parallel)

Goal: ~+0.16 overall. Requires a genuinely **trained perturbation model** —
the pds=0.70 tier is almost certainly occupied by GEARS-class or
foundation-model fine-tunes, not lookup+transfer.

Candidate approaches (evaluate before committing):

- **GEARS-class GNN** trained on Replogle K562 + RPE1 GWPS (~9.8k targets)
  + 2025 Atlas; predict held-out-target deltas conditioned on context
  basal expression.
- **scFoundation/scGPT/scBERT fine-tune** on the same corpora — heavier,
  needs the pretrained weights and careful eval hygiene.
- **Conditional VAE / MLP residual model** — simplest trained baseline:
  predict delta from (target embedding, context basal profile); less
  glamorous but honest and fast to iterate.

Platform: **Nebius cloud** (user-confirmed access, 2026-09-17) — single
GPU VM is plenty: L40S 48 GB or A100 80 GB covers GEARS-class training;
H100 if we go the scGPT fine-tune route. Persistent disk for checkpoints
+ SSH for interactive iteration across hours-days — the two things Modal
Functions don't give us (and preemption risk we just hit on builds).
Modal remains the build/submit path regardless of where the model trains.

Guardrails (same as always): tune on held-out targets/contexts in-corpus,
never on leaderboard feedback; ≤2 submissions/day; record negative
results.

## Sequencing

- **Now**: x2.0 build staged for tomorrow's slot.
- **This week**: Track 1 item 2 (paired-transfer Layer A) — design doc +
  training data extraction on Modal.
- **Parallel**: provision the GPU box; port the paired-transfer dataset
  builder to produce training tensors for whichever model class is chosen.
- Track 1 keeps spending daily slots on its best variant; Track 2 submits
  only when in-corpus eval clearly beats the running champion.
