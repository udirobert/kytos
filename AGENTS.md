# Kytos — Agent Operating Rules

> Last updated **2026-09-20** — VCC validation reset recorded in §4b;
> Cleveland Clinic / GQAI remains a separate workstream (`docs/cleveland/`).

This file is the ground truth for any agent working on this repo. It covers
the **2026 Virtual Cell Challenge** and a **separate** Cleveland Clinic
Enterprise Challenge (GQAI 2026) workstream. Do not mix their stacks or
run-ID prefixes (`kNNN-*` vs `cNNN-*`). It overrides generic assumptions about
"local dev" because the primary dev machine is **memory- and disk-constrained**.

---

## 0. Cleveland Clinic / GQAI (quantum allostery)

- Docs: `docs/cleveland/`. Code: `src/cleveland/`. Experiments: `experiments/cleveland/`.
- **Venv:** `.venv-cleveland` only (`networkx`, BioPython, scikit-learn). Never
  install Qiskit/Braket/Classiq into `.venv` / `.venv-science`.
- Phase 1 (classical CTRW + coarse-grain Spearman gate) is **local-safe**
  (small graphs). Phase 2+ quantum circuits use challenge Braket/Classiq.
- Secret: `MOTH_API_KEY` in `.env` (see `.env.example`).
- Runner: `.venv-cleveland/bin/python tools/run_cleveland_c001.py`
  … `c007.py` (see `docs/cleveland/`). Qiskit only in `.venv-cleveland`.
- **Compression watch:** cardiac myosin Phase 1 Spearman ρ=0.823 is the
  tightest gate margin — keep it visible. `c007` distal lever → myosin
  best-known rank 3 (null still n.s.).
---
## 1. The local machine (do not assume headroom)

- **RAM: 8 GB** (`sysctl hw.memsize` confirms 8 GiB).
- **Architecture: arm64 macOS**.
- **Useful for:** code, docs, small dry-runs, the Observatory build, and sparse
  baseline `.vcc` generation (e.g. `tools/run_k003_mean_shift.py`).
- **Not useful for:** full `vcc prep`, full evaluator/scorer runs, training,
  holding the 2025 Atlas (6.9 GB source), or any full-panel 2026 prediction that is
  denser than top-300 sparse.
- **Jinja2 is available** in the local `.venv`; `python3 frontend/build.py` works
  and has been verified after PR #1. Do not assume the build is blocked.

When an action would exceed 8 GB, **stop and route it to an external machine**.
Do not attempt to "just run it" and hope swap saves you.

---

## 2. What must run externally

| Task | Why it cannot run locally | Minimum remote | Suggested platform |
|---|---|---|---|
| Full `vcc prep` on a 2026 panel | Peak ~28 GB RAM; 360k cells × ~6k non-zeros per cell | 32 GB RAM | VPS, Vast/RunPod CPU instance, Brev |
| Evaluator/scorer runs on 2025 full validation | 6.9 GB source + held-out splits; >16 GB | 32 GB RAM | VPS / rented instance |
| Atlas 2025 download + prep | Source 6.9 GB, peak ~13 GB | 32 GB RAM + ~50 GB disk | VPS scratch disk |
| Layer A training (gene transfer) | Torch + corpus in memory | 16+ GB GPU or 32 GB RAM | Kaggle free GPU for smoke, then Vast/RunPod/Brev |
| Conditional generative-model training (historical Layer B proposals) | Sustained GPU | 24+ GB GPU | Brev / cloud GPU |
| Real control-cell resampling for 2026 panel | 360k cells × dense matrix | 32 GB RAM | Modal, VPS, Vast/RunPod |

---

## 3. Preferred external compute order

Cheapest / fastest-first for an agent asked to choose:

1. **Kaggle Notebooks** — free GPU/TPU; first stop for smoke tests and EDA on
   public corpora. Use the ratiocine two-phase pattern.
2. **Modal** — serverless Functions/Sandboxes with ≥32 GiB RAM and GPUs;
   excellent for `vcc prep` and controlled 360k-cell runs when you do not want
   to rent a full VPS by the hour. Pay by the second; keep data in a Modal
   Volume if needed.
3. **Vast.ai / RunPod** — hourly rented GPU/CPU; best for long training bursts.
   Pick an instance with ≥32 GB system RAM for non-GPU work.
4. **Brev.dev** — once the challenge credits arrive; do not design around them
   until they are in the account.
5. **Monthly VPS** — only if a persistent cron or long training run is needed.

The repo's `data/raw/` and `experiments/` stay **small**; the external machine
pulls corpora from Hugging Face / Kaggle and writes only small artifacts back
to git.

