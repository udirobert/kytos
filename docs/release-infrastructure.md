# Kytos — Release infrastructure: where everything lives

Status: **PROPOSAL** · Owner: udingethe · Started: **2026-08-22**
Companion to [`code-organization.md`](code-organization.md) (repo layout) and
[`architecture.md`](architecture.md) (model stack). This doc answers: **which
artifact goes on which platform, and why** — so we never fight git for a 2 GB
matrix or lose a model to a dead laptop.

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
| `kytos/layer-a-transfer` | gene-level transfer head checkpoints | mid-Sep |
| `kytos/layer-b-sampler` | flow-matching cell sampler | early Oct |
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

---

## 4. Compute ladder (and when a VPS is worth it)

Decision: **no VPS yet.** Phase 0–1 runs on the local arm64 Mac + Kaggle free
GPU. A VPS becomes worth it when one of these is true:

1. **Layer B training at scale** (flow-matching on the full corpus) — sustained
   GPU hours that the Mac can't do and Kaggle's weekly quota can't absorb.
2. **The laptop can't be the cron** — weekly digests / enrichment that must run
   even when the Mac is closed.

When that happens, the options, cheapest first:

| Option | Fit | Notes |
|---|---|---|
| **Rented GPU by the hour** (Vast.ai / RunPod / later Brev credits) | bursty training | pay only for training; no monthly commitment |
| **VPS with 1× T4 / 16 GB** | sustained training + cron | matches the Phase 0–1 compute ladder; monthly cost |
| VPS CPU-only | cron + data staging only | if training stays on rented GPU |

**What a VPS would run (when it exists):** training jobs, the corpus on disk,
weekly digests + enrichment cron. **What it would not run:** the Observatory
(Netlify does that — no backend during the challenge) and it is never the
source of truth (GitHub/HF are). A VPS is a worker, not a store.

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

*Next: stand up the HF org + first dataset when Atlas 2025 lands; add the
Kaggle mirror + first smoke-test notebook at the same time. See
[`phase0-environment.md`](phase0-environment.md) for the install and
[`architecture.md`](architecture.md) §3 for the corpus priority order.*
