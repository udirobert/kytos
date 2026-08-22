# Kytos — Code organization & stack

Started: **2026-08-22**. This is the layout and framework decision record. It
answers two questions: (1) how is the repository organized, (2) what goes in
the "backend" vs the **Observatory** frontend, and with which stacks. It is a
**proposal**, not a contract — annotate with the date you deviate and why.

See [`observatory.md`](observatory.md) for the visual build-in-public plan.

---

## 1. Principles

Drawn from `NOTES.md §4` and the existing repo:

1. **Build the surfaces that earn trust early.** The Observatory (visual
   experiment tracker + critique loop) ships **day 1** as Milestone 0 toward
   the Virtual Cell Challenge. Inference API serving (elcaro) stays post-challenge.
2. **Deterministic core, LLM narration only.** Numbers and charts come from code;
   any human-facing prose is rendered *from* a facts JSON (`matcha`), never
   independently. Partner APIs enrich around facts — they never invent metrics.
3. **Visual and engaging by design.** fal-generated hero imagery and share cards
   are first-class artifacts, not logos. The run page is the demo surface.
4. **One responsibility per package.** The backend is a single importable
   package (`src/kytos/`) split by concern, so any piece can be tested and
   swapped without entangling the rest.
5. **Provenance on everything.** Every artifact path + config + seed + code hash
   in a `meta.json` (see `docs/run-protocol.md`).
6. **Any data this project consumes is untrusted.** Parse defensively; never
   let an external file drive code execution.

---

## 2. Repository layout (monorepo, package-per-concern)

```
kytos/
├── README.md              # concise entry point → docs/  (no deep detail here)
├── docs/                  # ALL prose lives here (this repo's "knowledge base")
│   ├── observatory.md         # build-in-public surface: visual UX, partner tech
│   ├── competitive-landscape.md  # problem, evidence, wedge, adjacent projects
│   ├── milestone-0-worksplit.md  # three-dev parallel split (hackathon day)
│   ├── architecture.md        # model-stack ADR (Layer A/B, gates)
│   ├── code-organization.md   # THIS FILE
│   ├── release-infrastructure.md # GitHub / HF / Kaggle / VPS artifact map
│   ├── phase0-environment.md  # declared packages + install
│   ├── run-protocol.md        # run-IDs, meta.json, facts.json, provenance
│   └── security.md            # secrets policy + caveats
│
├── src/kytos/             # the backend — one importable package
│   ├── data/            # corpus loaders + the gene-space alignment layer
│   ├── features/        # context conditioning (basal-derived features: mean, var, rank, sparsity)
│   ├── models/          # Layer A (gene-level transfer) + Layer B (single-cell sampler)
│   ├── eval/            # cell-eval wrappers, facts.json assembly, metrics
│   ├── audit/           # biological sanity layer (deterministic rules)
│   └── serve/           # (deferred) thin API — elcaro pattern, post-challenge
│
├── frontend/             # Observatory — static site generator & design system
│   ├── build.py          # static generator → dist/
│   ├── observatory/      # Python engine, data loaders, Plotly charts, Jinja renderer
│   │   ├── templates.py  # Jinja2 environment config
│   │   └── templates/    # base.html, page layouts, component partials (matrix, journey, disclosure, agent_trace)
│   ├── static/           # CSS (glassmorphism), site.js, vessel3d.js (Three.js WebGL)
│   └── dist/             # committed or CI-built deploy artifact
│
├── tools/                # dev + enrichment tooling (16 Python scripts + 1 shell)
│   ├── scan_secrets.py   # pre-commit secrets scanner (~120 lines, pattern-based)
│   ├── render_narrative.py   # OpenAI (prod) or Venice (dev): facts → narrative/report.md
│   ├── check_narrative.py    # deterministic: digest grounding check → verification/
│   ├── enrich_literature.py  # Tavily: audit flags → literature/
│   ├── pioneer_ner.py        # Pioneer GLiNER2 biomedical entity extraction (LoRA fine-tuned)
│   ├── enrich_newsroom.py    # Tavily: audit flags → newsroom/research.json
│   ├── render_visuals.py     # fal: facts + metrics → visual/hero, share-card
│   ├── render_briefing.py    # fal veed/fabric-1.0: image + audio → visual/briefing.mp4
│   ├── render_anthem.py      # ElevenLabs Music: facts.json → sung sign-off audio
│   ├── holo_audit.py         # Holo VLM: Playwright screenshot → render verification
│   ├── planted_signal.py     # Planted-signal self-test: planted failures → audit rules
│   ├── prep_vcc2025_validation.py  # VCC 2025 validation data preparation
│   ├── build_audit_context.py      # Build audit context from prediction h5ad
│   ├── run_enrichment.sh     # one-shot: audit → facts → all enrichers → refresh
│
│   (partner keys: `.env.example` → `.env` at repo root — gitignored;
│    local narration: Venice — see docs/venice-dev.md)
│
├── submission/           # competition harness (the load-bearing contract)
│   ├── script.py         # official inputs → cell-eval AnnData
│   └── fixtures/         # smoke-test inputs + committed outputs
│
├── experiments/          # run outputs — artifacts + meta.json per run
│   └── README.md         # → points at docs/run-protocol.md
├── data/                 # corpora manifest/staging; raw/ is gitignored
├── tests/                # pytest suite
└── .pre-commit-config.yaml, .ruff.toml, .gitignore
```