---

## 4. VCC historical run log and CLI facts

The entries below are historical observations. Some causal interpretations and
"next step" claims are superseded by §4b and the active validation-first
strategy in `docs/vcc-two-track-strategy.md`; do not treat older labels such as
"dead end" as class-wide scientific conclusions.

- `vcc` is logged in as `ungethe@gmail.com` / team `Udi Ngethe`.
- `vcc` version `0.2.0` is installed in `.venv-science/bin/`.
- Legacy `cell-eval 0.8.2` is installed in `.venv-science`; it is not the
  official 2026 six-metric scorer identified in §4b.
- The 2026 `controls` bundle is at `data/raw/vcc2026/` (~660 MB zip; 3 context
  `.h5ad` + `gene_names.csv` + `pert_counts.csv`).
- A `kytos-pipe-test` random `vcc sample` baseline has been submitted and
  scored (`score_avg` ~-0.948). Do **not** submit another random sample; use
  daily slots for real models.
- A `kytos-k003-mean-shift` sparse baseline has also been submitted and scored
  the same (~-0.948). It is a valid pipeline test, not a competitive model.
- A `kytos-k004-real-resampling` full-panel baseline (real control-cell
  resampling, 360k cells × 18.5k genes) was generated and submitted on Modal.
  It scored **overall -0.304** (rank 765), confirming real single-cell
  dispersion helps, while `pds` stays near zero until a target-specific signal
  is added.
- A `kytos-k004-layer-a-b` full-panel target-specific model
  (`ContextConditionedTransfer` + log1p `AdditiveTransportSampler`) was
  submitted on Modal. It scored **overall -0.149** (rank 656) with `pds`
  positive (0.0019), confirming the target-specific knockdown signal is
  detectable.
- A `kytos-k005-atlas-prior` model was built on Modal using the 2025 VCC
  validation to compute real per-target log1p mean-shift signatures. Only
  **4/300** 2026 targets overlapped the 2025 validation, so the model is
  effectively k004-layer-a-b plus four real signatures. The `.vcc` is stored
  on the `kytos-vcc` Modal Volume and can be submitted when the daily
  allowance resets.
- A `kytos-k006-replogle-prior` model was submitted on Modal combining the
  2025 Atlas with the Replogle K562 genome-wide Perturb-seq bulk (9,866
  targets), covering **272/300** 2026 targets. It scored **overall -0.021**
  (rank 534), with `pds` 0.265 and `nmae` -0.074.
- A `kytos-k007-neighbor-prior` model imputed 18 of the 28 unscreened
  targets from confident STRING partners (score >= 0.7, >= 2 partners,
  top-5 score-weighted mean of partner deltas). It scored **overall
  -0.0159** (rank 534), `nmae` +0.002, `fid` -0.403.
- A `kytos-k008-kd-heterogeneity` model kept the k007 priors and replaced
  the sampler with `HeterogeneousTransportSampler` (`kd_std=0.4`, per-cell
  `eta ~ N(1, 0.4)` truncated at 0 — fit from Atlas eta spread ~1.1
  median). It scored **overall -0.0113** (rank 549), `fid` -0.388,
  `nmae` +0.007. Scalar KD heterogeneity was interpreted at the time as a
  modest benefit; the residual fid deficit was hypothesized as off-direction
  covariance (full Layer B problem).
- A `kytos-k008-kd-s0p7` sweep point (`kd_std=0.7`) scored **overall
  +0.0007** (rank 519) — the first positive score. `fid` -0.334, `nmae`
  +0.010, `pds` 0.282. The Atlas measurement (~1.1 median eta std) suggested
  `kd_std=1.0` as the next sweep point at the time; submissions are tagged
  `kytos-k008-kd-s<p>` to keep sweep variants distinguishable.
- A `kytos-k008-kd-s1p0` sweep point (`kd_std=1.0`) scored **overall
  +0.0152** (rank 509), `fid` -0.270, `pds` 0.297, `nmae` +0.011 — every
  component improved again at the Atlas-measured median spread.
- A `kytos-k008-kd-s1p3` sweep point (`kd_std=1.3`) scored **overall
  +0.0291** (rank 490), `fid` -0.209, `pds` 0.311 — fid gains still
  ~0.06/step, not bending. Next probes: `kd_std` 1.7 and ~2.0 (Atlas
  global eta std is 2.32).
