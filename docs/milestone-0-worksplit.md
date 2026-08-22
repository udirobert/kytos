# Milestone 0 — three-developer parallel work split

Status: **ACTIVE** · Owner: udingethe · Started: **2026-08-22**

How to divide **Observatory Milestone 0** (hackathon day) across three developers
working simultaneously. Split by **artifact contract** so branches rarely conflict;
integrate through `experiments/k001-mean-shift-baseline/`.

Scope reference: [`observatory.md §6`](observatory.md#6-milestone-0-scope-2026-08-22)  
Artifact contracts: [`run-protocol.md`](run-protocol.md)

---

## Kickoff (all three, ~30 min)

Agree and commit **before** branching:

1. **`experiments/k001-mean-shift-baseline/`** tree (per run protocol)
2. **`facts.json` v0 schema** — fields, paths; mock metric values OK for demo
3. **Branch names** — e.g. `m0/core`, `m0/enrich`, `m0/frontend`
4. **Integration order** — core seeds k001 → enrichers write artifacts → frontend builds `dist/`

---

## Developer A — Deterministic core (“truth layer”)

**Owns:** everything that produces numbers and flags without API calls.

| Deliverable | Paths |
|---|---|
| `facts.json` assembler | `src/kytos/eval/facts.py` (+ CLI) |
| Audit rules (≥2 deterministic) | `src/kytos/audit/rules.py`, `flags.json` writer |
| k001 seed run | `experiments/k001-mean-shift-baseline/` |
| Metrics CSVs (mock or real) | `experiments/.../metrics/*.csv` |
| Smoke tests | `tests/test_facts.py`, `tests/test_audit.py` |

**k001 seed includes:** `meta.json`, `metrics/`, `audit/flags.json`, assembled `facts.json`.

**Does not touch:** `tools/render_*`, `frontend/`.

**Done when:**

```bash
python -m kytos.eval.facts --run experiments/k001-mean-shift-baseline
```

writes valid `facts.json` with values matching committed CSVs.

### Suggested audit rules (Milestone 0)

| Rule ID | Check |
|---|---|
| `housekeeping_shift` | ACTB/GAPDH shift beyond threshold vs basal |
| `pathway_coherence` | flagged gene set fails pathway consistency |

---

## Developer B — Enrichment pipeline (“partner layer”)

**Owns:** all pre-render tools; writes only into the k001 run folder.

| Deliverable | Path | Output |
|---|---|---|
| OpenAI narrative | `tools/render_narrative.py` | `narrative/report.md` |
| Tavily literature | `tools/enrich_literature.py` | `literature/*.json` |
| fal stills | `tools/render_visuals.py` | `visual/hero.png`, `share-card.png` |
| VEED Fabric briefing | `tools/render_briefing.py` | `visual/briefing.mp4` |

**Hard rules:** read `facts.json` only; never invent metrics; degrade empty on API
failure; update `facts.json` visual paths after generation.

**Depends on A:** needs k001 + baseline `facts.json`. Can start against a
checked-in fixture until A merges.

**Does not touch:** `src/kytos/eval/`, `frontend/build.py`.

**Done when:** full enrichment chain runs against k001; committed artifacts allow
site build with zero API keys at view time.

```bash
python tools/render_narrative.py   --run experiments/k001-mean-shift-baseline
python tools/enrich_literature.py  --run experiments/k001-mean-shift-baseline
python tools/render_visuals.py     --run experiments/k001-mean-shift-baseline
python tools/render_briefing.py    --run experiments/k001-mean-shift-baseline
```

---

## Developer C — Observatory frontend (“demo layer”)

**Owns:** static site rendering committed artifacts only.

| Deliverable | Paths |
|---|---|
| Static generator | `frontend/build.py` |
| Templates + assets | `frontend/templates/`, `frontend/static/` |
| Run detail page (P0) | stage layout: strip + center + evidence rail |
| Plotly metrics charts | from `metrics/*.csv` only |
| Thin Home | mission blurb + link to k001 + VCC timeline |
| Deploy | Netlify (`netlify.toml` — auto-build on push) |

Visual spec: [`observatory.md §3`](observatory.md#3-experience-design--visual-first).

**Can start immediately** against a fixture `facts.json` (from docs or A’s branch).

**Does not touch:** `tools/`, `src/kytos/audit/`, eval assembler.

**Done when:**

```bash
python frontend/build.py --experiments experiments/ --out frontend/dist/
```

produces a run page with metrics, audit flags, narrative, literature rail, and
Fabric video embed — all from committed files.

---

## Dependency graph

```
Kickoff (facts.json v0)
    ├── Dev A: core + k001 seed
    │       ├── Dev B: enrichment (needs facts.json)
    │       └── Dev C: frontend (fixture → real facts.json)
    └── Integration: enrich → build dist → deploy → Loom
```

B and C work in parallel once the schema exists. B needs real `facts.json` before
final Fabric run; C can use fixtures until merge.

---

## Merge sequence

| Order | Owner | Merge |
|---|---|---|
| 1 | A | k001 seed + `facts.py` + audit |
| 2 | B + C | parallel (different directories) |
| 3 | Any | run enrichers → rebuild `dist/` → commit artifacts |
| 4 | Any | 2-min Loom from live URL |

**Conflict zones:** nominate one person for root `pyproject.toml` dependency adds
(A or B for eval deps; B for fal/OpenAI/Tavily client libs).

---

## Time-boxed priority (~6 h to hackathon opt-in)

If time is tight, each dev ships **one** P0 item:

| Dev | Single priority |
|---|---|
| A | k001 mock `facts.json` + 2 audit flags |
| B | `render_briefing.py` + `render_narrative.py` (Fabric = VEED hook) |
| C | **Run detail page only** — skip Home polish |

One complete run page beats three half-finished surfaces.

---

## Post–Milestone 0 ownership (same three)

| Dev | Long-running track |
|---|---|
| **A** | Data + eval — corpora, `cell-eval`, submission harness, ceiling runs |
| **B** | Layer A — gene transfer head, baselines, training |
| **C** | Layer B + Observatory ops — cell sampler, UMAP exports, deploy, digests |

Observatory maintenance stays with **C**; **A** feeds new runs into `experiments/`.

---

## Progress (2026-08-22, hackathon day)

| Dev | Status |
|---|---|
| **A** | ✅ core + k001 seed committed; 🏃 **live enrichment run in progress** — `tools/run_enrichment.sh` one-shot pipeline, `env.example`; venv unblocked (Python 3.12 + partner clients; full `uv sync` blocked on torch/3.14 wheel) |
| **B** | ✅ enrichment tools + `tools/README.md` + `obs` extra + `test_enrich.py`; ✅ deploy: Netlify config (`netlify.toml`), site verified desktop + mobile (Playwright, zero console errors), briefing autoplay — connect repo in Netlify dashboard |
| **C** | ✅ `frontend/build.py` + `frontend/observatory/` + `frontend/static/` + `netlify.toml`; 🧪 `tools/enrich_pioneer.py` (Pioneer side challenge) |
| **Shared** | ✅ ruff/format/secrets green; pre-commit passes; harness e2e tests added (`tests/test_harness.py` — 21 tests total) |

*Integration checklist: k001 folder complete → enrichment committed → `dist/` builds offline → deploy → demo script in [`observatory.md §7`](observatory.md#7-demo-script-2-minutes).*
