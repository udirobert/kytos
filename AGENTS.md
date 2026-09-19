# Kytos — Agent Operating Rules

> Last updated **2026-09-15** — Cleveland Clinic / GQAI workstream added
> alongside VCC (namespaced under `cleveland/`; see `docs/cleveland/`).

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
- **Not useful for:** full `vcc prep`, full `cell-eval run`, training, holding
  the 2025 Atlas (6.9 GB source), or any full-panel 2026 prediction that is
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
| `cell-eval run --ceiling` on 2025 full validation | 6.9 GB source + held-out splits; >16 GB | 32 GB RAM | VPS / rented instance |
| Atlas 2025 download + prep | Source 6.9 GB, peak ~13 GB | 32 GB RAM + ~50 GB disk | VPS scratch disk |
| Layer A training (gene transfer) | Torch + corpus in memory | 16+ GB GPU or 32 GB RAM | Kaggle free GPU for smoke, then Vast/RunPod/Brev |
| Layer B / flow-matching | Sustained GPU | 24+ GB GPU | Brev / cloud GPU |
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

## 4. VCC / CLI facts (state as of 2026-09-09)

- `vcc` is logged in as `ungethe@gmail.com` / team `Udi Ngethe`.
- `vcc` version `0.2.0` is installed in `.venv-science/bin/`.
- `cell-eval 0.8.2` is installed in `.venv-science`.
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
  `nmae` +0.007. Scalar KD heterogeneity helps modestly; the residual fid
  deficit is likely off-direction covariance (full Layer B problem).
- A `kytos-k008-kd-s0p7` sweep point (`kd_std=0.7`) scored **overall
  +0.0007** (rank 519) — the first positive score. `fid` -0.334, `nmae`
  +0.010, `pds` 0.282. The Atlas measurement (~1.1 median eta std) suggests
  `kd_std=1.0` is the next point to test; submissions are tagged
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
  Conclusion: keep the symmetric trunc-normal shape; next variant is a
  mean-corrected trunc-normal (divide eta by E[N(1,σ)|η>0]).
- `kytos-k010-mc-s2p0` / `kytos-k010-mc-s4p0` — mean-corrected
  `HeterogeneousTransportSampler` (`mean_correct=True`: eta divided by
  E[max(0, N(1,σ))] = cdf(1/σ) + σ·pdf(1/σ)) scored **+0.0090** (rank 565)
  and **+0.0122** (rank 564). nmae improved to +0.017/+0.019 but fid
  ~-0.30 and pds ~0.29 — conclusive that the champion's ~40% applied-mean
  inflation is load-bearing: the score rewards applied delta magnitude,
  not dispersion-at-mean-1. Next lever: explicit delta-scale calibration
  (borrowed signatures appear systematically weak in 2026 contexts) or
  off-direction covariance (Layer B).
- `kytos-k011-ds-x1p3` / `kytos-k011-ds-x1p7` — explicit `delta_scale`
  applied to the fully assembled delta (all dispatch tiers) on the champion
  config (`HeterogeneousTransportSampler` kd_std=2.0, uncorrected eta,
  `library_cap="median"`) scored **+0.0559** (rank 502) and **+0.0596**
  (rank 486) — two new best overall scores. `fid` nearly closed (-0.006 at
  x1.7) and `pds` recovered to 0.339, but `nmae` cratered to -0.076:
  magnitude inflation buys direction/discrimination at DE-accuracy cost.
  Scale axis still net-positive (1.3→1.7 gained +0.004); next real lever is
  learned context-conditioned Layer A (`docs/k012-learned-layer-a.md` —
  marker analysis suggests contexts are Jurkat-like/RPE1-like, not hESC).
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
  Root cause: insufficient paired cross-context signal (only 47 pairs).
  Next steps: GEARS-style GNN leveraging gene-gene graph, or foundation
  model fine-tune with per-cell Atlas data. VM deleted after run to save
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
  -0.125 now outweighs. Optimum ~1.7 (+0.0596, rank 486 = champion);
  scalar magnitude axis exhausted. Next lever: signature content.
- `kytos-k013-ctx-scale` (per-context delta_scale {A:1.7, B:2.65,
  C:0.75} from lineage ||delta|| ratios RPE1 1.57/Jurkat 1.01/hESC
  ~0.44) scored **+0.0312** (rank 560) — clean negative vs uniform x1.7;
  per-context amplitude is a dead end. **Corpus coverage reality:
  essential screens overlap 0/300 panel; figshare GWPS is K562-only —
  no public corpus covers the panel in a matched lineage.** Remaining
  levers: transfer learning (2,393 shared essential targets x 4
  lineages as supervision) or Track-2 trained model.
- `kytos-k015-lowrank-r256` (essential-screen low-rank transfer, rank 256,
  all contexts) scored **-0.028** (rank 689) — regression vs k011. Detailed
  components: `pds_cosine` 0.553 (score_pds 0.117), `expr_mse` 5.18
  (score_mse 0.0), `nmae` 1.043 (score_nmae -0.073), `fidelity` 0.449
  (score_fid -0.207), `reach` 0.092, `jaccard` 0.023. Diagnosis: the
  essential-gene low-rank map is OOD for the 2026 panel (0/300 overlap);
  rank-256 projection onto essential-response subspace discards target-
  specific signal, collapsing PDS and fidelity. Norm ratios on paired
  essential data were ~0.53–0.59 pred/dst; amplitude roughly OK with
  delta_scale=1.7 but direction is wrong for panel targets. **Conclusion:
  low-rank essential-screen transfer is a dead end for direct panel
  prediction.** Saved: `experiments/k015-essential-transfer/leaderboard_result.json`.
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
  ratio (0.532). Next: count-level offline validation with cell-eval on 2025
  validation before any submission.
- **k017 offline cell-eval (count-level, 47 H1-val targets, 400 cells/target,
  4000 controls, minimal profile):** dual-moment count generation confirms the
  delta-level gains survive to count space. `h1lr64_ds2p0_selfTrainScaled` is
  the best overall (discrimination 0.613, overlap 0.233, Pearson-delta 0.246);
  `h1lr64_ds1p7_selfTrain` has the lowest MSE (0.00779) and MAE (0.0554).
  Identity baseline at ds1.7: discrimination 0.530, overlap 0.205,
  Pearson-delta 0.076. H1 transfer is a clear improvement on every metric.
  Saved: `experiments/k017-offline-cell-eval/full_minimal/`.
- **Lineage score** (`experiments/k012-lineage-score/`): on top-2000
  discriminative genes, context **A is Jurkat-like (0.649)**, B weakly
  RPE1-leaning (0.369), C unresolved (hESC 0.379). Reference controls
  cached on `/kytos-vol/refs/` (K562/RPE1 bulks, Nadig Jurkat+HepG2
  single-cell, 2393-target essential design). LOO transfer eval
  (`experiments/k012-transfer-loo/`): raw K562→hESC cosine ~0.13 — naive
  paired transfer doesn't ship; lineage-matched corpora is the Track-1
  priority (k013 = per-context prior dispatch).
- **No RPE1/Jurkat/HepG2 GWPS arm exists** (`experiments/k013-lineage-ratios/`):
  only K562 has a genome-wide arm; the other public Replogle/Nadig files are
  2,393-target essential screens overlapping **0/300** panel targets. The
  context-B lineage-swap variant is dead; remaining Track-1 lever is
  4-lineage essential-set transfer learning (k015).

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