- `kytos-k008-kd-s1p7` (`kd_std=1.7`) scored **overall +0.0429** (rank
  477) and `kytos-k008-kd-s2p0` (`kd_std=2.0`) scored **overall +0.0511**
  (rank 462), `fid` -0.111 — the scalar optimum is near ~2.0–2.3 (Atlas
  global eta std 2.32); `nmae` eroding (+0.011 → +0.004) as overspread
  blurs DE signal.
- `kytos-k009-gamma-s1p4` / `kytos-k009-gamma-s2p0` — `GammaKnockdownSampler`
  (positive-support, capped eta_max=5.0, renormalized to E[eta]=1,
  `library_cap="median"` backstop) scored **-0.0011** (rank 565) and
  **+0.0075** (rank 544) respectively. `nmae` hit best-ever +0.020/+0.022
  — mean-preservation works — but `pds` ~0.21 and `fid` ~-0.25 regressed:
  the skewed density piles mass near eta≈0 (unperturbed-looking cells).
  Conclusion recorded at the time: keep the symmetric trunc-normal shape;
  the then-proposed next variant was a mean-corrected trunc-normal (divide
  eta by E[N(1,σ)|η>0]).
- `kytos-k010-mc-s2p0` / `kytos-k010-mc-s4p0` — mean-corrected
  `HeterogeneousTransportSampler` (`mean_correct=True`: eta divided by
  E[max(0, N(1,σ))] = cdf(1/σ) + σ·pdf(1/σ)) scored **+0.0090** (rank 565)
  and **+0.0122** (rank 564). nmae improved to +0.017/+0.019 but fid
  ~-0.30 and pds ~0.29 — interpreted at the time as evidence that the
  champion's ~40% applied-mean inflation was load-bearing. The then-proposed
  lever was explicit delta-scale calibration (borrowed signatures appeared
  systematically weak in 2026 contexts) or off-direction covariance (Layer B).
- `kytos-k011-ds-x1p3` / `kytos-k011-ds-x1p7` — explicit `delta_scale`
  applied to the fully assembled delta (all dispatch tiers) on the champion
  config (`HeterogeneousTransportSampler` kd_std=2.0, uncorrected eta,
  `library_cap="median"`) scored **+0.0559** (rank 502) and **+0.0596**
  (rank 486) — two new best overall scores. `fid` nearly closed (-0.006 at
  x1.7) and `pds` recovered to 0.339, but `nmae` cratered to -0.076:
  magnitude inflation was read at the time as buying direction/discrimination
  at DE-accuracy cost. The scale axis still appeared net-positive (1.3→1.7
  gained +0.004); the then-proposed lever was learned context-conditioned
  Layer A (`docs/k012-learned-layer-a.md` — marker analysis suggested the
  contexts were Jurkat-like/RPE1-like, not hESC).
- **Two-track plan** (`docs/vcc-two-track-strategy.md`, 2026-09-17):
  Track 1 targets top-200 on Modal (delta-scale bracket, paired-transfer
  Layer A per `docs/k012-layer-a-pipeline.md`, lineage-matched corpora,
  residual covariance). Track 2 targets top-100 in parallel on a rented
  GPU — **Nebius** (user has access): L40S/A100-class single VM with
  persistent disk for checkpoints — with a trained perturbation model.
  Modal remains the build/submit path either way.
- `kytos-k014-conditional-mlp` (Track 2 first attempt, 2026-09-18) —
  **negative result**. Conditional MLP (emb 128d + ctx random-proj 256d →
  1024 → 1024 → rank-64 → 18,533 genes) trained on 9,906 samples
  (9,869 targets from `delta_matrix_src.npz`, 47 paired K562/hESC).
  Best held-out cosine = 0.0425 vs identity baseline 0.1406 — model is
  worse than raw K562 transplant. Magnitude ratio collapsed to 0.35.
  Diagnosis recorded at the time: insufficient paired cross-context signal
  (only 47 pairs). Then-proposed next steps: GEARS-style GNN leveraging
  gene-gene graph, or foundation model fine-tune with per-cell Atlas data.
  VM deleted after run to save
  cost; provisioning details in `docs/track2-nebius-setup.md` §8.
- **Track 2 scaffolding ready** (2026-09-18): `tools/track2/` (conditional
  MLP trainer — smoke-tested locally in paired-only mode — bootstrap/stage/
  upload scripts), `tools/run_k014_trained_model.py` +
  `tools/modal_k014_trained_model.py` (consumes exported
  `prediction_deltas.npz` as the 'real' tier, neighbor/fallback backfill,
  champion sampler kd_std=2.0, library_cap=median). Awaiting Nebius VM
  provisioning; `delta_matrix_src.npz` (9,869 targets) already staged on
  `/kytos-vol/paired-transfer/`. Run-ID prefix: `k014-*`.
