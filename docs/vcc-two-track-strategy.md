# VCC strategy — validation first

Status: **ACTIVE** · Updated **2026-09-20** · Owner: udingethe

This file is the single active research strategy. Historical scores and run
notes stay in `experiments/README.md`; older strategy/runbook documents are
appendices only and must not be used to select the next experiment without
checking their validity caveats.

## Current state

- **Best recorded submission:** `kytos-k011-ds-x1p7`, overall
  **+0.059575**, observed rank **486** at publication (entry
  `dZk0Sca5UtJluzzfUdMf`). Treat all ranks and thresholds as dated snapshots;
  refresh them before using them for planning.
- **Objective:** make comparisons trustworthy before choosing the next model
  change. We are not assuming that more architecture complexity is the missing
  ingredient.
- **Implementation progress:** strict prediction-artifact metadata, baseline
  backfill for uncovered targets/contexts, no-op parity and A-only context
  isolation are verified on synthetic fixtures. Full-panel parity is not yet
  verified.
- **Current blocker:** k022 stopped at preflight because the source axis lacks
  three Atlas labels: `HSPA14-1`, `TBCE-1`, and `TMSB15B-1`. No prediction and
  no model-performance result was produced.
- **Scorer:** the public `cell-eval2` implementation and `vcc2026` preset were
  identified, including the six scored metrics and CPU execution path. It is
  **identified, not integrated or proven equivalent to the live scorer**.
  Contract notes: `experiments/k022-pipeline-audit/scorer_contract.json`.
- **Next action:** resolve the three features using stable identifiers, then
  obtain approval for the next bounded run. No automatic second launch.

## What the history establishes—and does not

| Earlier interpretation | Updated reading |
|---|---|
| Cross-lineage transfer is dead | The tested implementations regressed, but consumer, graph, and axis confounds prevent a clean model-class conclusion. Spending stays paused. |
| k020 failed because cosine loss left magnitude unconstrained | Norm matching reduced magnitude damage, but other unresolved implementation differences remain; direction transfer is still unproven. |
| k021 proves the remaining gap splits cleanly into signature vs count modeling | It is exploratory evidence only: it used a different generator and an effect representation mismatched to that generator. |
| `fid` indicates missing covariance | The leaderboard `fid` is DE direction fidelity, not a distribution distance. It does not diagnose covariance by itself. |
| Public corpora are exhausted | Audited sources have real coverage limits, but a targeted complementary-source audit has not been completed. |
| k022 was a negative experiment | Preflight blocked on gene alignment. It was not a model result. |

## Decision sequence

### Gate A — data and pipeline integrity

Resolve the k022 source-axis mismatch using feature metadata and stable gene
IDs. Do not strip suffixes or infer equivalence from spelling. Record the gene
universe and every dropped or remapped feature.

Also establish real-input parity:

- an unchanged artifact must reproduce the intended baseline;
- an A-only intervention must leave B/C unchanged;
- missing targets, genes, contexts, and ambiguous units must fail closed;
- artifact hashes and cell splits must be preserved.

**Pass criterion:** the experiment changes only what it claims to change.

### Gate B — official scoring contract

Integrate a pinned `cell-eval2` environment using the `vcc2026` preset, not
legacy `vcc` or `minimal`. Explicitly pin and record the DE backend, target
column, control handling, normalization, target-gene exclusions, panel, and
reference-anchor version. Validate backend differences rather than assuming
CPU/GPU numerical equivalence.

Important implication: `pds_cosine` excludes all panel target genes. Direct
self-knockdown is not PDS signal, and PDS rank values are panel-dependent.

**Pass criterion:** we can state precisely what an offline score measures and
what production differences remain.

### Gate C — controlled baseline diagnosis

After alignment and scorer setup, compare borrowed and measured effects using
disjoint fit/evaluation cells and generator-appropriate representations.
Measure achieved effects after count generation, not only requested vectors.
Report cell-fit statistics, variance, zeros, depth, and target-level
uncertainty alongside any official metrics.

Do not construct a new “overall” score from unrelated diagnostics.

**Pass criterion:** the result identifies a specific error mechanism, not
merely another aggregate that looks better.

### Gate D — conservative signature correction

Only then test bounded corrections to the champion:

- partial common-response adjustment, with target-specific signal protected;
- uncertainty-aware shrinkage using replicate/guide evidence where available;
- a small, regularized residual correction that degrades to the baseline under
  weak support;
- complementary data where it answers a specific coverage or uncertainty gap.

**Pass criterion:** improvement survives count generation, target-grouped or
context-held-out validation, and does not depend on a few targets.

### Gate E — submission

A submission needs a frozen artifact, the recorded k011 comparison, declared
expected component changes, and explicit approval. A favorable proxy cosine,
three-target result, or unverified scorer output is not sufficient.

## Paused work

- GPU training and new architectures remain paused pending Gates A–C.
- The archived MLP/GNN artifacts intentionally fail the strict consumer schema;
  reuse requires an audited conversion and code-revision provenance.
- Do not relabel old runs or change their saved scores. Add dated corrections
  beside their interpretation.
- Observatory work may continue independently because it does not depend on
  this validation bottleneck.

## If a gate fails

- **Gene axis unresolved:** inspect source and Atlas feature metadata; do not
  normalize labels silently.
- **Scorer not production-equivalent:** use only raw diagnostic comparisons and
  record the limitation; do not spend a submission slot.
- **Measured-effect diagnostics disagree with transport assumptions:** fix
  representation or generation before choosing a signature model.
- **A candidate correction wins on one proxy but damages production-equivalent
  metrics:** reject it rather than averaging conflicting evidence.

