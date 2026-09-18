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

1. ~~Bracket delta_scale~~ — **done 2026-09-18**: x1.3 +0.0559 →
   x1.7 **+0.0596** (champion) → x2.0 +0.0566. Optimum ~1.7; `pds`/`fid`
   keep improving with scale but `nmae` cost now dominates
   (+0.004 → -0.023 → -0.076 → -0.125). The scalar magnitude axis is
   exhausted — remaining levers are signature content, not amplitude.
2. ~~Learned Layer A — paired-signature transfer~~ — **LOO done
   2026-09-17** (`experiments/k012-transfer-loo/`): raw K562→hESC
   transfer cosine ~0.13; no transfer class cleared the +0.05 acceptance
   bar (fitted scalar s≈0.44; low-rank map sign acc 0.60 vs 0.32 raw —
   coarse pathway structure transfers, fine detail doesn't). Naive
   paired transfer does not ship.
3. **Lineage-matched corpora** — lineage score done 2026-09-18
   (`experiments/k012-lineage-score/`): on discriminative genes, **A is
   Jurkat-like (0.649)**, B weakly RPE1-leaning (0.369), C unresolved.
   **But** the Nadig Jurkat essential screen covers **0/300 panel
   targets** — essential screens can't supply panel deltas directly.
   Two live options: (a) the 4-lineage × 2,393-target essential set
   (K562/RPE1/Jurkat/HepG2) as a *transfer-learning training set* — learn
   inter-lineage delta maps, apply to K562 GWPS panel deltas;
   (b) non-essential corpora with panel overlap (check GWPS RPE1 arm's
   panel coverage — it shares K562's 9.8k-target design, so likely
   covers ~270 targets for context B).
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
Provisioning + data-layout spec: `docs/track2-nebius-setup.md`.

Guardrails (same as always): tune on held-out targets/contexts in-corpus,
never on leaderboard feedback; ≤2 submissions/day; record negative
results.

## Sequencing

- **Done**: x2.0 submitted + scored (2026-09-18); scale bracketed at ~1.7.
- **Now**: Track 1 item 3(b) — check the RPE1 GWPS arm's panel coverage;
  if ~270/300 as expected, build a context-B-dispatched variant
  (RPE1 deltas for B, K562 elsewhere) — the first testable lineage swap.
- **Next**: 4-lineage essential-screen transfer learning (item 3a) —
  richer paired data (2,393 targets × 4 contexts) than the 47-pair
  K562/hESC set that failed LOO.
- **Parallel**: provision the Nebius box; port the paired-transfer
  dataset builder to produce training tensors for whichever model class
  is chosen.
- Track 1 keeps spending daily slots on its best variant; Track 2 submits
  only when in-corpus eval clearly beats the running champion.
