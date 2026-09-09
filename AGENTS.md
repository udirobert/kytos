# Kytos — Agent Operating Rules

> Last updated **2026-09-09** after merging Observatory UX pass (PR #1) and fixing pipeline determinism.

This file is the ground truth for any agent working on the Kytos 2026 Virtual
Cell Challenge repo. It overrides generic assumptions about "local dev" because
the primary dev machine is **memory- and disk-constrained**.

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
| Real control-cell resampling for 2026 panel | 360k cells × dense matrix | 32 GB RAM | VPS / rented instance |

---

## 3. Preferred external compute order

Cheapest / fastest-first for an agent asked to choose:

1. **Kaggle Notebooks** — free GPU/TPU; first stop for smoke tests and EDA on
   public corpora. Use the ratiocine two-phase pattern.
2. **Vast.ai / RunPod** — hourly rented GPU/CPU; best for bursts of `vcc prep`
   or training. Pick an instance with ≥32 GB system RAM for non-GPU work.
3. **Brev.dev** — once the challenge credits arrive; do not design around them
   until they are in the account.
4. **Monthly VPS** — only if a persistent cron or long training run is needed.

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