- `kytos-k011-ds-x2p0` (delta_scale=2.0) scored **+0.0566** (rank 515):
  the scale curve has bent — `pds` best-yet 0.356, `fid` ~0, but `nmae`
  -0.125 now outweighs. The then-current reading was that uniform scalar
  magnitude was exhausted; the proposed next lever was signature content.
- `kytos-k013-ctx-scale` (per-context delta_scale {A:1.7, B:2.65,
  C:0.75} from lineage ||delta|| ratios RPE1 1.57/Jurkat 1.01/hESC
  ~0.44) scored **+0.0312** (rank 560) — clean negative vs uniform x1.7;
  that specific per-context amplitude variant failed. At the time, the audit
  found essential screens overlap 0/300 panel and figshare GWPS is K562-only;
  no matched-lineage public corpus covering the panel had been identified.
  The then-proposed levers were transfer learning (2,393 shared essential
  targets x 4 lineages as supervision) or a Track-2 trained model.
- `kytos-k015-lowrank-r256` (essential-screen low-rank transfer, rank 256,
  all contexts) scored **-0.028** (rank 689) — regression vs k011. Detailed
  components: `pds_cosine` 0.553 (score_pds 0.117), `expr_mse` 5.18
  (score_mse 0.0), `nmae` 1.043 (score_nmae -0.073), `fidelity` 0.449
  (score_fid -0.207), `reach` 0.092, `jaccard` 0.023. Diagnosis at the time:
  the essential-gene low-rank map was OOD for the 2026 panel (0/300 overlap);
  rank-256 projection onto the essential-response subspace discarded target-
  specific signal, collapsing PDS and fidelity. Norm ratios on paired
  essential data were ~0.53–0.59 pred/dst; amplitude was roughly OK with
  delta_scale=1.7 but direction was wrong for panel targets. **Conclusion:
  implementation-specific negative for direct panel prediction, not a
  class-wide falsification.** Saved:
  `experiments/k015-essential-transfer/leaderboard_result.json`.
- **H1-2025 training data extracted** to `/kytos-vol/h1-2025-train/`:
  `h1_train_deltas.npz` (150 targets × 18,080 genes), `adata_Training.h5ad`
  (15.5 GB). Overlap with 2026 panel: 13/300. H1 validation set: 50 targets,
  0 overlap with H1 training targets (clean train/val split). Offline delta-level
  harness (`tools/modal_k017_h1_eval.py`) on 136 H1-train pairs → 47 H1-val
  targets: raw K562 identity top-200 cosine 0.403. After fixing the sweep
  self-gene/scaling bug, rank-64 low-rank + training self-median reset reaches
  top-200 cosine ~0.61 and Pearson ~0.39–0.46. Best composite is
  `h1lr64_ds2p0_selfTrainScaled` (top200 0.610, Pearson 0.435, norm ratio
  0.874); `h1lr64_ds1p3_selfTrain` has the highest top200 (0.614) but low norm
  ratio (0.532). Then-planned next step: count-level offline validation with
  legacy `cell-eval` on 2025 validation before any submission.
- **k017 offline legacy `cell-eval` (count-level, 47 H1-val targets, 400 cells/target,
  4000 controls, minimal profile):** dual-moment count generation showed the
  delta-level gains surviving to count space in that legacy proxy harness.
  `h1lr64_ds2p0_selfTrainScaled` is the best overall (discrimination 0.613,
  overlap 0.233, Pearson-delta 0.246); `h1lr64_ds1p7_selfTrain` has the lowest
  MSE (0.00779) and MAE (0.0554). Identity baseline at ds1.7: discrimination
  0.530, overlap 0.205, Pearson-delta 0.076. H1 transfer was a clear proxy
  improvement on every reported metric. Saved:
  `experiments/k017-offline-cell-eval/full_minimal/`.
- **Lineage score** (`experiments/k012-lineage-score/`): on top-2000
  discriminative genes, context **A is Jurkat-like (0.649)**, B weakly
  RPE1-leaning (0.369), C unresolved (hESC 0.379). Reference controls
  cached on `/kytos-vol/refs/` (K562/RPE1 bulks, Nadig Jurkat+HepG2
  single-cell, 2393-target essential design). LOO transfer eval
  (`experiments/k012-transfer-loo/`): raw K562→hESC cosine ~0.13 — naive
  paired transfer did not ship; lineage-matched corpora was the then-proposed
  Track-1 priority (k013 = per-context prior dispatch).