**What lives where:** `submission/`, `tools/`, `experiments/`, `data/` stay
top-level (external-contract-facing). `src/kytos/` is the scientific backend;
`frontend/` is the Observatory; enrichment lives in `tools/` and writes back
into `experiments/<run-id>/`.

---

## 3. Backend — stack

The "backend" is the thing that computes. During the challenge it is the
pipeline itself; after the challenge it may become a thin API in front of a
frozen submission model. **One language, one env manager, one test runner.**

| Layer | Stack | Phase |
|---|---|---|
| Runtime / env | Python 3.14 + `uv` | now |
| Data & arrays | `numpy`, `scipy`, `pandas`, `polars`, `anndata`, `h5py/hdf5plugin` | now |
| Single-cell | `scanpy`, `scvi-tools` | now |
| Modeling | `torch` (Layer A + B) | now → Phase 2 |
| Eval | `cell-eval`, `pdex` | now |
| Tests | `pytest` | now |
| Lint/format/secrets | `ruff` + `tools/scan_secrets.py` via pre-commit | now |
| **API serving** | **FastAPI + uvicorn + pydantic** | **deferred to post-challenge** |

**Do not add** to the backend during the challenge: Docker/Kubernetes, message
queues, a database, an ORM. A `experiments/` directory plus frozen CSVs is the
durable store.

---

## 4. Observatory frontend — stack

The Observatory is the **visual, engaging** human-facing surface. It renders
from committed artifacts only; enrichment runs at build time and commits outputs.

### Pages

| Page | Layout |
|---|---|
| Home | Full-bleed 3D vessel fills viewport; headline + lede + CTA float over it with glass scrim; data readout strip; scroll hint |
| About | VCC stats, substantiation evidence strip, comparison with adjacent projects |
| Runs | Comparison matrix (cross-experiment scorecard) + card grid — severity dot + fill % badge + headline + metrics |
| Run detail | Full-bleed 3D vessel hero (min-height 100vh) with title + metric summary + data strip overlay; evidence panels flow in centered 760px column with scroll-reveal; interactive volcano plot |

### Stack

| Layer | Stack | Status |
|---|---|---|
| Static generator | Python `frontend/build.py` → HTML | shipped |
| **3D vessel** | **Three.js r169** (import map, jsDelivr CDN) — `frontend/static/vessel3d.js` | **shipped — core to UX** |
| Charts | Plotly (from committed CSVs) | shipped |
| Post-processing | UnrealBloomPass, EffectComposer (Three.js addons) | shipped |
| Narration | OpenAI (prod) or **Venice** (local dev) via `render_narrative.py` | shipped |
| Literature | Tavily via `tools/enrich_literature.py` | shipped |
| **Visuals** | **fal via `tools/render_visuals.py`** | shipped |
| Interactive SPA | React + Vite | only if a page needs it later |

**Default:** custom static generator + **real-time 3D vessel** + Plotly + fal
hero/share assets per run.

