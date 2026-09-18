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
- **Done (negative)**: Track 1 item 3(b) — the RPE1 GWPS panel-coverage check
  is answered by `experiments/k013-lineage-ratios/report.json`: **no RPE1 GWPS
  arm exists** (only K562 has a genome-wide arm; rpe1/jurkat/hepg2 public files
  are the 2,393-target essential screen, overlapping **0/300** panel targets).
  The context-B lineage-swap variant is dead; do not re-check.
- **Done (negative)**: k014 conditional MLP baseline (2026-09-18). Model cosine
  0.0425 vs identity 0.1406 — worse than raw transplant. Root cause: only 47
  paired examples; no cross-context signal to learn. See
  `docs/track2-nebius-setup.md` §8 for full details.
- **Now**: 4-lineage essential-screen transfer learning (item 3a) —
  richer paired data (2,393 targets × 4 contexts) than the 47-pair
  K562/hESC set that failed LOO. Run ID: k015 (k014 is reserved for
  Track-2 trained-model submissions).
- **Next (Track 2)**: GEARS-style GNN on Nebius. The conditional MLP failure
  confirms we need graph structure (gene-gene interactions) to generalize to
  unseen targets, not just context conditioning. See §9 below.
- Track 1 keeps spending daily slots on its best variant; Track 2 submits
  only when in-corpus eval clearly beats the running champion.

## 9. Track 2 revised plan (post-k014)

The conditional MLP baseline (k014-run-1) failed because it tried to learn
a context-transfer function from only 47 paired examples. The model needs
structural priors about gene-gene relationships to generalize.

### Priority order for Track 2 experiments:

1. **GEARS-style GNN** (highest expected value)
   - Architecture: gene-node embeddings + GNN message passing on STRING
     interaction graph → predict delta vector for target gene.
   - Training data: 9,869 Replogle K562 targets (pseudobulk deltas) as
     supervised signal. The graph structure enables generalization to the
     28 uncovered panel targets.
   - Context conditioning: concatenate context basal vector (or learned
     context embedding) as a global conditioning signal.
   - Why this should work: GEARS (Roohani et al. 2022) showed that GNNs
     trained on perturbation data + gene interaction graphs can predict
     effects of unseen gene knockouts. Our setting is analogous.
   - Key difference from k014: the graph provides inductive bias for
     unseen targets; k014 had no mechanism to generalize beyond memorization.

2. **scGPT / scFoundation fine-tune** (if GEARS plateaus)
   - Pretrained on millions of single-cell transcriptomes; already encodes
     gene-gene relationships.
   - Fine-tune on Atlas perturbation data (per-cell, not pseudobulk).
   - Heavier setup (model download, GPU memory), but potentially much
     stronger representations.

3. **Ensemble / stacking** (combine best Track 1 + Track 2)
   - Use k011 priors as base, add model-predicted deltas as correction.
   - Learn per-target or per-gene weights on held-out data.
   - Can be done on Modal (no GPU needed).

### VM provisioning quick-reference

```bash
# Re-create instance (after deletion to save cost)
nebius compute instance create \
  --parent-id project-e00sz92bpr005x5c3r80zr \
  --name kytos-track2-gpu \
  --resources-platform gpu-l40s-a \
  --resources-preset 1gpu-16vcpu-64gb \
  --boot-disk-attach-mode read_write \
  --boot-disk-managed-disk-name kytos-track2-disk \
  --boot-disk-managed-disk-source-image-id computeimage-e00q003g5k851wjgpn \
  --boot-disk-managed-disk-size-gibibytes 500 \
  --boot-disk-managed-disk-type network_ssd \
  --network-interfaces '[{"name":"eth0","subnet_id":"vpcsubnet-e00pbj53wtjbf7c6e9","ip_address":{},"public_ip_address":{},"security_groups":[{"id":"vpcsecuritygroup-e00jth18f0j9zbct6g"},{"id":"vpcsecuritygroup-e00ac0vv3g60xcp6h7"}]}]' \
  --cloud-init-user-data "$(cat <<'EOF'
#cloud-config
users:
  - name: ubuntu
    ssh_authorized_keys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEsq2UpnLyOLm2rr0gf1pH2Qf8ykKZTK7Vq9bnZSLz2q
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
EOF
)" \
  --async

# SSH (use ubuntu user, not root)
ssh -i ~/.ssh/id_ed25519 ubuntu@<IP>

# Data staging (from local, after modal volume get)
modal volume get kytos-vcc /paired-transfer/paired_transfer_train.npz /tmp/modal_transfer/
modal volume get kytos-vcc /paired-transfer/delta_matrix_src.npz /tmp/modal_transfer/
scp /tmp/modal_transfer/*.npz ubuntu@<IP>:/data/derived/

# Delete when done (saves ~$1/hr)
nebius compute instance delete --id <instance-id> --async
```

### Cost tracking

| Session | Duration | Approx cost |
|---------|----------|-------------|
| 2026-09-18 (k014-run-1) | ~15 min | ~$0.25 |

**Total Nebius spend so far: ~$0.25**
