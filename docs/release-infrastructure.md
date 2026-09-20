# Kytos — Release infrastructure: where everything lives

Status: **PROPOSAL / HISTORICAL** · Owner: udingethe · Updated: **2026-09-20**
Companion to [`code-organization.md`](code-organization.md) (repo layout) and
[`architecture.md`](architecture.md) (implemented stack versus proposals).
This doc answers: **which artifact goes on which platform, and why** — so we
never fight git for a 2 GB matrix or lose a model to a dead laptop.

References to future Layer A/B weights or flow-matching training are proposed
artifacts, not active work. Current sequencing is governed by
[`vcc-two-track-strategy.md`](vcc-two-track-strategy.md) (“VCC strategy —
validation first”).

The rule of thumb that decides everything:

> **Code changes often and needs review → git. Datasets and weights are large,
> immutable, and versioned → a hub. Compute is where the work runs, not where
> it's stored. Secrets never ship.**

---

## 1. The artifact → home map

| Artifact | Home | Why |
|---|---|---|
| Source code (`src/`, `submission/`, `tools/`, `frontend/`, `tests/`) | **GitHub** (this repo) | review, history, PRs |
| Docs / ADRs / run protocol | **GitHub** (`docs/`) | prose lives with code |
| Small run artifacts (CSVs, JSON, facts, small H5AD) | **GitHub** (`experiments/<run>/`, committed) | provenance + Observatory builds from them |
| **Processed corpora** (Atlas 2025, Replogle/Norman, gene-space alignment) | **Hugging Face Datasets** (primary) + **Kaggle Datasets** (mirror) | large, immutable, versioned, viewable |
| **Model weights** (Layer A, Layer B, Pioneer fine-tunes) | **Hugging Face Models** | binary, versioned, the standard for the VCC community |
| Synthetic training data (facts→digest pairs, NER examples) | **Hugging Face Datasets** | regenerable but versioned for reproducibility |
| **Compute** (training, long jobs) | local (arm64 Mac) → **Kaggle GPU** (free, smoke tests) → **VPS / rented GPU** (Phase 2+) | see §4 |
| Deployed surfaces | **Netlify** (Observatory) · **HF Spaces** (optional model demo, later) | static + no backend during challenge |
| Secrets / API keys | env vars only (`.env`, gitignored) | never on any of the above |
| Raw downloads (`data/raw/`) | local + VPS disk (gitignored) | regenerable, not an artifact |

**Never in git:** model weights, raw corpora, anything > ~50 MB per file, `.env`.
If it's big or binary, it's on a hub; git keeps a manifest + provenance.

---

## 2. Hugging Face — the canonical hub

One org (`kytos` — or your user id if you prefer) with three namespaces.

### Datasets (`kytos/<corpus>`)

| Dataset | Contents | Role |
|---|---|---|
| `kytos/atlas-2025-processed` | Atlas 2025 aligned to `expected_genelist` | in-distribution assay prior; baseline validation |
| `kytos/crispri-multiline` | Replogle / Nadig / Norman-style CRISPRi screens | **cross-context supervision** — trains Layer A transfer |
| `kytos/gene-space-alignment` | canonical gene namespace + mapping version | the alignment layer, one artifact |
| `kytos/facts-digest-pairs` | synthetic `facts.json` → `report.md` pairs | Pioneer narrative fine-tune (side challenge) |
| `kytos/k001-baseline` | first real baseline outputs (`results.csv`, `ceiling_results.csv`) | public reproducibility of run #1 |

Every dataset card carries: **source URL, license, processing script + commit
hash, schema, and the reproduce command** (the lemma/orbura provenance habit).

### Models (`kytos/<component>`)

| Model | Contents | When |
|---|---|---|
| `kytos/layer-a-transfer` | proposed gene-level transfer head checkpoints | only if a gated model ships |
| `kytos/layer-b-sampler` | proposed conditional cell sampler weights | only if a gated model ships |
| `kytos/pioneer-narrative` | fine-tuned facts→digest model | hackathon (side challenge) |

Every model card carries: **training data, eval numbers vs the mean-shift
baseline (measurable % improvement), license, reproduce command** — the orbura
release discipline, verbatim.

### Spaces (optional, later)
A "predict a perturbation" interactive demo once Layer A/B exist. The
Observatory is the primary demo; a Space is a model-level bonus, not required.

**Gate:** check the **Arc Atlas license** before publishing anything derived
from it — if it's competition-only, gate the dataset (HF supports gated
access) or keep it private and publish only our processed/derived artifacts.

---

## 3. Kaggle — discovery + free compute

Secondary to HF for versioning; primary for two things:

1. **Datasets** — mirror the public corpora we consume (Replogle, Norman, …)
   and our processed versions under `kytos/<name>`. Kaggle is where the bio +
   competition community browses; it's also how the corpus gets pulled directly
   into a notebook.
2. **Notebooks** — the **ratiocine two-phase pattern**: validate a data format
   or a small model on Kaggle's **free GPU** (Phase 1, ~minutes/run) before
   committing local or paid compute (Phase 2). EDA + smoke tests live here.

Kaggle never holds the canonical version — HF does. Kaggle is the mirror +
the free-GPU test bench.