### Frontend file layout

```
frontend/
├── build.py                # static generator → dist/
├── observatory/
│   ├── render.py           # HTML rendering — home, about, runs index, run detail
│   ├── data.py             # loads facts.json, metrics, narrative, literature, NER
│   ├── charts.py           # Plotly bar chart (metrics vs ceiling)
│   ├── meta.py             # <head> tags, SEO, social, import map for Three.js
│   └── runs.py             # RunSummary dataclass, run discovery
├── static/
│   ├── vessel3d.js         # Three.js κύτος vessel — 3D scene (1162 lines)
│   ├── site.js             # Plotly init, VCC rail, copy buttons, scroll reveal, SVG fallback
│   ├── style.css           # full design system (4500 lines)
│   ├── favicon.svg          # κύτος vessel icon
│   ├── og-image.png         # social share image
│   ├── site.webmanifest     # PWA manifest
│   └── apple-touch-icon.png
└── dist/                   # built output (committed or CI-built)
```

### Partner technology map (hackathon + ongoing)

| Partner | Integration point | Hard rule |
|---|---|---|
| **OpenAI** | `tools/render_narrative.py` (prod) + TTS for briefings | Output must cite `facts.json` fields |
| **Venice** | Same script when `NARRATION_PROVIDER=venice` — **local dev only** | Private inference; see [`venice-dev.md`](venice-dev.md) |
| **Tavily** | `tools/enrich_literature.py` → `literature/*.json` | Empty on failure; never blocks build |
| **fal** | `tools/render_visuals.py` → `visual/hero.png`, `share-card.png` | Gen media for engagement; not metric source |
| **fal + VEED** | `tools/render_briefing.py` → `visual/briefing.mp4` via `veed/fabric-1.0` | Image + audio → talking video; core demo moment |
| **Three.js** | `frontend/static/vessel3d.js` — 3D vessel instrument | Renders from `facts.json` only; SVG fallback if WebGL unavailable |
| **Holo VLM** | `tools/holo_audit.py` — independent render verification | Playwright screenshots + VLM diff vs `facts.json`; degrades to skip without `HAI_API_KEY` |

Optional: Pioneer (critique classification) — post-Milestone 0.

Problem / wedge / adjacent projects: [`competitive-landscape.md`](competitive-landscape.md).

### Visual design

Quality bar: full-bleed 3D vessel hero, editorial typography, glassmorphism
evidence panels — inspired by [cell-architecture-studio](https://github.com/cclank/cell-architecture-studio)
and [plant-dna](https://github.com/thebuggeddev/plant-dna), with Kytos identity
(observatory / instrument-panel metaphor, κύτος vessel centerpiece). Spec:
[`observatory.md §3`](observatory.md#3-experience-design--visual-first).

Layout grammar: `Header · Run strip · Full-bleed vessel hero · Glass evidence column`.

### Frontend rules (hard)

1. Render **only** from `facts.json`, committed CSVs, and committed `visual/`.
   No live LLM or fal calls in the browser.
2. Pre-render enrichment; static `frontend/dist/` must build with zero API keys.
3. Every narrative sentence links to its source fact field.
4. fal / Fabric media are **first-class** — briefing on run detail, hero + share card.
5. The 3D vessel renders from the same `facts.json` data — zero API calls at view time.

---

## 5. Dependency & build hygiene

- **uv** is the single tool for env + package resolution. Declare deps in
  `pyproject.toml` (root) as the source of truth.
- **Node toolchain is absent by design** at repo root. If a page needs React,
  it gets its own `frontend/package.json` — never at root.
- Partner API keys live in env / local secrets only (see `docs/security.md`).
- Ruff + secrets scan on every commit. No CI yet — hooks are the local gate.

---

## 6. Open questions to resolve as we go

1. ~~Deploy target for `frontend/dist/`~~ → **Netlify** (`netlify.toml`)
2. MkDocs vs all-in-one Python generator for Observatory layout — decide Milestone 0.
3. fal model for hero still vs Fabric source frame (same image or separate).
4. Interactive UMAP on run detail — emit JSON from Layer B before Phase 2 ends.
5. Post-challenge serving (elcaro / x402) — decide after Nov 5.