- **No RPE1/Jurkat/HepG2 GWPS arm exists** (`experiments/k013-lineage-ratios/`):
  only K562 has a genome-wide arm; the other public Replogle/Nadig files are
  2,393-target essential screens overlapping **0/300** panel targets. The
  specific context-B lineage-swap variant failed that coverage check; the
  then-proposed Track-1 lever was 4-lineage essential-set transfer learning
  (k015).
- `kytos-k018-h1lr-dm-c` (H1 rank-64 transfer + dual-moment counts for
  context C only; A/B stay on the k011 champion) scored **+0.042** (rank
  546) — a **regression** vs k011 (+0.0596). Deltas vs champion: `pds`
  -0.058, `nmae` -0.018, `fid` -0.005, `reach` -0.026, `jac` +0.004. The
  k017 offline count-level "clear improvement on every metric" did **not**
  transfer to the leaderboard — another caution that an in-corpus/proxy win
  is not proof. That one-context implementation regressed; it does not
  isolate which signature or sampler mechanism moves `pds`. Saved:
  `experiments/k018-h1-dualmoment/leaderboard_result.json`. Champion remains
  `kytos-k011-ds-x1p7` (+0.0596, rank 486).
- **k019 cross-lineage OOD-proxy gate (proxy diagnostic, `experiments/k019-
  crosslineage/`)**: added an out-of-distribution split to the ~2.3k paired
  essential K562↔lineage deltas (train on cross-lineage-conserved targets,
  test on lineage-specific ones — the closest stand-in for the non-essential
  panel). Held-out cosine on the **OOD-proxy tail**: identity transplant
  (what k011/k018 ship on A/B) is **negative** — Jurkat −0.090, RPE1
  −0.077 — i.e. wrong *sign* of effect on panel-like targets; this was a
  candidate mechanical explanation for `pds`~0.34.
  `global_scalar`/`gene_scale` = identity (scaling / per-gene cannot fix
  direction). **Across-gene maps flip OOD positive**: low_rank Jurkat +0.099
  / RPE1 +0.296; kernel_rbf +0.138 / +0.268. This suggested k015's rank-256
  map direction could be viable, but the OOD proxy did not represent the real
  panel and a controlled comparison would still be required. Tool:
  `tools/run_k019_crosslineage.py` (Modal CPU). Builder + submission (k019 =
  map-applied A/B) deliberately **held** per user 2026-09-19 in favour of
  Track 2; it was the then-proposed fallback if the GNN stalled.
- **k020 Track-2 GNN trainer ready + CPU-proven** (`tools/track2/
  train_gnn_crosslineage.py`): GEARS-style message-passing model — gene-node
  embeddings + co-perturbation correlation graph (no STRING download needed;
  built from `delta_matrix_src` across-target correlation) + context-basal
  conditioning, predicts the lineage delta from the K562 delta. Uses the same
  in-dist vs OOD-proxy split as k019 for validation (never repeat k015).
  Loss falls and it beats identity on the synthetic OOD smoke; NOT a science
  result. Real run needs Nebius GPU + staged `essential_transfer_data.npz`.
  **Path B blocked 2026-09-19**: router DNS returns "No answer" for
  `*.api.nebius.cloud` (public 1.1.1.1/8.8.8.8 resolve it); Nebius OAuth token
  expired → needs `networksetup -setdnsservers Wi-Fi 1.1.1.1 8.8.8.8` +
  interactive browser sign-in (user action). CLI at `~/.nebius/bin/nebius`,
  project-e00sz92bpr005x5c3r80zr.
- **k020 GNN RUN ON NEBIUS + SUBMITTED (2026-09-20, `entry
  iKItvQOyDdOzw4gv4zDJ`)**: DNS fixed, VM booted (L40S), trained on the real
  2,661-sample K562→{Jurkat,RPE1} essential set (HepG2 absent from
  `essential_transfer_data.npz`, so only contexts A/B get GNN deltas; C stays
  on the k011 prior). **Offline OOD gate PASSED at scale**: identity cos_ood
  −0.088 → GNN cos_ood **+0.199**, cos_all 0.249→0.374, in-dist parity
  (0.604→0.585). Panel predict: 300 targets × 272 K562-covered, scattered to
  full 18,533-gene space (`coverage_mask` set to the covered flag; 28
  no-signature targets → neighbour/fallback). Submitted A/B=GNN, C=champion,
  `delta_scale=1.7`, `kd_std=2.0`.
  **Result: rank 811, score_avg −0.114 — a big REGRESSION** vs k011 (+0.0596).
  Components: `expr_mse` raw **23.7** (→ score_mse 0), `score_nmae` **−0.745**
  (the killer), `pds_cosine` 0.528 (≈ parity, no direction gain), `fid` −0.028.
  **Diagnosis at the time: the cosine loss is scale-invariant, so GNN delta
  magnitudes were un-calibrated; the ×1.7 knob (tuned for near-norm K562
  signatures) over-amplified them → expression blew up.** This was the 3rd
  proxy-vs-leaderboard gap (k017→k018, k020). A plausible next test was to
  norm-match each GNN delta to its borrowed K562 signature *before* the
  sampler and drop the blind ×1.7, while recognizing that observed direction
  was only ~parity and upside was uncertain. Nebius VM STOPPED (disk persists, ~small
  monthly SSD cost) pending that decision. `modal_k020_gnn_model.py` is the
  build/submit path (`submit_from_volume` uses `vcc submit <file> --model-name
  <tag>`, NOT `--file/--name`). Champion remains `kytos-k011-ds-x1p7`.
