# Kytos (κύτος, "hollow vessel")

Predict how an **unseen cellular context** responds to CRISPRi perturbation,
from its unperturbed basal state alone. Entry for the **2026 Virtual Cell
Challenge** (Arc Institute; NVIDIA, 10x Genomics, Ultima Genomics; $100K grand
prize). Deadline **Nov 5, 2026 23:59 UTC**; test set releases **Oct 22, 2026**.

**Started 2026-08-22.** We build in public via the **Kytos Observatory** — a
visual accountability layer for experiment progress, biological audit flags,
literature context, and video briefings ([`docs/observatory.md`](docs/observatory.md)).

This README is the entry point. **All prose lives in [`docs/`](docs/)**.

## Problem and wedge

Virtual cell competitions score 18,000-dimensional predictions on a live
leaderboard — but **no public layer shows when a model is wrong for biological
reasons** rather than numerical ones. Arc's 2026 challenge expanded to six
metrics because narrow scoring invites optimization against the metric, not the
biology.

**Kytos Observatory** is our answer: every experiment run publishes
`cell-eval` metrics, ceiling headroom, deterministic audit flags, literature
evidence, provenance, and VEED Fabric video briefings — so failure modes are
visible *during* the 78-day competition, not only at the end.

The perturbation **predictor** is the Nov 5 goal; the **Observatory** ships
first (hackathon Milestone 0, 2026-08-22). Full research and demarcation:
[`docs/competitive-landscape.md`](docs/competitive-landscape.md).

## Docs (start here)

| Doc | What it's for |
|---|---|
| [`docs/competitive-landscape.md`](docs/competitive-landscape.md) | **problem, evidence, wedge, adjacent projects** — pitch foundation |
| [`docs/observatory.md`](docs/observatory.md) | build-in-public surface: UX, partners, Fabric, hackathon scope |
| [`docs/milestone-0-worksplit.md`](docs/milestone-0-worksplit.md) | three-developer parallel split for Milestone 0 |
| [`docs/architecture.md`](docs/architecture.md) | model-stack ADR: Layer A (gene transfer) + Layer B (cell sampler), gates |
| [`docs/code-organization.md`](docs/code-organization.md) | repo layout, backend & Observatory frontend stack |
| [`docs/phase0-environment.md`](docs/phase0-environment.md) | declared packages + install (`uv`) |
| [`docs/venice-dev.md`](docs/venice-dev.md) | **local dev narration** — Venice AI (privacy, env, vs OpenAI prod) |
| [`docs/run-protocol.md`](docs/run-protocol.md) | experiment run-IDs, `meta.json`, `facts.json`, provenance rules |
| [`docs/security.md`](docs/security.md) | secrets policy + caveats |
| [`NOTES.md`](NOTES.md) | task, motivation, catalog learnings |

## Partner technologies

Used in the Observatory enrichment pipeline (hackathon: min. 3 required).
Confirm usage in submission materials.

| Partner | Script | Output | Role |
|---|---|---|---|
| **OpenAI** | `tools/render_narrative.py`, TTS in `render_briefing.py` | `narrative/report.md`, briefing audio | Grounded run digest + Fabric voice (hackathon / prod) |
| **Venice** | same script when `NARRATION_PROVIDER=venice` | `narrative/report.md` | **Local dev only** — private narration without burning OpenAI credits ([`docs/venice-dev.md`](docs/venice-dev.md)) |
| **Tavily** | `tools/enrich_literature.py` | `literature/*.json` | Evidence for audit-flagged genes (degrades empty) |
| **fal** | `tools/render_visuals.py`, `tools/render_briefing.py` | `visual/*` | Hero stills; **VEED Fabric** (`veed/fabric-1.0`) run briefings |

Metrics and charts come **only** from committed CSVs — never from LLM or gen-media APIs.

## Layout at a glance

```
docs/            all prose (knowledge base)
src/kytos/       backend package: data, features, models, eval, audit, serve
submission/      competition harness (official inputs → cell-eval AnnData)
tools/           dev tooling + Observatory enrichment scripts
experiments/     run outputs, one folder per run-id
data/            corpora manifest/staging (raw/ gitignored)
tests/           pytest suite
frontend/        Observatory — static site from facts JSON + visual/
```

## Quick start

```bash
pre-commit install            # secrets + lint hooks on commit
python -m pytest              # smoke tests
python submission/script.py --basal <basal> --targets <genes> \
  --gene-order <genelist> --out pred.h5ad --meta meta.json
```

Env note: the heavy stack (torch/scanpy/anndata/cell-eval) targets **Python
3.12** — 3.14 has no torch wheel. The `.venv` already holds the Observatory
partner clients (see [`docs/phase0-environment.md`](docs/phase0-environment.md)).

Observatory build (enrichment + static site — see [`docs/observatory.md`](docs/observatory.md)):

```bash
cp .env.example .env          # fill partner keys (.env is gitignored)
./tools/run_enrichment.sh     # loads .env; see tools/README.md
python frontend/build.py --experiments experiments/ --out frontend/dist/
```

Every commit is gated by a **deterministic, offline** secrets scan + `ruff`
lint + `ruff` format (see [`docs/security.md`](docs/security.md)).

## Status (Phase 0 — updated 2026-08-22)

- [x] Notes reviewed, stack reasoned (architecture ADR)
- [x] Problem / wedge / competitive landscape documented
- [x] Submission harness contract drafted + running (degrades with no deps) — e2e shape tests lock the groups-vs-X contract ([tests/test_harness.py](tests/test_harness.py))
- [x] Repo organized: package-per-concern backend, consolidated `docs/`
- [x] Milestone 0 worksplit agreed — three-dev parallel build ([docs/milestone-0-worksplit.md](docs/milestone-0-worksplit.md))
- [x] **k001 seeded (Dev A)**: `facts.json` assembler, audit rules (`housekeeping_shift`, `pathway_coherence`), metrics + ceiling CSVs, committed run artifacts
- [x] **Enrichment tools (Dev B)**: OpenAI narrative (+ deterministic fallback), Tavily literature, fal visuals, VEED Fabric briefing — degrade-empty verified against k001; one-shot `tools/run_enrichment.sh`; **live API run in progress** ([tools/README.md](tools/README.md))
- [x] **Observatory frontend (Dev C)**: `frontend/build.py` → `dist/` (home, runs index, k001 run page); Playwright-verified desktop + mobile, zero console errors; briefing video autoplay
- [x] **Deploy**: [kytosapp.netlify.app](https://kytosapp.netlify.app) via Netlify ([`netlify.toml`](netlify.toml)) — auto-builds `frontend/dist/` on push
- [ ] Integration: real enrichment artifacts → rebuilt `dist/` → redeploy → 2-min Loom
- [ ] Install `cell-eval` + `anndata` (uv, **Python 3.12**) → H5AD write path
- [ ] k001 through `cell-eval run --ceiling` — real metrics replace mock CSVs

## Open decisions

See [`docs/architecture.md §7`](docs/architecture.md): Gate 1 (six-metric
aggregate), Gate 2 (Layer A formulation), Gate 3 (counts-vs-log1p encoding),
Gate 4 (public-overlap of unseen lines).
