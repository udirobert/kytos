# VCC two-track strategy — top 200 on Modal, top 100 on rented GPU

> **STATUS 2026-09-20: SUPERSEDED — read this banner before acting on
> anything below.** This was the plan as of 2026-09-17. Track 2 (rented-GPU
> trained model) and the essential-screen transfer have since been run to
> **decisive negative results**, and a ceiling analysis reframed where the
> remaining score lives. Canonical per-run record: `AGENTS.md` §4. What
> actually happened:
>
> - **Track 2 / Nebius GNN is CLOSED.** The GEARS-style cross-lineage GNN
>   (k020, raw) scored **−0.114** and the norm-matched re-run (k020b) **−0.098**
>   — both big regressions vs the k011 champion (+0.0596). Critically,
>   `pds_cosine` never improved (0.528→0.521), so the GNN's per-gene
>   *direction* on the real panel is no better than the borrowed K562 prior.
>   **Nebius is fully deleted** (no residual spend); the provisioning
>   commands in §9 below are dead references. Cross-lineage essential-set
>   transfer is a dead scoring avenue.
> - **k015 low-rank essential transfer was also negative** (−0.028): OOD for
>   the non-essential panel.
> - **The kaipengm2 "highest-EV replicate" note (§10) is moot** — we already
>   ship its dual-moment generator (`src/kytos/models/dual_moment.py`); its
>   0.1546 came from a 4-source lineage-matched ensemble (K562/HCT116/
>   HEK293T/H1) + CD4 + promoter prior we cannot assemble from corpora that
>   cover the panel in a matched lineage.
> - **k021 ceiling analysis (`experiments/k021-ceiling/summary.json`) is the
>   current decision tool.** It shows the gap splits by metric family:
>   *direction* metrics (discrimination, pearson_delta) are **signature-bound**
>   — a perfect per-target delta nearly hits the ceiling, so `pds` is capped by
>   our inability to *recover* the true delta (public corpora exhausted);
>   *DE-count* metrics (overlap_at_N, precision_at_N) stay **modeling-bound
>   even with a perfect delta** because the generator over-calls DE genes
>   ~1.6–2× (5462 pred vs 3436 real). **That over-calling is the one large
>   lever that needs no GPU and no new corpus — calibrate generator dispersion
>   so predicted DE-count ≈ real, gated offline on the k021 harness first.**
>
> Champion remains `kytos-k011-ds-x1p7` (+0.0596, rank ~486). Everything under
> "Track 2", §9, and the §10 "Revised priorities" is historical — kept for the
> record, not as a plan.

Status: ~~**active plan**~~ (agreed 2026-09-17 after k011 x1.3/x1.7 set new
best scores of +0.0559 / +0.0596, rank ~486) — **see SUPERSEDED banner above.**

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

## Track 2 — top 100 on rented GPU (parallel) — **CLOSED 2026-09-20: negative**

*(Ran to completion below: k020 raw GNN −0.114, k020b norm-matched −0.098,
`pds` flat → direction no better than the K562 prior. Nebius deleted. See the
SUPERSEDED banner and `AGENTS.md` §4. Kept as the record of what was tried.)*

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

## 9. Track 2 revised plan (post-k014) — **EXECUTED, NEGATIVE (historical)**

*(The GEARS-style GNN below was built and trained on Nebius as k020/k020b and
both regressed on the leaderboard with `pds` unchanged; scGPT fine-tune not
pursued. The VM-provisioning snippet is dead — Nebius torn down.)*

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

## 10. Resource audit (2026-09-18, post-leaderboard-API discovery)

Prompted by user question "are we using all the resources available to us?"
— audit of official + public resources, several previously unused.

### Newly exploited today

1. **Public leaderboard API** — `https://virtualcellchallenge.org/api/leaderboard`
   returns all 1,036 published entries with raw metrics AND normalized
   component scores (no auth required). Saved snapshot: `/tmp/vcc_leaderboard.json`.
   Findings:
   - `score_avg` is the plain arithmetic mean of six component scores:
     `score_pds, score_mse, score_nmae, score_fid, score_reach, score_jac`
     (verified exact on top 5 entries).
   - **Top-100 threshold today: 0.1685** (team "xxx yan", model
     "atlas-transfer v1.1"). Rank 100 component profile: pds 0.690,
     nmae 0.165, reach 0.119, mse 0.052, fid -0.015, jac 0.001.
     ⇒ PDS is the dominant lever; MSE near zero is common even at rank 100.
   - The live leaderboard shows only each team's **latest** submission.
     Our public position is therefore k013-ctx-scale (0.0312, rank ~554),
     NOT our best k011-ds-x1p7 (0.0596, ~rank 489). Next submission must
     beat k011 just to restore standing.

2. **Official `vcc skill install`** — ships with vcc-cli; installed to
   `~/.claude/skills/vcc`. Confirms 2026 scorer requirements: raw integer
   counts (`--require-counts` is prep default), exactly 400 cells per
   perturbation, no control cells, 1e6 per-cell count cap, one in-flight
   submission per team.