**Live (2026-09-10):** **Dataset** `udingethe/vcc2026-controls` (632 MB, private;
`context_A/B/C.h5ad` 215/201/216 MB + `gene_names.csv`/`pert_counts.csv`/`manifest.json`;
via `tools/kaggle_bundle.py`) + **Notebook** `udingethe/kytos-k004-kaggle-smoke`
(v2, CPU, `enable_internet=true`, `dataset_sources=["udingethe/vcc2026-controls"]`)
smoke-tests real control-cell resampling vs `ContextConditionedTransfer` +
`AdditiveTransportSampler` (`notebooks/kaggle_k004_smoke.ipynb` / `.py`,
`notebooks/README.md`). See `experiments/README.md` k004.

---

## 4. Compute ladder (and when a VPS is worth it)

**Updated 2026-09-10.** The primary dev machine has **8 GB RAM** (arm64 Mac),
so the default is now **external first**: the Mac is only for docs, small
sparse baselines, and `vcc prep --dry-run` on subsets. Anything that touches the
full 2026 panel, the 2025 Atlas, or a real cell-distribution sampler runs on a
machine with **≥32 GB RAM** (or a GPU instance).

A VPS / rented instance is worth it for:

1. **Full `vcc prep` on a real 2026 panel** — peak ~28 GB; cannot fit locally.
2. **2025 Atlas download + prep** — 6.9 GB source and ~13 GB peak scratch.
3. **Layer B training at scale** (flow-matching on the full corpus) — sustained
   GPU hours that the Mac can't do and Kaggle's weekly quota can't absorb.
4. **The laptop can't be the cron** — weekly digests / enrichment that must run
   even when the Mac is closed.

Options, cheapest first:

| Option | Fit | Notes |
|---|---|---|
| **Kaggle free GPU/CPU** | smoke tests, EDA, small notebooks | weekly quota; use the ratiocine two-phase pattern first — live: `vcc2026-controls` dataset + `k004` notebook (10–20 targets × 3 contexts) |
| **Rented CPU/GPU by the hour** (Vast.ai / RunPod) | full `vcc prep`, bursts of training | pick ≥32 GB system RAM for `vcc prep`; use only after the active strategy gates approve the run |
| **VPS with 1× T4 / 32 GB+** | sustained training + cron | only if a long-running worker is needed |

**What a VPS / rented instance runs:** heavy data prep, `vcc prep`, scorer/eval
runs, training. **What it does not run:** the Observatory (Netlify does that —
no backend during the challenge), and it is never the source of truth (GitHub/HF
are). External compute is a worker, not a store.

---

## 5. Data flow (how the pieces connect)

```
public sources (Atlas 2025, Replogle, Norman)
      │  src/kytos/data/ loader + gene-space alignment
      ▼
data/raw/ (local, gitignored) ──process──▶ HF Datasets (canonical, versioned)
      │                                        │
      │                                        │  kaggle datasets (mirror)
      │                                        ▼
      │                              training: local Mac → Kaggle GPU → VPS
      │                                        │
      │                                        ▼
      │                                 HF Models (weights + cards)
      │                                        │
      ▼                                        ▼
experiments/<run>/ (small CSVs/JSON → GitHub)  └──▶ reproducibility (reproduce cmd)
      │
      ▼
Observatory (frontend/build.py → Netlify)
```

Every arrow is a **script + provenance**, never a manual copy: the processing
script and its commit hash ride along in each dataset/model card and each
`experiments/<run>/meta.json`.

---

## 6. Naming & release conventions

- **GitHub:** single monorepo `udirobert/kytos` — no split repos during the
  challenge. Keep it that way until something is genuinely independent.
- **HF:** org `kytos`; datasets `kytos/<corpus>`; models `kytos/<component>`.
  Version datasets with a `-v<N>` suffix when the schema changes.
- **Kaggle:** user namespace; datasets `kytos/<corpus>` mirroring HF.
- **Every release** (orbura): adapted dataset + weights + **measurable %
  improvement over baseline on a held-out set**. No release without the number.

## 7. Hard rules

1. Weights never in git — HF only.
2. Big matrices never in git — HF/Kaggle only; `experiments/` stays small.
3. Every hub artifact has a card: source, license, processing commit, reproduce command.
4. Raw downloads are regenerable — never an artifact, never committed.
5. Challenge data: check license before publishing; gate if competition-only.
6. Kaggle is a mirror + test bench, HF is canonical.
7. VPS (when it arrives) is a worker — never the source of truth, never hosting.
8. Secrets stay in env vars on every platform.

---

*Status 2026-09-20: Kaggle Dataset `udingethe/vcc2026-controls` + Notebook `udingethe/kytos-k004-kaggle-smoke` v2 remain historical smoke artifacts. Current sequencing is validation-first: resolve the k022 source-axis mismatch, pin the official `cell-eval2`/`vcc2026` scoring contract, then run controlled diagnostics. No new heavyweight training run is justified by this infrastructure document. See [`notebooks/README.md`](../notebooks/README.md), [`architecture.md`](architecture.md), and [`vcc-two-track-strategy.md`](vcc-two-track-strategy.md).*