- **k020b norm-matched GNN — implementation-specific negative; Path B paused
  (2026-09-20, `entry coCmgLQW2T5OZRnAk5yW`)**: re-ran the SAME trained
  `gnn.pt` (no retrain, Modal CPU predict via
  `modal_k020_gnn_model.py::predict_and_stage`) but rescaled every GNN delta
  to the L2 norm of its own borrowed K562 signature (`--norm-match`), so
  *direction* was the intended change vs the k011 champion (raw GNN median
  magnitude ratio had been A 0.50 / B 0.37). Result: rank 802, score_avg
  **−0.098** (still a big regression vs k011 +0.0596). Norm-matching reduced
  the expression damage (`expr_mse` 23.7→13.0, `score_nmae` −0.745→−0.601),
  consistent with a magnitude bug, **but `pds_cosine` did NOT improve
  (0.528→0.521)**. The kill criterion (pds meaningfully above champion)
  failed. Observed direction in that implementation was no better than the
  K562 prior, and the OOD-proxy gate (cos_ood −0.088→+0.199) was again
  non-predictive. **Spending on that implementation is paused; this is not a
  class-wide falsification.** Then-proposed alternatives were
  `fidelity`/off-direction covariance (Layer B) or a per-cell Atlas-trained
  generative model. Champion still `kytos-k011-ds-x1p7`.
- **k021 ceiling/attribution analysis (`tools/run_k021_ceiling.py` +
  `tools/modal_k021_ceiling.py`, self-contained Modal CPU, `experiments/k021-ceiling/summary.json`)**:
  an exploratory diagnostic for "signature vs modeling". Three arms on the
  SAME 47 H1-val eval targets: `identity_ds1p7` (borrowed K562 signature),
  `true_ds1p0` (the *true* per-target log1p delta pushed through the identical
  dual-moment generator), and the real-vs-real legacy `cell-eval` `ceiling`.
  Direction-robust `frac = (arm−identity)/(ceiling−identity)`. Within that
  exploratory harness, the observed split by metric family was:
  - **Direction metrics appeared signature-bound.** discrimination_l1
    0.53→**0.96** (ceiling 0.99, sig_frac 0.93); pearson_delta 0.08→0.67
    (ceiling 0.86, sig_frac 0.75). A perfect delta nearly reached the ceiling,
    consistent with signature limitation in that harness; leaderboard `pds`
    (~0.34) may be capped by our inability to *recover* the true delta (mean
    cos(identity,true)=0.11). Audited public corpora had coverage limits
    (K562-only; k020 transfer left direction flat), but exhaustion was not
    established.
  - **DE-count metrics appeared modeling-bound even with a perfect delta.**
    overlap_at_N 0.21→0.38 (ceiling 0.65, mod_frac 0.61); precision_at_N
    0.21→0.32 (ceiling 0.65, mod_frac 0.75). Candidate mechanism:
    `de_nsig_counts_pred` = 6704 (identity) / 5462 (true@1.0) vs **real
    3436** — the generator **over-called DE genes ~1.6–2×**, plausibly because
    the dual-moment per-cell dispersion (kd_std=2.0) inflated apparent DE.
    This suggested a low-cost calibration hypothesis — tune generator
    dispersion so predicted DE-gene-count ≈ real — testable offline on the
    same k021 harness before spending a slot.
  - Auto-verdict string ("signature-limited") was dragged by the mean of the
    two L1-delta metrics; treat it as the qualified split above, not one
    word. Caveat: this was the H1 corpus (k017 offline ≠ k018 leaderboard),
    used a different generator/effect representation, and did not establish
    transferability. Nebius deleted (no residual spend). Champion still
    `kytos-k011-ds-x1p7`.