Top 100 remains the objective. The current plan is validation-first because a
larger model cannot compensate for an experiment whose axes, units, scorer, or
unchanged controls are wrong.

---

## Historical two-track plan (appendix only)

The sections below preserve the plan that led to the rented-GPU Track 2
experiment. Its scores remain observations; its causal conclusions and action
items are superseded by this file, `AGENTS.md`, and `experiments/README.md`.

## Historical scoreboard snapshot (984+ entries, dated)

| | us (best) | top 200 | top 100 | #1 |
|---|---:|---:|---:|---:|
| overall | +0.060 | +0.134 | +0.158 | +0.292 |
| pds | 0.339 | ~0.52 | 0.699 | 0.830 |
| nmae | -0.076 | ~+0.13 | +0.145 | +0.220 |
| fid | -0.006 | ~-0.003 | -0.019 | +0.085 |

`pds` (perturbation discrimination) and `nmae` (DE log-FC accuracy) were the
gating metrics in this historical plan. The statement that `fid` was solved
and that the remaining gap was cleanly signature-bound is superseded; `fid`
is DE direction fidelity, not a covariance diagnostic.

## Historical Track 1 — top-200 Modal plan

Goal: ~+0.13 overall. Stays on the existing Modal pipeline (64 GiB CPU
Functions, `kytos-vcc` Volume, `submit_from_volume` flow). Ordered by
expected value per engineering hour:

1. ~~Bracket delta_scale~~ — **done 2026-09-18**: x1.3 +0.0559 →
   x1.7 **+0.0596** (champion) → x2.0 +0.0566. Optimum ~1.7; `pds`/`fid`
   keep improving with scale but `nmae` cost now dominates
   (+0.004 → -0.023 → -0.076 → -0.125). The then-current reading was that
   the scalar magnitude axis was exhausted — remaining levers appeared to be
   signature content, not amplitude.
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

## Historical Track 2 — top-100 rented-GPU plan (paused after implementation-specific negatives)

*(Ran to completion below: k020 raw GNN −0.114, k020b norm-matched −0.098,
with `pds` not improving. Source review later found implementation confounds,
so this is not a class-wide falsification of transfer models. Nebius deleted.
Kept as the record of what was tried.)*

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

## Historical sequencing (not active)

- **Done**: x2.0 submitted + scored (2026-09-18); scale bracketed at ~1.7.
- **Done (negative)**: Track 1 item 3(b) — the RPE1 GWPS panel-coverage check
  is answered by `experiments/k013-lineage-ratios/report.json`: **no RPE1 GWPS
  arm exists** (only K562 has a genome-wide arm; rpe1/jurkat/hepg2 public files
  are the 2,393-target essential screen, overlapping **0/300** panel targets).
  The specific context-B lineage-swap variant failed that coverage check.
- **Done (negative)**: k014 conditional MLP baseline (2026-09-18). Model cosine
  0.0425 vs identity 0.1406 — worse than raw transplant. Root cause recorded at
  the time: only 47 paired examples; no cross-context signal to learn. See
  `docs/track2-nebius-setup.md` §8 for full details.
- **Then-current**: 4-lineage essential-screen transfer learning (item 3a) —
  richer paired data (2,393 targets × 4 contexts) than the 47-pair
  K562/hESC set that failed LOO. Run ID: k015 (k014 is reserved for
  Track-2 trained-model submissions).
- **Then-next (Track 2)**: GEARS-style GNN on Nebius. The conditional MLP
  failure motivated graph structure for generalization. See §9 below.
- The old rule to keep spending daily slots on Track 1 is superseded by the
  Gate E submission requirements in the active strategy.

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
     ⇒ In that snapshot, PDS appeared to be the dominant scored component;
     MSE near zero was common even at rank 100. This was a leaderboard
     reading, not proof of the causal mechanism.
   - The live leaderboard at that time showed only each team's **latest**
     submission. Our public position was therefore k013-ctx-scale (0.0312,
     rank ~554), NOT our best k011-ds-x1p7 (0.0596, ~rank 489).

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

### Then-current revised priorities — **how each landed (2026-09-20)**

*(1) k015 rank-256 was still submitted (`kytos-k015-lowrank-r256`) and
scored −0.028 — negative, confirming the caution. (2) kaipengm2 dual-moment
generator already adopted; its ensemble sources are corpus-blocked. (3) H1
train/val used via k017/k018 — offline win did NOT transfer to leaderboard.
(4) count-generation discipline in place. (5) k021 is now classified as an
exploratory diagnostic with generator/effect-space mismatches, not a proven
offline gate. The then-current generator-dispersion hypothesis is superseded
by Gates A–C in the active strategy.)*

1. **Do not submit k015 rank-256 blindly.** Held-out cosine improved, but
   (a) 256 may overfit with ~1,900 train pairs, (b) the top-100 reference
   uses far smaller amplitudes and moment-matched counts, (c) our delta_scale
   1.7 was tuned for raw K562 deltas, not low-rank-transformed ones.
2. **Study/replicate the kaipengm2 pipeline** (MIT, CPU-only, ~10 min
   inference). It scored 0.1546 ≈ the then-current top-100 threshold. Highest
   expected value per hour then visible.
3. **Pull 2025 H1 training set on Modal** for context-C transfer training
   (150 pairs vs 47) and use the 2025 test set for honest offline eval.
4. **Adopt count-generation discipline**: promoter prior + dual-moment
   matching likely explains why top entries avoid the MSE collapse that
   killed k013.
5. Continue using leaderboard API snapshots for calibration; no submission
   until an offline gate shows improvement over k011 config.