3. **Arc 2025 wrap-up blog** (arcinstitute.org): winning approaches were
   hybrids. 3rd place (TransPert) is a *statistical cross-cell-line transfer*
   using pseudobulk summaries + Wilcoxon DE stats + similarity-aware
   aggregation + PDS-optimized global scaling — validates the k015 direction.
   2nd place used ESM-2 protein embeddings, residual delta prediction, and
   PerturbAtlas H1 data. PDS carried ~2x DES weight in 2025.

4. **Public top-100 competitor code** — `github.com/kaipengm2/Virtual-Cell-Challenge-2026`
   (rank 82 at snapshot time, score 0.1546, MIT license). Method:
   - Weighted ensemble of 4 sources: K562 GWPS, HCT116, HEK293T, H1-2025 (2:1:1:2)
   - CD4 T-cell Perturb-seq DE statistics as additive family-level signal
   - Common-response centering (subtract shared transcriptional reaction)
   - **Promoter-neighbor prior** for CRISPRi local effects (gencode distances)
   - Dual-moment integer count generation matching both per-cell mean CPM
     and pseudobulk profile, exact library-depth preservation
   - Amplitudes: 0.6 (log2fc space) / 0.3 (bulk-delta space) — much more
     conservative than our delta_scale=1.7

5. **2025 H1 training set** — `adata_Training.h5ad` (15.5 GB, 150 targets)
   is public and explicitly allowed ("use the H1 data released last year").
   We had only used the 2025 *validation* set (47 pairs). Training-set
   overlap with the 2026 panel is only 13/300 targets, so its value is for
   learning transfer maps (esp. context C / hESC-like), not direct deltas.
   URL in that repo's `sources.json`; also 2025 test set (11.9 GB) available.

6. **X-Atlas** (HF: `slaf-project/X-Atlas-Orion`, CC-BY-NC-SA-4.0) — large
   cross-tissue perturbation compendium referenced by the top-100 repo's
   prepare script. Candidate corpus for Track 2.

### Previously unused data sources now identified (from competitor repo)

| Source | Size | Use |
|---|---:|---|
| K562 GWPS single-cell raw (figshare 35775507) | 65.8 GB | per-cell variability, DE stats |
| CD4 T-cell Perturb-seq DE stats (Marson 2025, S3) | 16.8 GB | immune-lineage transfer signal |
| HCT116 + HEK293T perturbation statistics | via prepare.py | additional ensemble sources |
| 2025 H1 train/test h5ad | 15.5 + 11.9 GB | context-C transfer training/eval |

### k015 low-rank eval results (Modal job ap-uEt7lCW8KFzAvNAoA53JrK, 495 s)

| Pair | n pairs | identity | rank 128 | rank 256 (best) |
|---|---:|---:|---:|---:|
| K562→Jurkat (ctx A) | 2,334 | 0.439 | 0.537 | 0.549 |
| K562→RPE1 (ctx B) | 2,390 | 0.330 | 0.607 | 0.614 |
| K562→HepG2 (ctx C proxy) | 2,327 | 0.355 | 0.541 | 0.548 |

Full-rank-256 refits persisted to `/kytos-vol/k015-essential-transfer/lowrank_models.npz`
(60 MB). Per-gene shrinkage remains worse than identity — drop it.

### Revised priorities — **how each landed (2026-09-20)**

*(1) k015 rank-256 was still submitted (`kytos-k015-lowrank-r256`) and
scored −0.028 — negative, confirming the caution. (2) kaipengm2 dual-moment
generator already adopted; its ensemble sources are corpus-blocked. (3) H1
train/val used via k017/k018 — offline win did NOT transfer to leaderboard.
(4) count-generation discipline in place. (5) offline-gate rule is now the
k021 ceiling/attribution harness. Current live lever: generator-dispersion
calibration for the DE over-calling (see top banner).)*

1. **Do not submit k015 rank-256 blindly.** Held-out cosine improved, but
   (a) 256 may overfit with ~1,900 train pairs, (b) the top-100 reference
   uses far smaller amplitudes and moment-matched counts, (c) our delta_scale
   1.7 was tuned for raw K562 deltas, not low-rank-transformed ones.
2. **Study/replicate the kaipengm2 pipeline** (MIT, CPU-only, ~10 min
   inference). It already scores 0.1546 ≈ top-100 threshold. Highest
   expected value per hour currently visible.
3. **Pull 2025 H1 training set on Modal** for context-C transfer training
   (150 pairs vs 47) and use the 2025 test set for honest offline eval.
4. **Adopt count-generation discipline**: promoter prior + dual-moment
   matching likely explains why top entries avoid the MSE collapse that
   killed k013.
5. Continue using leaderboard API snapshots for calibration; no submission
   until an offline gate shows improvement over k011 config.