- **kytos-k026-consensus-w-ctr — SUBMITTED 2026-09-22 (entry
  `E6fr2Xe4zkBxx7RaAD1X`): score_avg +0.0670, rank 512 of 1086.** First
  Gate-B-backed submission: `variant_consensus_w_ctr` deltas (weighted
  K562 2 : HCT116 1 : HEK293T 1 : CD4 1, common-response centered,
  extract-20260921-02-honest) through the unchanged champion generator
  (kd_std=2.0, delta_scale=1.7, library_cap=median, 400 cells/pert,
  360k cells, all-real dispatch). **New champion by score** (+0.0074 over
  k011's +0.0596) though rank nominally dropped 486→512 — the leaderboard
  densified; more submissions sit above 0.067 now than above 0.0596 at the
  k011 snapshot. Gate B predicted +0.033 local avg_score; official delta
  +0.0074 — direction correct, ~4× attenuation, consistent with the
  declared caveats (47/300 eval targets, local bundle ≠ live anchors,
  hESC context only). **cell-eval2 Gate B is validated as a directional
  promotion gate — the first proxy whose sign survived to the
  leaderboard.** Component scores were not displayed at capture time;
  declared regressions (fidelity/jaccard) not yet confirmed on the
  leaderboard. Receipts: `experiments/k026-consensus-w-ctr/`.

---

## 4b. Validation reset (2026-09-20; supersedes broad causal conclusions above)

- The k020/k020b and k021 scores above remain historical observations, not clean
  falsifications of whole model classes. Current-source review found k020's
  consumer failed to retain baseline real priors for absent context C; GNN
  inference rebuilt its graph, aliased absent target indices to zero, and
  zero-filled unmodeled output genes. Archived remote revisions still require
  provenance verification. Do not resume GPU training or silently relabel old runs.
- Leaderboard `score_fid` is DE direction fidelity, not Frechet distance.
  k021 uses dual-moment counts, not the champion sampler, and has no `kd_std`.
  Its mean-log single-cell effect is not a bulk-log effect. The DE over-calling
  mechanism and signature/modeling headroom split are not established.
- `tools/run_k014_trained_model.py` now overlays trained effects on combined
  baseline priors; uncovered targets/contexts retain those priors. The shared
  k007 renderer, k011, sampler settings and legacy RNG sequence are unchanged.
  Exact no-op parity and A-only isolation are verified on synthetic fixtures,
  not yet on the full panel. Existing prediction/meta outputs are protected;
  directories containing staged input artifacts remain usable.
- New consumer artifact contract: scalar `schema_version=1`, scalar
  `effect_space="additive_log1p"`, explicit unique `gene_names`, `contexts`,
  `vcc_targets`, finite `(C,T,G)` deltas, boolean `(C,T)` coverage mask. Gene
  names must exactly cover the consumer axis (reordering is supported).
  Old MLP/GNN exports lack this metadata and intentionally fail closed; an
  audited producer/conversion update is required, not invented labels.
- `tools/run_k022_pipeline_audit.py` is a diagnostic scaffold: disjoint
  fit/evaluation cells, champion-path transport, direct cell/bulk moments,
  null arms, preserved split manifests and hashes. It does NOT compute DE or
  the six official scores and is NOT a submission gate. Synthetic smoke:
  `experiments/k022-pipeline-audit/smoke/summary.json`. Full real-data and
  official-metric validation, GNN rehabilitation, residual modeling and the
  complementary-data audit remain pending; no new submission is justified yet.
- User approved **one Modal CPU pilot** after the estimate. Run
  `pilot-20260920-01`, app `ap-tT4vyif5ZftRY7WPcFJlRR`, completed its preflight
  and STOPPED: `source_gene_axis_incomplete`. Atlas is 98,927 x 18,080;
  source is 47 x 18,533. Exactly three Atlas labels are absent from source:
  `HSPA14-1`, `TBCE-1`, `TMSB15B-1`. Do not strip suffixes or infer equivalence
  without feature-ID evidence. Other gates passed: 38,176 controls; ACLY 1,026,
  ANXA6 2,496, ARPC2 980 cells. The diagnostic subprocess did NOT execute.
  Artifacts: `experiments/k022-pipeline-audit/pilot-20260920-01/` (preflight and
  execution receipt). Actual cost is unavailable from retrieved CLI metadata;
  do not substitute the historical ~$0.13 per-attempt estimate for a billed
  charge.
- **Axis blocker resolved (2026-09-21).** Metadata-only audit
  (`axis-20260921-01`, `tools/audit_gene_axis.py` +
  `tools/modal_k022_axis_audit.py`) proved the three labels are
  `make_unique`-style duplicate-symbol artifacts: each base symbol also
  exists, the Atlas `var` has no stable feature-ID columns, and the
  suffixed rows have distinct dropout/mean profiles — suffix mapping
  would fabricate effects. Resolution: **recorded drop** to the 18,077-label
  aligned axis via `--allow-axis-drop` (strict-by-default; >50-label
  mismatch still blocks). Report:
  `experiments/k022-pipeline-audit/axis-20260921-01/axis_report.json`.
  `pilot-20260921-01` failed on a backed-AnnData view-of-a-view defect
  (fixed — `var_keep` is threaded through `run_audit` and applied in one
  `(obs, var)` index); `pilot-20260921-02` then COMPLETED the 3-target
  proxy diagnostic. The full paired-panel run `paired47-20260921-01`
  evaluated 32/47 targets (15 under-powered). Key findings: transport
  null calibrated on controls (variance ratio 1.05); borrowed K562
  signatures reach median cosine 0.268 vs 0.514 for measured in-context
  deltas — **signature content is the quantified bottleneck**; and the
  precomputable transferability gate is **falsified**
  (cos(delta_k562, delta_hesc) predicts borrowed success at r≈0.22).
  Diagnostics only — proxy evidence class, not a promotion gate.
  Receipts: `experiments/k022-pipeline-audit/paired47-20260921-01/`.
- Official scorer located via the VCC CLI guide: public
  `https://github.com/ArcInstitute/cell-eval2`, inspected revision
  `5e64833518a6603a0301cbe28185d49c30f4a986` (package version 0.16.0).
  Its `vcc2026` PRESET includes the six 2026 metrics and supports CPU execution.
  PDS excludes ALL panel target genes; DE uses real controls, arithmetic CPM
  means, a control-expression filter of 5 CPM, per-perturbation BH and epsilon
  1e-9. Source settings and caveats are captured in
  `experiments/k022-pipeline-audit/scorer_contract.json`. **Pinned + smoke-tested
  (2026-09-21):** `.venv-eval2` (Python 3.12.8) holds cell-eval2 0.16.0 at the
  pinned revision plus `pdex`; `tools/check_cell_eval2_contract.py` exercised
  `run → baseline → prep-real-bundle → score --real-bundle` end to end on a
  synthetic fixture and enrolled a competition bundle (rule_digest set, zero
  mismatches). Resolved contract: cpu + pdex + bulk_lognorm + counts input;
  `pert_col` defaults to `target` (Atlas uses `target_gene` — must reconcile);
  fractional predictions under `input_type=counts` are baseline-only. Report:
  `experiments/k022-pipeline-audit/eval2_contract_smoke.json`. Production
  equivalence remains unverified (anchor-bundle rules, DE-engine parity vs
  production, pert_col naming). Local `cell-eval` 0.8.2 `vcc` profile remains
  the unrelated legacy three-metric suite.
- Local verification (existing science venv, no installations):
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv-science/bin/python -m pytest -q tests/test_prediction_parity.py tests/test_pipeline_audit.py tests/test_models.py tests/test_transfer.py`.
  The initial targeted run passed 39 tests; two subsequent output-safety tests
  also passed in the final 21-test consumer run. Ruff checks pass for the
  consumer, audit runner and their two test files. Heavy runs still require
  external-compute/budget confirmation under section 6.

---

## 5. Daily workflow guardrails

- **≤2 submissions / day.** Prefer dry-runs (`vcc prep --dry-run`) before live
  `vcc submit`.
- **If a submission is stuck in scoring**, use `vcc cancel <entry-id> --yes`.
  It does not count against the daily limit.
- **Never commit** `.env`, raw `.vcc`, or large `.h5ad` files. `.vcc` and
  prediction `.h5ad` live in `experiments/<run>/` or `data/raw/`, both
  gitignored.
- **Long jobs** use `nohup` + log files from the start, never a live terminal.
- **Chronicle videos never go in git** — the build caps media at 4 MB.
  Upload renders to Grove/Lens (`docs/chronicle/context-layer.md` §8) and
  reference the `gateway_url` in `shorts.json`; posters/captions stay local.

---

## 6. What to do when the user says "go ahead" on a heavy task

Before running anything that could take >30 minutes or use >6 GB RAM:

1. Confirm the target machine (local vs external).
2. If local, run a small dry-run first and report expected memory/time.
3. If external, ask for the host, key, or platform choice before writing
   deployment scripts.

This repo is a **competition science project**, not a local web app. The
fastest path to a better score is almost never "run it on this Mac."
