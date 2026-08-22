# Observatory substantiation — claims, stats, and UI placement

Status: **ACTIVE** · Owner: udingethe · Started: **2026-08-22**

Curated evidence for hackathon jury, About page copy, and runs-index insight cards.
**Use Tier 1 (Arc official) in user-facing copy first.** Tier 2 is supporting literature.

Companion: [`competitive-landscape.md`](competitive-landscape.md) (strategy),
[`observatory.md`](observatory.md) (product).

---

## Anchor claim

> Arc asks for people who know when a model is wrong for **biological rather than
> numerical reasons** — but the public challenge surface is still scores and
> rankings. The Observatory publishes scrutiny alongside every run.

---

## Tier 1 — Arc / official (cite in UI)

| Stat | Value | Source |
|------|-------|--------|
| 2025 registrants | **5,000+** from **114 countries** | [2025 wrap-up](https://arcinstitute.org/news/virtual-cell-challenge-2025-wrap-up) |
| 2025 submissions | **1,200+** teams submitted; **300+** final | Same |
| 2026 scoring | **Six-metric aggregate** (not one score) | [VCC 2026](https://arcinstitute.org/news/virtual-cell-challenge-2026) |
| Why six metrics | *"No single metric captures model quality… narrow surface invites optimization against the metric rather than the biology"* | Same |
| 2026 task | **Zero-shot** across **six unseen cell contexts**; **no challenge training set** | Same |
| Generalist Prize | **$100k** for robust performance **across seven metrics** (2025 lesson) | [2025 wrap-up](https://arcinstitute.org/news/virtual-cell-challenge-2025-wrap-up) |
| Metric scale (2026) | Each scored metric: **0 = mean-response baseline**, **1 = replicate** | [cell-eval2 / vcc2026](https://pypi.org/project/cell-eval2/) |
| Public build window | **~78 days** (validation open Aug 20 → submission Nov 5, 2026) | Challenge timeline |
| Perturb-seq QC | ~**1,000** cells/perturbation; **>50k** UMIs/cell; **83%** cells >80% knockdown | [Behind the data](https://arcinstitute.org/news/behind-the-data-virtual-cell-challenge) |

### Approved phrases (user-facing)

- *"Six metrics because one score wasn't enough — we publish what the leaderboard can't."*
- *"5,000+ people joined VCC 2025. We publish every run for all 78 days of 2026."*
- *"Scores from cell-eval; biological audit flags are separate and reproducible."*

---

## Tier 2 — Literature (About → Sources only, or one clause max)

| Claim | Source |
|-------|--------|
| Deep perturbation models don't consistently beat linear baselines | [Nature Methods 2025](https://www.nature.com/articles/s41592-025-02772-6) |
| scFMs don't consistently beat simpler baselines under shift | [Genome Biology 2025](https://link.springer.com/article/10.1186/s13059-025-03574-x) |
| Different metrics → different rankings; global ≠ perturbation-specific | [VC benchmark 2026](https://arxiv.org/html/2604.27646v1) |
| Common metrics misrepresent performance; DL often below simple baselines | [bioRxiv 2026.02.14](https://www.biorxiv.org/content/10.64898/2026.02.14.705879v1) |
| Evaluation protocols vary → incomparable conclusions | [scPertEval](https://www.biorxiv.org/content/10.64898/2026.07.23.740433v1.full.pdf) |
| 2025 teams optimized highest-weighted metrics strategically | [BioTechGrid / Generalist Prize](https://biotechgrid.com/neurips-2025-altos-labs-wins-generalist-prize-at-arcs-virtual-cell-challenge/) |

---

## Tier 3 — k001 live case study (auto from `facts.json`)

| Field | Value | UI |
|-------|-------|-----|
| DE gene recall | 0.12 / ceiling 0.45 → **~27% of ceiling** | Run card, home proof pill |
| Pearson Δ | 0.08 / 0.31 → **~26% of ceiling** | Metric pills |
| Audit warnings | **2** (housekeeping + pathway coherence) | Confession banner, cards |
| Pre-reg hypothesis | Baseline <50% ceiling on pearson_delta | **Satisfied** at ~26% |

### Approved k001 line

> *"Run #1: ~27% of ceiling on DE gene recall — and 2 biological warnings the score never names."*

---

## UI placement map

| Location | What to show | Max density |
|----------|--------------|-------------|
| **Home** proof pill | 1 live stat + warns | 1 line |
| **Runs index** run cards | Ceiling % + audit warn count | 1 line |
| **Runs index** insight cards | Tier 1 stats until ≥4 runs | 3 cards when n=1 |
| **About** | Why + evidence strip + sources | 3 panels + `<details>` |
| **Run detail** | This run only; no literature dump | Per panel |
| **Narrative** | No abstract quotes | — |

---

## What not to claim

- We replace cell-eval or the official leaderboard
- We outperform STATE / GEARS / other predictors (predictor is early)
- Audit flags are ground truth — they are **deterministic sanity checks**, published for critique

---

## Maintenance

When k002+ lands, insight cards auto-hide as the grid fills (`4 - n` cards).
Refresh k001 percentages from `experiments/*/facts.json` if headline metrics change.