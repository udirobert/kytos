# Kytos (κύτος, "hollow vessel")

Predict how an **unseen cellular context** responds to CRISPRi perturbation,
from its unperturbed basal state alone. Entry for the **2026 Virtual Cell
Challenge** (Arc Institute; $100K grand prize). Deadline **Nov 5, 2026**.

We build in public via the **Kytos Observatory** — every experiment run
publishes cell-eval metrics, ceiling headroom, biological audit flags,
literature evidence, and video briefings for community scrutiny.

**Live:** [kytosapp.netlify.app](https://kytosapp.netlify.app)

## Runs

| Run | What | Data status |
|---|---|---|
| **k001** | Audit-probe — deliberately fails its own audit (ACTB shifted +2.10 log2FC) | `probe` |
| **k002** | First real run — VCC 2025 validation, 98,927 cells, 50 targets, cell-eval 0.8.2 | `real` (subsample) |
| **k003** | Sparse mean-shift baseline — VCC 2026 validation, 360k cells, 300 targets × 3 contexts, `vcc` 0.2.0 | `real` (submitted; score -0.948) |

See [`experiments/README.md`](experiments/README.md) for run details,
[`docs/k002-retro.md`](docs/k002-retro.md) for process notes, and
[`docs/k002-retro.md#k003-reality`](docs/k002-retro.md#k003-reality-2026-09-05) for
the k003 external-first compute lesson.

## Quick start

```bash
pre-commit install            # secrets + lint hooks on commit
python -m pytest             # smoke tests (89 tests)

# Submission harness
python submission/script.py --basal <basal> --targets <genes> \
  --gene-order <genelist> --out pred.h5ad --meta meta.json

# Observatory build (enrichment + static site)
cp .env.example .env          # fill partner keys (.env is gitignored)
./tools/run_enrichment.sh      # loads .env; see tools/README.md
python frontend/build.py --experiments experiments/ --out frontend/dist/
```

**Environment:** `uv sync --extra dev` — Python 3.12, arm64 venv. See
[`docs/phase0-environment.md`](docs/phase0-environment.md).

## Docs

| Doc | What it covers |
|---|---|
| [`docs/competitive-landscape.md`](docs/competitive-landscape.md) | Problem, evidence, wedge, adjacent projects |
| [`docs/architecture.md`](docs/architecture.md) | Model stack ADR: Layer A (gene transfer) + Layer B (cell sampler) |
| [`docs/observatory.md`](docs/observatory.md) | Observatory UX, partners, hackathon scope |
| [`AGENTS.md`](AGENTS.md) | Agent operating rules: compute, secrets, VCC limits |
| [`docs/milestone-0-worksplit.md`](docs/milestone-0-worksplit.md) | Three-developer parallel split |
| [`docs/code-organization.md`](docs/code-organization.md) | Repo layout, backend & frontend stack |
| [`docs/release-infrastructure.md`](docs/release-infrastructure.md) | Where artifacts live: GitHub, Hugging Face, Kaggle, VPS |
| [`docs/phase0-environment.md`](docs/phase0-environment.md) | Declared packages + install |
| [`docs/venice-dev.md`](docs/venice-dev.md) | Local dev narration via Venice AI |
| [`docs/run-protocol.md`](docs/run-protocol.md) | Run-IDs, `meta.json`, `facts.json`, provenance |
| [`docs/k002-retro.md`](docs/k002-retro.md) | Process notes from the first real cell-eval run |
| [`docs/security.md`](docs/security.md) | Secrets policy + caveats |
| [`docs/demo-script.md`](docs/demo-script.md) | 7-beat pitch script for a 2-min Loom |
| [`NOTES.md`](NOTES.md) | Task, motivation, catalog learnings |

## Layout

```
docs/            all prose (knowledge base)
src/kytos/       backend: data, features, models, eval, audit, serve
submission/      competition harness (official inputs → cell-eval AnnData)
tools/           dev tooling + Observatory enrichment scripts
experiments/     run outputs, one folder per run-id
frontend/        Observatory — static site from facts JSON + visual/
tests/           pytest suite
data/            corpora manifest/staging (raw/ gitignored)
```

## Status

Phase 0 complete: submission harness, audit rules, enrichment tools
(OpenAI, Tavily, fal, Venice, Pioneer, Holo), Observatory frontend,
trust layer (planted-signal, narrative grounding, Holo VLM audit),
CI autonomy loop, k001 + k002 runs committed.

**2026-09-05:** k003 pipeline proven: VCC 2026 `controls` downloaded, `vcc`
logged in, sparse mean-shift baseline submitted and scored (overall -0.948).
The 8 GB arm64 Mac is too small for full `vcc prep`, Atlas prep, or real
cell-distribution sampling; docs and `AGENTS.md` now mandate
**external-first compute** (VPS / Vast / RunPod / Kaggle / Brev) for heavy
work.

Next: provision a 32 GB+ worker, run a real control-cell resampling baseline,
then train a Layer A per-target model → final H5AD submission by Nov 5. See
[`docs/architecture.md §4`](docs/architecture.md#4-compute-ladder-do-not-design-around-brev)
and [`AGENTS.md`](AGENTS.md) for the compute rules.
