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
  (Phase 1) / `tools/run_cleveland_c002.py` (Phase 2 CTQW).
- **Compression watch:** cardiac myosin Phase 1 Spearman ρ=0.823 is the
  tightest gate margin — keep it visible in Phase 2+ reports.
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
  477), `fid` -0.148; `nmae` began eroding (+0.008).
- `kytos-k008-kd-s2p0` (`kd_std=2.0`) scored **overall +0.0511** (rank
  462), `fid` -0.111, `nmae` +0.004 — the curve is bending near the
  Atlas global std (2.32). Scalar sweep is saturating; next lever is
  per-target spread or off-direction covariance (Layer B).

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

---

## 6. What to do when the user says "go ahead" on a heavy task

Before running anything that could take >30 minutes or use >6 GB RAM:

1. Confirm the target machine (local vs external).
2. If local, run a small dry-run first and report expected memory/time.
3. If external, ask for the host, key, or platform choice before writing
   deployment scripts.

This repo is a **competition science project**, not a local web app. The
fastest path to a better score is almost never "run it on this Mac."
