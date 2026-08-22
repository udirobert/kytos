# Kytos — competitive landscape, problem, and wedge

Status: **ACTIVE** · Owner: udingethe · Started: **2026-08-22**

This document grounds the project before we build: what problem we solve, why
it is substantiated, who else touches adjacent space, and where Kytos is
differentiated. Use it for hackathon jury Q&A and pitch slides.

Companion docs: [`observatory.md`](observatory.md) (what we ship),
[`architecture.md`](architecture.md) (prediction stack ADR).

---

## 1. Problem statement

> **Virtual cell competitions produce leaderboard scores for 18,000-dimensional
> predictions, but no public way to see when a model is wrong for biological
> reasons.** Models can climb metrics while shifting housekeeping genes, breaking
> pathway coherence, or producing geometrically incoherent states — and the
> community often only discovers this after the fact, if at all.

### Who feels the pain

| Stakeholder | Pain |
|---|---|
| **Competition participants** | Hard to tell if leaderboard gains reflect biology or metric gaming |
| **Computational biologists / reviewers** | Need interpretable failure modes, not a single aggregate score |
| **The field** | Long competitions (Aug–Nov) reward opaque iteration unless scrutiny is public |

### What official infrastructure provides today

| Resource | Provides | Does *not* provide |
|---|---|---|
| [Virtual Cell Challenge](https://virtualcellchallenge.org/) | Leaderboard, submission portal | Biological audit, build log, public interpretability |
| [Arc `cell-eval`](https://github.com/ArcInstitute/cell-eval) | Six-metric scoring, ceiling analysis | Plausibility flags separate from score |
| VCC participant repos (e.g. [STATE](https://github.com/ArcInstitute/state), [vcc-latent-space](https://github.com/rcurrie/vcc-latent-space)) | Prediction pipelines | Public accountability layer for the competition |

**Kytos does not replace any of the above.** We consume `cell-eval` and publish
everything else the leaderboard cannot show.

---

## 2. Evidence the problem is real

### Arc Institute (primary — cite in presentations)

From the [2026 VCC announcement](https://arcinstitute.org/news/virtual-cell-challenge-2026) (Aug 20, 2026):

> *"Last year showed that no single metric captures model quality, and that a
> scoring function with a narrow surface invites optimization against the metric
> rather than the biology."*

2026 final ranking uses an **aggregate of six metrics** specifically because of
this. From the same post, on who should enter:

> *"Computational biologists… who know when a model is wrong for **biological
> rather than numerical reasons**."*

From the [2025 wrap-up](https://arcinstitute.org/news/virtual-cell-challenge-2025-wrap-up):

> *"No single metric captures 'model quality'… optimizing one metric sometimes
> came at the cost of others."*

Arc added a **Generalist Prize** (Altos Labs) for robust performance across seven
metrics — an explicit response to single-metric optimization in 2025.

### VCC 2025 — metric optimization in practice

Coverage of the Generalist Prize ([BioTechGrid](https://biotechgrid.com/neurips-2025-altos-labs-wins-generalist-prize-at-arcs-virtual-cell-challenge/)):

> *"MAE was no longer influencing optimization… many top performers strategically
> focused their efforts on PDS and DES… without accounting for all metrics."*

Winning approaches included **strategic optimization for highest-weighted
metrics** (Arc wrap-up, community writeups). Rational behavior — and exactly why
scrutiny beyond the scoreboard matters.

### Peer-reviewed and preprint literature

| Source | Relevant claim |
|---|---|
| [Ahlmann-Eltze et al., *Nature Methods* 2025](https://www.nature.com/articles/s41592-025-02772-6) | Deep-learning perturbation models **do not yet outperform simple linear baselines** despite heavy compute |
| [Kedzierska et al., *Genome Biology* 2025](https://link.springer.com/article/10.1186/s13059-025-03574-x) | Zero-shot scFMs **don't consistently beat simpler baselines**; fine-tuning hides vulnerabilities |
| [PertEval-scFM (ICML 2025)](https://proceedings.mlr.press/v267/wenteler25a.html) | scFM embeddings offer **limited improvement under distribution shift** — the 2026 zero-shot setting |
| [Geometric coherence (2026)](https://arxiv.org/html/2604.16642v1) | High predicted shift + low stability → **"hallucinatory intermediate"** — quality signal beyond leaderboard metrics |
| [scPertEval preprint (2026)](https://www.biorxiv.org/content/10.64898/2026.07.23.740433v1.full.pdf) | Inconsistent evaluation protocols → **incomparable benchmark conclusions** |

### Why 2026 makes the gap worse

- **Zero-shot across six unseen cell contexts** — harder to interpret than 2025's single-context task
- **No challenge training set** — more room for models that transfer numerically but not biologically
- **Live leaderboard for ~78 days** (Aug 20 → Nov 5) — long window where public scrutiny should run *during* the competition, not only at the end

---

## 3. Our wedge

### One sentence

> **Kytos Observatory is the public accountability layer for Virtual Cell
> Challenge experiments** — every run publishes metrics, ceiling headroom,
> biological audit flags, literature evidence, provenance, and video briefings,
> so failure modes are visible while the competition is still running.

### What Kytos is

| Layer | Role |
|---|---|
| **Predictor** (Nov 5 goal) | Zero-shot perturbation model via `submission/script.py` |
| **Observatory** (ships first) | Visual build-in-public surface for experiment scrutiny |
| **Audit layer** | Deterministic biological sanity rules *separate from* `cell-eval` six metrics |

### What Kytos is not

| Not… | Because… |
|---|---|
| Another perturbation predictor | Crowded field (STATE, GEARS, thousands of VCC registrants in 2025) |
| A replacement for `cell-eval` | Official metrics stay source of truth; we add interpretability |
| BioSurface / karyon | They audit analysis bundles or tool outputs post hoc; we audit **our competition runs** in a **public, longitudinal** loop |
| OpenLab ResearchBook / Researka | They scrutinize research-agent **claims**; we scrutinize **ML experiment artifacts** tied to a live benchmark |
| Generic experiment tracking (W&B, MLflow) | No biological sanity rules, no public critique contract, no competition-specific `facts.json` |

### Unique combination (the moat)

No surveyed project combines all of:

1. `cell-eval` metrics + ceiling headroom (official numbers)
2. Biological audit flags (lemma-inspired, **separate from score**)
3. `facts.json` provenance contract (deterministic core)
4. Public Observatory UX (visual, engaging)
5. Literature grounding (Tavily)
6. Video run briefings (VEED Fabric via fal)
7. Build-in-public over the full Aug–Nov 2026 competition window

---

## 4. Adjacent projects (partial overlap only)

| Project | Overlap | Differentiation |
|---|---|---|
| [**BioSurface**](https://github.com/mrothroc/biosurface) | Deterministic audit of perturbation/scRNA claims | Post-hoc analysis bundles; not VCC companion or public build log |
| [**karyon**](https://github.com/Curtisflo/karyon) | Named-reason QC for bio-AI outputs | Qualification gate; no public run pages |
| [**PerturbGuard**](https://pypi.org/project/perturbguard/) | Benchmark / split validity | Audits **datasets**, not predictions that score well |
| [**PerturbCheck**](https://clawrxiv.io/abs/2605.02300) | Replicate-robust perturbation claim audit | Experimental **claims**, not in-silico predictions |
| [**OpenLab ResearchBook**](https://github.com/SimplyLiz/OpenLab) | Public feed, challenge/fork threads | Cancer gene dossiers, not perturbation ML runs |
| [**Researka**](https://researka.org/) | Public audit for research agents | Citation/claim verification, not experiment tracking |
| **VCC participant repos** | Same competition | Ship predictors, not transparency layer |

**Research conclusion (2026-08-22):** Pieces exist in isolation. The integrated
Observatory product for VCC does not appear to exist.

---

## 5. Honest risks (acknowledge in pitch)

1. **Arc is partially addressing metric gaming** with six metrics + ceiling.
   Our wedge: *six metrics reduce gaming; they don't make failure modes legible
   to biologists.*

2. **BioSurface is philosophically closest.** We differentiate on:
   competition-specific, public, longitudinal, enriched with video + literature,
   tied to `facts.json` + reproduce commands.

3. **Audit rules must be real.** Hand-wavy flags = theater. Milestone 0 ships
   at least 2–3 deterministic rules (e.g. housekeeping shift, pathway coherence)
   with committed outputs.

4. **"Build in public" is not unique as a concept.** Unique is applying it to
   **this competition with this artifact contract** over 78 days.

---

## 6. Presentation crib sheet

**Hook:** Arc says models can be wrong for biological rather than numerical
reasons — but the leaderboard only shows numbers.

**Evidence:** 2025 Generalist Prize; six-metric aggregate in 2026; Nature Methods
baseline paper.

**Gap:** Scores without scrutiny for 18,000-dimensional predictions over 78 days.

**Solution:** Kytos Observatory — metrics + audit + literature + provenance +
Fabric briefings.

**Honest scope:** Predictor is early (Nov 5); transparency layer ships today and
carries through the competition.

**Ask:** Critique our audit rules and pre-registered hypotheses via Discussions.

---

*Next: implement per [`observatory.md`](observatory.md) Milestone 0 scope.*
