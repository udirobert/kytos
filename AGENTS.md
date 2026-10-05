# Kytos — Agent Operating Rules

> Last updated **2026-10-03** — the agreement-gate axis is **closed**: k035
> and k038 both tied the champion (+0.1242/+0.1254 vs +0.1262) with
> opposite component reshuffles (pds↔reach trade). k033 trained-signature
> track (Modal GPU) remains **complete with a negative Gate B result** (no
> submission); §4b's GPU-training pause is **re-instated**. The §4b
> validation reset still supersedes broad §4 conclusions. Cleveland
> Clinic / GQAI remains a separate workstream (`docs/cleveland/`).

This file is the ground truth for any agent working on this repo. It covers
the **2026 Virtual Cell Challenge** and a **separate** Cleveland Clinic
Enterprise Challenge (GQAI 2026) workstream. Do not mix their stacks or
run-ID prefixes (`kNNN-*` vs `cNNN-*`). It overrides generic assumptions about
"local dev" because the primary dev machine is **memory- and disk-constrained**.

## Publication embargo (active until the Oct 22 final test set)

The repo is public and competitors read it. **Code, tools, and
infrastructure still push to `main`.** Because the method is already public
via that code, docs may describe variant internals (weights, samplers,
configs). **The embargoed unit is exact non-leaderboard metric values and
analysis not derivable from code or the public leaderboard:** score tables,
per-metric results, diagnostic cosines/correlations, and harness numbers go
to `experiments/_embargoed/` (gitignored, local-only; consolidated at
`experiments/_embargoed/diagnostic-numbers.md`) — never to
`experiments/<kNNN-*>/` tracked dirs, never into public docs. Public docs
state qualitative outcomes ("Gate B validated", "variant X won", "borrowed
signatures reach roughly half of measured transfer") plus
leaderboard-public facts (scores/ranks/component scores are on the public
leaderboard). Publish `experiments/_embargoed/` after Oct 22 with history
intact. When in doubt, keep it local.

**Dated facts live in exactly one place.** Current-state facts (champion,
scorer env, gate status) are recorded here (run log) and in
`docs/vcc-two-track-strategy.md` / `experiments/README.md`; other docs link
to those rather than restating them, and status headers get updated in the
same commit as the fact.

---

## 0. Cleveland Clinic / GQAI (quantum allostery)

- Docs: `docs/cleveland/`. Code: `src/cleveland/`. Experiments: `experiments/cleveland/`.
- **Venv:** `.venv-cleveland` only (`networkx`, BioPython, scikit-learn). Never
  install Qiskit/Braket/Classiq into `.venv` / `.venv-science`. **As of
  2026-10-03 that env does not exist locally** (only `.venv` does, and it has
  `networkx` + `scikit-learn` but no BioPython), so the `c001`–`c007` runners
  break on the `Bio.PDB` import in `src/cleveland/pdb/__init__.py`. The isolation rule above still
  stands; rebuilding `.venv-cleveland` is a pending user decision.
- Phase 1 (classical CTRW + coarse-grain Spearman gate) is **local-safe**
  (small graphs). Phase 2+ quantum circuits use challenge Braket/Classiq.
- Secret: `MOTH_API_KEY` in `.env` (see `.env.example`).
- Runner: `.venv-cleveland/bin/python tools/run_cleveland_c001.py`
  … `c007.py` (see `docs/cleveland/`). Qiskit only in `.venv-cleveland`.
- **`c008` (2026-10-04) is the live Moth Hack entry** — protein contact-graph
  coupling maps (KRAS G12C + cardiac myosin + random control) through Moth's
  `graph-v1` engine on IBM `ibm_fez`; real-hardware tomography + qpixl
  read-back (Pearson 0.98). No `.venv-cleveland` needed — everything ran via
  `experiments/cleveland/c008-moth-qpu-tomography/reproduce/engine_client.py`
  (curl, `MOTH_API_KEY`). The interactive exhibit is `/quantum/` on the
  Observatory. Phase C (our own Laplacian CTQW compiled to OpenQASM 2,
  verified vs expm at Pearson 0.991, `reproduce/qasm_ctqw.py`) is
  **engine-blocked**: `tomography-api-v2` timed out on every submission —
  retry before the 2026-10-05 23:59 PT deadline if the engine recovers.
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
- **Environment reality check (verified 2026-10-03).** The older entries below
  name local venvs that no longer exist: the only local venv is `.venv`
  (uv CPython 3.12.8 — pytest 9.1.1, anndata/scipy stack; the four cited
  science test files pass there, 43 tests, no installs needed). `.venv-eval2`
  was deleted 2026-09-23 for disk (rebuild recipe in
  `docs/phase0-environment.md`); `.venv-science` and `.venv-cleveland` are also
  gone, so `vcc`, legacy `cell-eval 0.8.2` and the cleveland runners are NOT
  available locally.
- The `vcc` CLI (0.2.2) lives on `snapflip-vultr` at `/opt/kytos/.venv/bin/vcc`
  (credentialed, `token_source: file`) and inside the Modal job images. Use it
  there, not locally.
- The 2026 `controls` bundle is NOT held locally any more (only
  `gene_names.csv` / `pert_counts.csv` / `manifest.json` remain in
  `data/raw/vcc2026/`); the 3 context `.h5ad` files live on
  `snapflip-vultr:/opt/kytos/repo/data/raw/vcc2026/` and every Modal build job
  re-downloads them via `vcc datasets download controls`.
- Legacy `cell-eval 0.8.2` was never the official 2026 six-metric scorer
  identified in §4b.
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
  Held-out cosine was well below the raw-transplant identity baseline —
  the model is worse than doing nothing; magnitude collapsed
  (exact values embargoed: `experiments/_embargoed/diagnostic-numbers.md`).
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
  essential data were sub-unity (exact values embargoed); amplitude was
  roughly OK with
  delta_scale=1.7 but direction was wrong for panel targets. **Conclusion:
  implementation-specific negative for direct panel prediction, not a
  class-wide falsification.** Saved:
  `experiments/k015-essential-transfer/leaderboard_result.json`.
- **H1-2025 training data extracted** to `/kytos-vol/h1-2025-train/`:
  `h1_train_deltas.npz` (150 targets × 18,080 genes), `adata_Training.h5ad`
  (15.5 GB). Overlap with 2026 panel: 13/300. H1 validation set: 50 targets,
  0 overlap with H1 training targets (clean train/val split). Offline delta-level
  harness (`tools/modal_k017_h1_eval.py`) on 136 H1-train pairs → 47 H1-val
  targets: raw K562 identity top-200 cosine was moderate; after fixing the
  sweep self-gene/scaling bug, rank-64 low-rank + training self-median reset
  improved it substantially. Best composite is
  `h1lr64_ds2p0_selfTrainScaled`; `h1lr64_ds1p3_selfTrain` has the highest
  top-200 but low norm ratio. Exact values embargoed:
  `experiments/_embargoed/diagnostic-numbers.md`. Then-planned next step: count-level offline validation with
  legacy `cell-eval` on 2025 validation before any submission.
- **k017 offline legacy `cell-eval` (count-level, 47 H1-val targets, 400 cells/target,
  4000 controls, minimal profile):** dual-moment count generation showed the
  delta-level gains surviving to count space in that legacy proxy harness.
  `h1lr64_ds2p0_selfTrainScaled` is the best overall; `h1lr64_ds1p7_selfTrain`
  has the lowest MSE/MAE; both clearly beat the identity ds1.7 baseline on
  every reported metric (exact values embargoed:
  `experiments/_embargoed/diagnostic-numbers.md`). H1 transfer was a clear proxy
  improvement on every reported metric. Saved:
  `experiments/k017-offline-cell-eval/full_minimal/`.
- **Lineage score** (`experiments/k012-lineage-score/`): on top-2000
  discriminative genes, context **A is clearly Jurkat-like**, B weakly
  RPE1-leaning, C unresolved (exact scores embargoed). Reference controls
  cached on `/kytos-vol/refs/` (K562/RPE1 bulks, Nadig Jurkat+HepG2
  single-cell, 2393-target essential design). LOO transfer eval
  (`experiments/k012-transfer-loo/`): raw K562→hESC cosine was low (exact
  value embargoed) — naive paired transfer did not ship; lineage-matched corpora was the then-proposed
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
  (what k011/k018 ship on A/B) is **negative** on both lineage tails —
  i.e. wrong *sign* of effect on panel-like targets; this was a
  candidate mechanical explanation for `pds`~0.34.
  `global_scalar`/`gene_scale` = identity (scaling / per-gene cannot fix
  direction). **Across-gene maps flip OOD positive** (low_rank, kernel_rbf;
  exact values embargoed: `experiments/_embargoed/diagnostic-numbers.md`).
  This suggested k015's rank-256
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
  interactive browser sign-in (user action). CLI at `~/.nebius/bin/nebius`;
  project ID via `nebius` CLI / console (IDs removed from tracked docs
  2026-09-23).
- **k020 GNN RUN ON NEBIUS + SUBMITTED (2026-09-20, `entry
  iKItvQOyDdOzw4gv4zDJ`)**: DNS fixed, VM booted (L40S), trained on the real
  2,661-sample K562→{Jurkat,RPE1} essential set (HepG2 absent from
  `essential_transfer_data.npz`, so only contexts A/B get GNN deltas; C stays
  on the k011 prior). **Offline OOD gate PASSED at scale**: GNN cos_ood
  flipped from clearly negative (identity) to clearly positive, cos_all
  improved substantially, in-dist parity held (exact values embargoed:
  `experiments/_embargoed/diagnostic-numbers.md`). Panel predict: 300 targets × 272 K562-covered, scattered to
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
  *direction* was the intended change vs the k011 champion (raw GNN deltas
  had been severely under-magnitude on A/B; exact ratios embargoed). Result: rank 802, score_avg
  **−0.098** (still a big regression vs k011 +0.0596). Norm-matching reduced
  the expression damage (`expr_mse` 23.7→13.0, `score_nmae` −0.745→−0.601),
  consistent with a magnitude bug, **but `pds_cosine` did NOT improve
  (0.528→0.521)**. The kill criterion (pds meaningfully above champion)
  failed. Observed direction in that implementation was no better than the
  K562 prior, and the OOD-proxy gate (cos_ood negative→positive) was again
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
  exploratory harness, the observed split by metric family was (exact values
  embargoed: `experiments/_embargoed/diagnostic-numbers.md`):
  - **Direction metrics appeared signature-bound.** A perfect delta nearly
    reached the ceiling on both discrimination and Pearson-delta metrics,
    consistent with signature limitation in that harness; leaderboard `pds`
    (~0.34) may be capped by our inability to *recover* the true delta
    (mean cos(identity,true) was low). Audited public corpora had coverage limits
    (K562-only; k020 transfer left direction flat), but exhaustion was not
    established.
  - **DE-count metrics appeared modeling-bound even with a perfect delta.**
    A perfect delta still missed the overlap/precision ceilings.
    Candidate mechanism: `de_nsig_counts_pred` was ~1.6–2× the real
    DE-gene count on both identity and true-delta arms — plausibly because
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
  densified. **cell-eval2 Gate B is validated as a directional promotion
  gate — the first proxy whose sign survived to the leaderboard.** Local
  gate internals and exact arm metrics are embargoed until Oct 22
  (`experiments/_embargoed/`, local-only). Receipts:
  `experiments/k026-consensus-w-ctr/`.
- **kytos-k027-consensus-dm — SUBMITTED 2026-09-22 (entry
  `fN4wjAp9BUEvHtGWk0az`): score_avg +0.1262, rank 308 of 1088. New
  champion.** Same consensus_w_ctr deltas as k026, generated by
  `build_prediction_dual_moment` (see `tools/run_k027_dual_moment_submit.py`).
  Component scores not displayed at capture. Receipts:
  `experiments/k027-consensus-dm/`; Gate B arm metrics and transfer
  analysis embargoed (`experiments/_embargoed/`).
- **kytos-k028-consensus-dm-pk12** (entry on leaderboard): score_avg
  +0.1239 — slight regression vs k027; pool_k=12 did not transfer.
- **kytos-k029-consensus-eb2-dm-pk12** (entry `qI6vc1sBVpE4P1llPfhu`):
  score_avg +0.1115, rank 416 — eb2 agreement shrinkage regressed
  officially. k027 remains champion.
- **kytos-k030-consensus-meanj-dm — SUBMITTED 2026-09-24 (entry
  `A1N2nYKZ07jKewReEUMp`): score_avg +0.1088, rank 442 — regression
  vs k027; k027 remains champion.** Uniform 5-source consensus mean adding
  Jurkat CRISPRi deltas (GSE249595, stim arm) to the k026 source set,
  with the champion k027 dual-moment generator config unchanged.
  Rationale: context-matched source self-evaluation showed no existing
  source predicts Jurkat-lineage responses, so the new source is the
  only real signal for the T-cell-like context. Receipts:
  `experiments/k030-consensus-meanj-dm/`; arm metrics and analysis
  embargoed (`experiments/_embargoed/`).
- **k034 final-phase readiness (2026-09-28, no submission).** Genome-wide
  delta stores for all five sources staged under `/kytos-vol/k034-final-prep/`
  (K562 9.9k, HCT116 18.3k, HEK293T 18.3k, CD4 7.3k, Jurkat 18k targets;
  QA vs panel extracts exact). Extractors now take `--targets-file` /
  `--all-source-targets` (so the Oct-22 panel is a subset, not a rescan)
  and the X-Atlas scan checkpoints/resumes after preemption. Mock D/E/F
  rehearsal passed `vcc prep` dry-run; Oct-22 checklist in
  `docs/final-phase-runbook.md`. Tools: `tools/subset_deltas_npz.py`,
  `tools/modal_k034_final_submit.py`. Receipts:
  `experiments/k034-final-rehearsal/`, `experiments/k034-genomewide-extract/`.
- **`kytos-k034-nctr-dm` submitted 2026-09-28 — +0.1178 (rank ~455),
  regression vs champion.** Single-variable ablation: champion dual-moment
  generator config but deltas = `variant_consensus_w` (uncentered; the
  `*_ctr` common-response centering removed). Officially regressed
  (−0.0084 vs k027) — consistent with Gate B's local ordering
  (centering helps, does not delete signal). **This settles the open
  final-phase recipe question: ship the centered k027 recipe blind; k027
  remains champion.** k027's per-component officials were never captured
  and the entry is purged from the API, so only the overall delta is
  verifiable; the embargoed note records the fullest comparison.
  Receipts: `experiments/k034-nctr-dm/`; analysis:
  `experiments/_embargoed/k034-nctr-nm.md`.
- **Submission protocol revised (2026-09-29, user-directed).** The +0.02
  Gate-B promotion bar is retired for signature/fusion machinery: Gate B's
  hESC-only eval demonstrably cannot arbitrate recipe choices (k030
  ordering inversion; nctr's local gain officially regressing). New rule:
  **submissions are measurement probes** — each must carry a pre-declared
  component-level prediction recorded BEFORE submit (in the run's
  embargoed note), and cadence is up to the daily cap rather than gated
  by local deltas. Gate B still runs for drift control, regression
  checks and leakage screening; it no longer vetoes machinery. Constants
  fit to validation contexts A/B/C via the board are flagged
  "context-fit" and do NOT ship blind on D/E/F unless they self-
  calibrate from control statistics. New compute host:
  `snapflip-vultr` (4 vCPU/31 GB/252 GB, no GPU) at `/opt/kytos/` —
  replaces Modal for CPU work (vcc auth + Modal volume read wired);
  SnapFlip containers under `/opt/snapflip/` are untouchable, cap our
  RSS ~24 GB. Untracked: `experiments/k030-ctxlineage/` and `logs/` stay
  out of git.
- **`kytos-k035-ctragr-dm` submitted 2026-09-30 — +0.1242 (rank ~449):
  statistical tie with champion (−0.0020), ALL pre-declared predictions
  confirmed.** Single-variable probe: k027 generator config + deltas =
  `variant_consensus_w_ctr_agr` (centered consensus + per-gene
  cross-source agreement gate, constants 0.30/0.70). Highest recorded
  `score_pds` (0.6113); mse/fid/jac flat, nmae flat-to-slightly-down.
  **RE-READ 2026-10-03 against k037's captured champion baseline: the
  "all confirmed" reading is wrong on `score_reach`** — this entry's 0.0591 is
  *below* the champion's 0.0686, not a record. The gate is a component
  reshuffle: +0.0081 pds paid back by −0.0095 reach, −0.0052 nmae, −0.0031 mse,
  −0.0021 fid (the six deltas sum to the observed −0.0020). Verdict revised:
  agreement-gate machinery does **not** transfer as a win; it stays the
  reference delta set only because pds is the channel nothing else moves.
  Local gate also showed
  uncentered+gate beats centered+gate (same trap as k034-nctr — the
  centered variant was the correct probe). Selective decorrelation
  (`_selctr`) was locally NEGATIVE alone — dropped. Gate round on the
  VPS (`gate-local-20260929-01`, tools/run_k025_gate_local.py — VPS-only,
  uncommitted there) reproduced dm_ref at float epsilon vs the Modal
  harness. Streamed submit generator `tools/run_k035_streamed_submit.py`
  (2 GB peak vs 59 GB; bit-identical X) makes full builds runnable on
  the VPS — **but `vcc prep` on the same bundle peaked >29 GB there and was
  aborted by the memory guard; packaging stays a Modal step.** Receipts:
  `experiments/k035-ctragr-dm/`; analysis:
  `experiments/_embargoed/k035-ctragr-predeclared.md` (RESULT section) and
  `experiments/_embargoed/k037-k027-rescore-predeclared.md` (RESULT section,
  champion component table).
- **`kytos-k037-k027-rescore` submitted 2026-10-03 — +0.12617 (rank 483/1299):
  byte-identical re-score of the champion; scorer/panel confirmed STABLE.**
  Not a new model — the champion's original packaged bundle
  (`/kytos-vol/k027-consensus-dm/prediction.prep.vcc`, built 2026-09-22T13:53Z,
  deltas sha `336f2cbc1d01…`, nnz 2434201087) resubmitted under a distinct
  model name to capture the six per-component officials k027 never recorded
  before its entry left the API. `score_avg` reproduced +0.1262 to Δ3e-5 across
  the 11-day gap → no drift; the rank slide is field densification only
  (1088→1299 entries). **Champion components are now the canonical baseline:
  pds 0.6032 · mse 0.0148 · nmae 0.0882 · fid −0.0188 · reach 0.0686 ·
  jac 0.00106.** k027 remains champion. The cheapest possible probe (a
  resubmit of an artifact already on disk) and it re-based five runs' worth of
  component reads. Tool: `tools/modal_k037_k027_rescore_submit.py`; receipts:
  `experiments/k037-k027-rescore/`; analysis:
  `experiments/_embargoed/k037-k027-rescore-predeclared.md`.
- **Gate-constant optimum found and axis exhausted (2026-09-30, rounds
  `gate-local-20260929-02` + `gate-local-20260930-01`, VPS):** bracketed
  the agr clip constants — tight (0.40/0.80) is the local optimum, with
  loose → std → xtight → tight ordering monotonically improving and
  xtight/tight close together; n_cells reliability weighting (vagr) helps
  at std constants but does NOT stack at tight. Exact arm averages for all
  four bracket points: `experiments/_embargoed/k025-eval2-gate/gate-local-
  {20260929-02,20260930-01}/` (local-only). The constant gain over
  confirmed `ctr_agr` is sub-resolution on the official scale — no
  standalone probe; **`consensus_w_ctr_agr_tight`
  is the new reference delta set**, stacked under the next mechanism
  change. Within-source per-sample agreement remains untested (npz
  `delta_batch` is pooled, not per-sample — needs re-extraction).
  Builder: `tools/build_consensus_deltas_v2.py`.
  **SUPERSEDED 2026-10-03 by `kytos-k038-ctragr-tight-rmass-dm` (+0.1254): the
  tight-constant "new reference delta set" is NOT a promotion — see the k038
  entry. The constants axis is closed.**
- **Round `gate-local-20260930-02` (2026-09-30):** `ctr_agr_tight_rmass`
  (gate picks genes, row-norm restores target mass) = new local best;
  gain attributed to reach/jac — the rmass hypothesis (recover nmae/mse)
  was called FALSIFIED locally. **Both of those local readings inverted
  officially — see the k038 entry below.**
  Per-sample/per-donor agreement feasibility: Jurkat
  per-channel parts exist on the Modal volume (cheap, today); X-Atlas
  per-sample needs a small Modal re-extract (~2-3h) — worthwhile, 78-116
  samples/target median is a far stronger gate term than 5-source
  agreement; CD4 per-donor does NOT exist in the publisher artifact
  (pooled across donors); K562 pooled only. Atlas h5ad on the VPS has
  48 batches — usable as an ORACLE check (does batch sign-agreement
  track true DE?) before spending Modal credits.
- **`kytos-k038-ctragr-tight-rmass-dm` submitted 2026-10-03 — +0.12544 (rank
  489/1299): second consecutive statistical tie; the agreement-gate axis is
  CLOSED.** Recipe probe (two delta variables vs k035: gate constants
  0.30/0.70→0.40/0.80 **and** the rmass row-norm restore), champion generator
  otherwise identical, deltas sha `989d1415b247…`. Best `score_pds` (0.6136),
  `score_nmae` (0.0903) and `score_jac` (0.00121) ever recorded — and the
  **lowest `score_reach`** (0.0541) of the three gate settings, so the two
  falsifiable declarations both broke, in opposite directions: reach was declared
  UP (it fell), nmae was declared explicitly-not-UP (it rose past the champion).
  **Mechanism found — the plateau explained:** along the gate axis
  (no gate → std → tight+rmass) pds and reach move monotonically *opposite*
  (0.6032→0.6113→0.6136 vs 0.0686→0.0591→0.0541). Sharpening cross-source
  agreement suppresses low-agreement genes, which are exactly the genes that
  would register as reached DE genes; the channels are equally weighted and
  reach moves harder, so every step on this axis is a tie or a loss. We have
  been re-shuffling between anti-correlated channels, not losing signal.
  Ship recipe for Oct 22 is unchanged (`consensus_w_ctr` + dual-moment
  a1.0/b0.5/pk4). Only mechanisms that add confidently-signed genes (more
  samples per source = k036; a lineage-matched second source) qualify for a
  slot; further gate-constant/shape/centering variants do not. Gate B's
  promotion ordering has now failed to transfer on four consecutive attempts —
  it is a leakage/regression/drift screen, not a judge. Tool:
  `tools/modal_k038_rmass_submit.py`; receipts:
  `experiments/k038-ctragr-tight-rmass-dm/`; analysis:
  `experiments/_embargoed/k038-ctragr-tight-rmass-predeclared.md` (RESULT).
- **Gate B rounds 11–12 (2026-09-28, no promotion candidate).**
  `gate-20260928-02` swept `bulk_amplitude` 0.5–3.0 plus eb2/uncentered
  probes; `gate-20260928-03` tested their composition. Raw
  `expr_mse` tracks `bulk_amplitude` alone and is U-shaped with a shallow
  optimum near ~0.7–1.0 — the mse channel is direction-bound (bulk-shift
  direction vs real is near-orthogonal on eval targets), same wall as
  `pds`, not a separate lever. The small positives (uncentered consensus,
  eb2) did not compose and none cleared the +0.02 local promotion bar;
  no submission spent. Champion remains `kytos-k027-consensus-dm`. Exact
  arm values: `experiments/_embargoed/k025-eval2-gate/gate-20260928-{02,03}/`.
  Infra note: pred writes are now atomic (write-then-rename) — a
  preemption-truncated h5ad previously passed the `exists()` resume check.
- **k031/k032 — data-extraction runs (2026-09-22/25), no submissions.**
  `tools/modal_k031_jurkat_extract.py` produced the Jurkat CRISPRi delta
  source consumed by k030. `tools/modal_k032_replogle_reliability.py`
  established the figshare GWPS K562 bundle (URL `35775507`) access pattern
  and per-target reliability ranking used to decide what was worth training
  on. Qualitative outcome only; exact reliability tables embargoed.
- **k033 — trained-signature track (COMPLETE 2026-09-28, negative gate
  result, no submission).** First attempt at
  a *learned* signature source rather than transplanted mean shifts.
  `tools/modal_k033_state_probe.py` established that every published Arc
  State checkpoint carries the 2,024-target essential onehot vocab and
  therefore cannot emit panel-target deltas (panel coverage 0/300 on all 24
  checkpoints), while the Replogle genome-wide Perturb-seq K562 single-cell
  bundle covers **272/300** panel targets. `tools/modal_k033_state_train.py`
  prepares that bundle as a cell-load dataset and trains a state24m-class
  model (hidden 768, `cell_set_len` 64, batch encoder) with the ~9.8k-target
  genome-wide vocab on Modal GPU; `state tx infer` then emits per-target log1p
  deltas. Stages are idempotent and resumable on the `kytos-vcc` Modal Volume
  (`prepare` / `fix` / `recompress` / `train` / `infer`), and the run chains
  itself server-side (`wait_and_train` → `train` → `infer_deltas`) so no live
  client is required. Two infrastructure blockers found and fixed, both worth
  remembering: cell-load 0.10.4 needs `obs/_index`/`var/_index` as h5py
  **datasets** (anndata writes groups), and **gzip-compressed** `.h5ad` parts
  starve the dataloader badly enough that the GPU idles — parts are stored
  uncompressed. A third blocker on the infer side: the volume sync's
  non-checkpoint size guard silently dropped the dense
  `pert_onehot_map.pt` the CLI writes pre-fit; `infer_deltas` now rebuilds it
  from `var_dims.pkl` `pert_names` (identical ordering by construction).
  Training completed the full 40k-step run; inference emitted learned deltas
  for the covered panel + paired-eval targets; the calibrator norm-matched
  them onto the consensus axis. **Gate B round 10 (`gate-20260928-01`): all
  three ST arms lost to the `dm_ref` drift control** — the learned signature
  does not recover per-target direction as well as the transplanted consensus
  mean on the measured eval targets, and no blend setting beat the reference.
  Clean negative: the sign of the verdict is unambiguous, so no submission
  slot was spent. This is implementation-specific (one model class, one
  corpus, ~40k steps) — not a class-wide falsification of trained signature
  models. Gate protocol unchanged: nothing gets a submission slot without
  beating the pinned cell-eval2 Gate B (`tools/modal_k025_eval2_gate.py`
  round 10 arms: ST-only, ST-raw, ST×consensus blend, plus a drift control).
  Exact step-rate, loss and arm numbers embargoed
  (`experiments/_embargoed/`).

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
  null calibrated on controls; borrowed K562 signatures reach roughly
  half of measured in-context transfer — **signature content is the
  quantified bottleneck**; and the precomputable transferability gate is
  **falsified** (cos(delta_k562, delta_hesc) predicts borrowed success
  only weakly). Exact diagnostic values embargoed:
  `experiments/_embargoed/diagnostic-numbers.md`.
  Diagnostics only — proxy evidence class, not a promotion gate.
  Receipts: `experiments/k022-pipeline-audit/paired47-20260921-01/`.
- Official scorer located via the VCC CLI guide: public
  `https://github.com/ArcInstitute/cell-eval2`, inspected revision
  `5e64833518a6603a0301cbe28185d49c30f4a986` (package version 0.16.0).
  (Local `.venv-eval2` deleted 2026-09-23 to save disk — rebuild with
  `python3.12 -m venv .venv-eval2 && .venv-eval2/bin/pip install
  "cell-eval2 @ git+https://github.com/ArcInstitute/cell-eval2@5e64833518a6603a0301cbe28185d49c30f4a986" "pdex==0.3.0"`;
  all real scoring runs on Modal, which pins the same revision.)
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
- Local verification (existing `.venv`, no installations):
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_prediction_parity.py tests/test_pipeline_audit.py tests/test_models.py tests/test_transfer.py`.
  Re-confirmed 2026-10-03: 43 passed in ~2s. (Historically the same suite ran
  in `.venv-science`: 39 tests initially, 21 in a later consumer-only run.)
  Ruff 0.16.4 checks pass for the consumer, audit runner and their two test
  files. Heavy runs still require external-compute/budget confirmation under
  section 6.

---

## 5. Daily workflow guardrails

- **≤2 submissions / day.** Prefer dry-runs (`vcc prep --dry-run`) before live
  `vcc submit`.
- **…and only ONE submission in flight at a time.** The site rejects a second
  create while the first is still `scoring` ("Your team already has a
  submission in progress"), so real cadence is gated by scoring latency, not the
  daily cap. Sequence probes: submit, wait for terminal, submit next.
- **Check the slot state before assuming a submission happened or a slot was
  spent:** `GET /api/cli/submissions/limits` (Bearer token from
  `~/.config/vcc/credentials.json` on the VPS) returns
  `{limit_reached, spent, limit, in_flight}`. There is no CLI command to list
  your submissions — `vcc status` needs an entry ID.
- **A Modal app that stops with no function logs did not run.** Observed
  2026-10-03: a detached submit job ended right after `Built image …`, and
  `limits` confirmed nothing reached the server (`spent 0, in_flight 0`) — no
  slot consumed. Verify via `limits` rather than re-submitting blind.
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
