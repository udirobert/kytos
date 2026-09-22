# Kytos (κύτος, "hollow vessel")

Predict how an **unseen cellular context** responds to CRISPRi perturbation,
from its unperturbed basal state alone. Entry for the **2026 Virtual Cell
Challenge** (Arc Institute; $100K grand prize). Deadline **Nov 5, 2026**.

We build in public via the **Kytos Observatory** — every experiment run
publishes metrics, biological audit flags, provenance, literature evidence,
and video briefings for community scrutiny.

**Live:** [kytosapp.netlify.app](https://kytosapp.netlify.app)

## Current status — 2026-09-20

- **Best recorded submission:** `kytos-k011-ds-x1p7`, overall **+0.059575**,
  observed rank **486** at publication. Ranks and thresholds are dated
  snapshots, not current standing.
- **Active plan:** validation first. Resolve feature-axis alignment, pin the
  official `cell-eval2`/`vcc2026` scoring contract, then run controlled
  baseline diagnostics before choosing the next model change.
- **Current blocker:** the k022 real-data pilot stopped at preflight because
  three Atlas labels are absent from the source gene axis (`HSPA14-1`,
  `TBCE-1`, `TMSB15B-1`). No predictions or official scores were produced.
- **Scorer:** the public `cell-eval2` `vcc2026` preset has been identified and
  documented, but not installed, integrated, or proven production-equivalent.
- **Paused:** GPU training, architecture escalation, and new leaderboard
  submissions until the data/scoring gates pass.

Start here:

- [`AGENTS.md`](AGENTS.md) — operating rules, compute limits, latest guardrails
- [`docs/vcc-two-track-strategy.md`](docs/vcc-two-track-strategy.md) — active
  validation-first strategy and decision gates
- [`docs/run-protocol.md`](docs/run-protocol.md) — required experiment record
- [`docs/architecture.md`](docs/architecture.md) — implemented architecture
  versus proposals
- [`experiments/README.md`](experiments/README.md) — immutable run registry
- [`experiments/k022-pipeline-audit/scorer_contract.json`](experiments/k022-pipeline-audit/scorer_contract.json)
  — identified official scorer contract notes

## Selected runs

| Run | What | Result/status |
|---|---|---|
| `k003` | Sparse VCC 2026 mean-shift pipeline test | submitted; score -0.948 |
| `k004-real-resampling` | Real control-cell resampling baseline | submitted; score -0.304 |
| `k004-layer-a-b` | Context-conditioned transfer + additive transport | submitted; score -0.149 |
| `k006` | Replogle K562 + Atlas prior | submitted; score -0.021 |
| `k011-x1p7` | Delta-scale transport | submitted; score +0.0596 |
| `k018` | H1 transfer + dual-moment counts for context C | submitted; score +0.0424 |
| `k020` / `k020b` | GEARS-style GNN, raw then norm-matched | submitted; scores -0.114 / -0.098 |
| `k022` | Pipeline audit | synthetic smoke passed; real pilot blocked at preflight |
| `k026` | Multi-lineage consensus deltas | submitted; score +0.0670 |
| `k027` | Consensus deltas + dual-moment generation — **champion** | submitted; score +0.1262, rank 308 |

See [`experiments/README.md`](experiments/README.md) for the full registry,
including proxy labels and interpretation caveats.

## Quick start

```bash
pre-commit install            # secrets + lint hooks on commit
python -m pytest             # smoke tests

# Submission harness
python submission/script.py --basal <basal> --targets <genes> \
  --gene-order <genelist> --out pred.h5ad --meta meta.json

# Observatory build (enrichment + static site)
cp .env.example .env          # fill partner keys (.env is gitignored)
./tools/run_enrichment.sh      # loads .env; see tools/README.md
python frontend/build.py --experiments experiments/ --out frontend/dist/
```

**Environment:** `uv sync --extra dev` — Python 3.12, arm64 venv. See
[`docs/phase0-environment.md`](docs/phase0-environment.md). Heavy VCC runs
require external compute; see [`AGENTS.md`](AGENTS.md).

## Docs

| Doc | What it covers |
|---|---|
| [`docs/vcc-two-track-strategy.md`](docs/vcc-two-track-strategy.md) | Active validation-first strategy |
| [`docs/run-protocol.md`](docs/run-protocol.md) | Run IDs, scientific record, `meta.json`, `facts.json` |
| [`docs/architecture.md`](docs/architecture.md) | Current champion, safeguards, diagnostics, proposals |
| [`experiments/README.md`](experiments/README.md) | Run registry and interpretation reset |
| [`docs/competitive-landscape.md`](docs/competitive-landscape.md) | Problem, evidence, wedge, adjacent projects |
| [`docs/observatory.md`](docs/observatory.md) | Observatory UX, partners, hackathon scope |
| [`AGENTS.md`](AGENTS.md) | Agent operating rules: compute, secrets, VCC limits |
| [`docs/milestone-0-worksplit.md`](docs/milestone-0-worksplit.md) | Historical Milestone 0 work split |
| [`docs/code-organization.md`](docs/code-organization.md) | Repo layout, backend & frontend stack |
| [`docs/release-infrastructure.md`](docs/release-infrastructure.md) | Artifact platforms and external-compute notes |
| [`docs/phase0-environment.md`](docs/phase0-environment.md) | Declared packages + install |
| [`docs/venice-dev.md`](docs/venice-dev.md) | Local dev narration via Venice AI |
| [`docs/k002-retro.md`](docs/k002-retro.md) | Process notes from the first real legacy eval run |
| [`docs/security.md`](docs/security.md) | Secrets policy + caveats |
| [`docs/demo-script.md`](docs/demo-script.md) | 7-beat pitch script for a 2-min Loom |
| [`NOTES.md`](NOTES.md) | Task, motivation, catalog learnings |
| [`docs/cleveland/`](docs/cleveland/) | **Separate** Cleveland Clinic / GQAI 2026 workstream |

## Layout

```
docs/            all prose (knowledge base); docs/cleveland/ is GQAI-only
src/kytos/       backend: data, features, models, eval, audit, serve
src/cleveland/   GQAI allostery pipeline (namespaced; uses .venv-cleveland)
submission/      competition harness (official inputs → AnnData)
tools/           dev tooling + Observatory enrichment scripts
experiments/     run outputs, one folder per run-id (cNNN-* under cleveland/)
frontend/        Observatory — static site from facts JSON + visual/
tests/           pytest suite (tests/cleveland/ for GQAI)
data/            corpora manifest/staging (raw/ gitignored; data/cleveland/raw/ too)
```
