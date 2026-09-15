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
| **k004-resample** | Real control-cell resampling baseline — VCC 2026 validation, 360k cells, 300 targets × 3 contexts, `vcc` 0.2.0 on Modal 64 GiB | `real` (submitted; score -0.304, rank 765) |
| **k004-layer-a-b** | Context-conditioned gene transfer + log1p transport (Layer A/B) — first target-specific Kytos model on Modal 64 GiB | `real` (submitted; score -0.149, rank 656) |
| **k005-atlas-prior** | 2025 Atlas perturbation prior + log1p transport — real per-target signatures where the 2025 validation overlaps (4/300 targets) | `real` (built; `.vcc` on Modal Volume, not yet submitted) |
| **k006-replogle-prior** | Replogle K562 GWPS + 2025 Atlas prior + log1p transport — real signatures for 272/300 targets | `real` (submitted; score -0.021, rank 534) |

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
| [`docs/cleveland/`](docs/cleveland/) | **Separate** Cleveland Clinic / GQAI 2026 workstream (allostery CTQW; not VCC) |

## Layout

```
docs/            all prose (knowledge base); docs/cleveland/ is GQAI-only
src/kytos/       backend: data, features, models, eval, audit, serve
src/cleveland/   GQAI allostery pipeline (namespaced; uses .venv-cleveland)
submission/      competition harness (official inputs → cell-eval AnnData)
tools/           dev tooling + Observatory enrichment scripts
experiments/     run outputs, one folder per run-id (cNNN-* under cleveland/)
frontend/        Observatory — static site from facts JSON + visual/
tests/           pytest suite (tests/cleveland/ for GQAI)
data/            corpora manifest/staging (raw/ gitignored; data/cleveland/raw/ too)
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

**2026-09-11:** k004 Layer A/B on Modal: context-conditioned gene transfer
(ContextConditionedTransfer) + log1p transport (AdditiveTransportSampler) produced
a target-specific 360k × 18,533 prediction. `vcc prep` and `vcc submit` passed.
Score: **overall -0.149** (rank 656), improving on k004-resample (-0.304) and
k003 (-0.948). `pds` is now positive (0.0019), confirming the target-specific
knockdown signal is detectable.

**2026-09-11:** k005 Atlas-prior on Modal: downloaded the 2025 VCC validation
(6.9 GB, 50 targets), computed per-target log1p mean-shift signatures, and
applied them to the 2026 panel. `vcc prep` passed and the `.vcc` is persisted on
the `kytos-vcc` Modal Volume. **Only 4/300 2026 targets overlap the 2025
validation**, so the model is effectively k004-layer-a-b plus four real
signatures; a larger perturbation atlas (e.g., full Arc Perturb-seq / Replogle)
is needed to cover the 2026 panel.

**2026-09-11:** k006 Replogle-prior on Modal: combined the 2025 Atlas (50
targets) with the Replogle K562 genome-wide Perturb-seq bulk (9,866 targets).
This gave real perturbation signatures for **272/300** 2026 targets. The model
was submitted and scored **overall -0.021** (rank 534), a large improvement
over k004-layer-a-b (-0.149). `pds` improved to **0.265** and `nmae` to
**-0.074**, confirming that real perturbation signatures drive the score.

Next: improve the remaining 28 fallback targets (e.g., other CRISPRi datasets),
tune `noise_scale` / `knockdown_efficiency`, and consider a learned Layer A
that generalizes from the 2025/Replogle data to unseen contexts.
See [`docs/architecture.md §4`](docs/architecture.md#4-compute-ladder-do-not-design-around-brev)
and [`AGENTS.md`](AGENTS.md) for compute rules.
