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
│   ├── phase0-environment.md  # declared packages + install
│   ├── run-protocol.md        # run-IDs, meta.json, facts.json, provenance
│   └── security.md            # secrets policy + caveats
│
├── src/kytos/             # the backend — one importable package
│   ├── data/            # corpus loaders + the gene-space alignment layer
│   ├── features/        # context conditioning (basal-derived features)
│   ├── models/          # Layer A (gene-level transfer) + Layer B (sampler)
│   ├── eval/            # cell-eval wrappers, facts.json assembly, metrics
│   ├── audit/           # biological sanity layer (lemma-derived)
│   └── serve/           # (deferred) thin API — elcaro pattern, post-challenge
│
├── frontend/             # Observatory — static site from facts JSON + visuals
│   ├── build.py          # static generator → dist/
│   └── dist/             # committed or CI-built deploy artifact
│
├── tools/                # dev + enrichment tooling
│   ├── scan_secrets.py
│   ├── render_narrative.py   # OpenAI: facts → narrative/report.md (+ briefing script)
│   ├── enrich_literature.py  # Tavily: audit flags → literature/
│   ├── render_visuals.py     # fal: facts + metrics → visual/hero, share-card
│   ├── render_briefing.py    # fal veed/fabric-1.0: image + audio → visual/briefing.mp4
│   ├── run_enrichment.sh     # one-shot: audit → facts → all enrichers → refresh
│   ├── enrich_pioneer.py     # (experimental) Pioneer fine-tuned narrative — side challenge
│
│   (partner keys: `.env.example` → `.env` at repo root — gitignored)
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

| Page | Content source |
|---|---|
| Home | Latest run hero (`visual/hero`), VCC timeline, build log |
| Runs | Index of `experiments/*/facts.json` — card layout |
| Run detail | Metrics (Plotly), audit flags, literature rail, narrative, provenance |
| Critique | Links to GitHub Discussions; pre-registered hypotheses per run |

### Stack

| Layer | Stack | When |
|---|---|---|
| Static generator | Python `frontend/build.py` → HTML | now |
| Charts | Plotly (from committed CSVs) | now |
| Docs prose | MkDocs Material (optional sibling site) | now |
| Narration | OpenAI via `tools/render_narrative.py` | now |
| Literature | Tavily via `tools/enrich_literature.py` | now |
| **Visuals** | **fal via `tools/render_visuals.py`** | **now — core to UX** |
| Interactive SPA | React + Vite | only if a page needs it later |

**Default:** custom static generator + Plotly + **fal hero/share assets** per run.
MkDocs for long-form ADRs; Observatory for the visual experiment experience.

### Partner technology map (hackathon + ongoing)

| Partner | Integration point | Hard rule |
|---|---|---|
| **OpenAI** | `tools/render_narrative.py` → `narrative/report.md`; TTS for briefings | Output must cite `facts.json` fields |
| **Tavily** | `tools/enrich_literature.py` → `literature/*.json` | Empty on failure; never blocks build |
| **fal** | `tools/render_visuals.py` → `visual/hero.png`, `share-card.png` | Gen media for engagement; not metric source |
| **fal + VEED** | `tools/render_briefing.py` → `visual/briefing.mp4` via `veed/fabric-1.0` | Image + audio → talking video; core demo moment |

Optional: Pioneer (critique classification), h (computer-use agents) — post-Milestone 0.

Problem / wedge / adjacent projects: [`competitive-landscape.md`](competitive-landscape.md).

### Visual design (Milestone 0)

Quality bar: immersive center stage, editorial typography, detail panels —
inspired by [cell-architecture-studio](https://github.com/cclank/cell-architecture-studio)
and [plant-dna](https://github.com/thebuggeddev/plant-dna), with Kytos identity
(observatory / instrument-panel metaphor, κύτος vessel centerpiece). Spec:
[`observatory.md §3`](observatory.md#3-experience-design--visual-first).

Layout grammar: `Header · Run strip · Stage (vessel + Fabric video) · Evidence rail`.

### Frontend rules (hard)

1. Render **only** from `facts.json`, committed CSVs, and committed `visual/`.
   No live LLM or fal calls in the browser.
2. Pre-render enrichment; static `frontend/dist/` must build with zero API keys.
3. Every narrative sentence links to its source fact field.
4. fal / Fabric media are **first-class** — briefing on run detail, hero + share card.

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
