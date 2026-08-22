# Kytos — Code organization & stack

This is the layout and framework decision record. It answers two questions:
(1) how is the repository organized, (2) what goes in the "backend" vs the
"frontend", and with which stacks. It is a **proposal**, not a contract —
annotate with the date you deviate and why.

---

## 1. Principles

Drawn from `NOTES.md §4` and the existing repo:

1. **Infrastructure you defer is infrastructure you don't burn during the
   deadline.** Serving/UI (elcaro: "post-challenge, not during"), heavyweight
   frontends. Build only the surfaces you must show the competition loop now.
2. **Deterministic core, LLM narration only.** Numbers come from code; any
   human-facing prose is rendered *from* a facts JSON (`matcha`), never
   independently. This drives the frontend choice below.
3. **One responsibility per package.** The backend is a single importable
   package (`src/kytos/`) split by concern, so any piece can be tested and
   swapped without entangling the rest.
4. **Provenance on everything.** Every artifact path + config + seed + code hash
   in a `meta.json` (see `docs/run-protocol.md`).
5. **Any data this project consumes is untrusted.** Parse defensively; never
   let an external file drive code execution.

---

## 2. Repository layout (monorepo, package-per-concern)

```
kytos/
├── README.md              # concise entry point → docs/  (no deep detail here)
├── docs/                  # ALL prose lives here (this repo's "knowledge base")
│   ├── architecture.md        # model-stack ADR (Layer A/B, gates)
│   ├── code-organization.md   # THIS FILE
│   ├── phase0-environment.md  # declared packages + install
│   ├── run-protocol.md        # run-IDs, meta.json, provenance rules
│   └── security.md            # secrets policy + caveats
│
├── src/kytos/             # the backend — one importable package
│   ├── data/            # corpus loaders + the gene-space alignment layer
│   ├── features/        # context conditioning (basal-derived features)
│   ├── models/          # Layer A (gene-level transfer) + Layer B (sampler)
│   ├── eval/            # cell-eval wrappers, run-IDs, metric aggregation
│   ├── audit/           # biological sanity layer (lemma-derived)
│   └── serve/           # (deferred) thin API — elcaro pattern, post-challenge
│
├── submission/           # competition harness (the load-bearing contract)
│   ├── script.py         # official inputs → cell-eval AnnData
│   └── fixtures/         # smoke-test inputs + committed outputs
│
├── tools/                # dev tooling (secrets scanner, etc.)
├── experiments/          # run outputs — artifacts + meta.json per run
│   └── README.md         # → points at docs/run-protocol.md
├── data/                 # corpora manifest/staging; raw/ is gitignored
├── tests/                # pytest suite
├── frontend/             # (deferred) static renderer from facts JSON
└── .pre-commit-config.yaml, .ruff.toml, .gitignore
```

**What lives where vs today:** `submission/`, `tools/`, `experiments/`,
`data/` stay top-level (they are external-contract-facing, not library code).
The new `src/kytos/` package is the internal "backend" that those top-level
entrypoints import. `docs/` becomes the single home for all prose.

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

**Decision rationale — API (FastAPI) is deferred, not absent:** `elcaro` gives
the pattern (config-driven service description, request/response schemas,
x402-metered inference) and explicitly flags it as *post-challenge*. During the
competition the only "frontend" of the backend is `cell-eval` itself and the
filesystem. Standing up a server now adds deployment surface, creds, and timing
risk for zero competition value.

**Do not add** to the backend during the challenge: Docker/Kubernetes, message
queues, a database, an ORM. None help the leaderboard. A `results/` directory
plus frozen CSVs is the durable store.

---

## 4. Frontend — stack

The "frontend" is any human-facing surface. Honest scope here:

- **During the challenge**, the human-facing surfaces are: the **docs site**
  (walkthrough/ADRs), the **experiment tracker** (run results + audit report),
  and a **leaderboard tracker** (our scores vs validation over time). These are
  **internal tooling** and are all stable, low-frequency, and already structured
  as facts JSON.

**Recommendation: generated static site, not an SPA.** Build-time HTML rendered
from facts JSON (matcha: "renders from a facts JSON — nothing else"; lemma:
"generated outputs committed so the site needs no backend").

| Option | When | Why |
|---|---|---|
| **MkDocs + Material** (Markdown) | now | Painless for the heavily-prose docs; links to /static prediction HTML + charts |
| **Tiny static generator + a chart lib** (e.g. Plotly HTML, FastHTML) | now | Experiment/leaderboard pages written server-side from facts JSON |
| **React + Vite + TS** | **only if** a real interactive UI is required | Overkill for 3 low-frequency pages; adds a node toolchain + build step to a Python repo |

**Default: `MkDocs` (Material) for docs + a minimal `frontend/` that emits
static HTML/Plotly from the run's facts JSON.** If a genuine interactive need
emerges, graduate only that page to React/Vite as a **static export**.

**Frontend rules (hard):**
1. Render **only** from facts JSON / committed CSVs. No live second guesses, no
   LLM prose in the DOM.
2. No runtime backend for the frontend during the challenge — it is static, so
   it can't break the prediction path.
3. If we ever expose predictions publicly (post-challenge), that surface goes
   behind the deferred FastAPI/x402 layer; the static tracker stays internal.

---

## 5. Dependency & build hygiene

- **uv** is the single tool for env + package resolution (cell-eval documents
  `uv pip install`). Declare deps in `pyproject.toml` (root) as the source of
  truth, not a stray `requirements.txt`.
- **Node toolchain is absent by design** during the challenge (no `package.json`
  at the root). The first page that needs a real build gets its own
  `frontend/package.json`; it must never own the repo root.
- Ruff config is committed (`.ruff.toml`); secrets scan + ruff run on every
  commit. No CI yet — the hooks are the local gate.

---

## 6. Open questions to resolve as we go
1. Do we want any interactive view pre-validation (e.g. a clickable UMAP of a
   predicted distribution)? If no, MkDocs + static Plotly suffices; decide
   before Phase 2 (sampling) so Layer B can emit the needed JSON lazily.
2. Experiment-tracking volume — at ~2–5 runs/week the filesystem + meta.json is
   fine; only if this grows past ~10 runs/week consider a lightweight
   SQLite-backed index (still no server).
3. Whether post-challenge serving is in scope (elcaro), and if so whether it is
   a metered public API (x402) or a private notebook export. Decide after the
   competition.