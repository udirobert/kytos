# Kytos Observatory — build-in-public surface

Status: **ACTIVE** · Owner: udingethe · Started: **2026-08-22**

The **Observatory** is Kytos's public-facing layer: a visual, engaging experience
where experiment progress, biological audit flags, and literature context are
published for scrutiny, collaboration, and critique. It is the build-in-public
companion to our **2026 Virtual Cell Challenge** entry — not a substitute for
the prediction pipeline, but the medium through which we share it.

**Problem, evidence, and wedge:** [`competitive-landscape.md`](competitive-landscape.md)

Companion docs: [`architecture.md`](architecture.md) (model stack),
[`run-protocol.md`](run-protocol.md) (artifacts + `facts.json`),
[`code-organization.md`](code-organization.md) (repo layout + stacks).

---

## 1. Why this exists

The Virtual Cell Challenge runs for months (validation open Aug 20; final
submission Nov 5, 2026). Arc explicitly seeks people who *"know when a model is
wrong for biological rather than numerical reasons"* — yet official
infrastructure provides a **leaderboard and `cell-eval` scores**, not public
interpretability of failure modes.

We build in public:

- **Show** every run's metrics, ceiling headroom, and provenance.
- **Flag** predictions that pass cell-eval but fail biological sanity checks.
- **Ground** flags in literature — evidence, not prescription.
- **Explain** runs via auto-generated video briefings (VEED Fabric).
- **Invite** critique, replication, and collaboration before we overfit validation.

The Observatory makes that loop **visual and engaging** — not a dry CSV dump.

---

## 2. Hackathon milestone (2026-08-22)

**{Tech: Europe} × VEED Hackathon — Summer Lock-In** is today's forcing function.
We submit the Observatory as **Milestone 0** toward the Virtual Cell Challenge.

| Hackathon requirement | Observatory deliverable |
|---|---|
| Min. 3 partner technologies | OpenAI + Tavily + **fal** (incl. VEED Fabric) |
| 2-minute video demo | Live walkthrough: run page → audit → Fabric briefing |
| Public GitHub + README | This repo; partner map in README + [`code-organization.md`](code-organization.md) |
| Built at hackathon | `frontend/`, enrichment tools, k001 run page |

**Honest pitch:** the perturbation model is early; the **transparency layer**
ships today and carries through to Nov 5. See
[`competitive-landscape.md §3`](competitive-landscape.md#3-our-wedge).

### Partner roles

| Partner | Role | Catalog pattern |
|---|---|---|
| **OpenAI** | Run script + digest — **from `facts.json` only**; TTS for Fabric audio | weft / matcha |
| **Tavily** | Literature sidebar for audit-flagged genes/pathways; empty on failure | famile |
| **fal** | Hero stills, share cards, **VEED Fabric run briefings** | — |

Optional later: **Pioneer** (critique classification), **h** (computer-use agents).

### VEED Fabric (`veed/fabric-1.0` on fal)

Hosted by VEED — their API is a first-class demo moment, not an afterthought.

**Run briefing pipeline:**

```
facts.json + metrics
  → OpenAI: ~45s script (grounded, cites fields)
  → OpenAI TTS: audio track
  → fal image gen: κύτος vessel portrait (source frame)
  → fal veed/fabric-1.0: visual/briefing.mp4
  → Observatory embeds on Home + Run detail
```

Fabric turns committed experiment artifacts into **talking video explainers** —
science communication (our domain) meets video (VEED's domain). The hackathon
demo can include a Fabric-generated briefing as the centerpiece.

---

## 3. Experience design — visual first

Quality bar: immersive center stage, editorial typography, specimen/run selection,
detail panels — inspired by [cell-architecture-studio](https://github.com/cclank/cell-architecture-studio)
and [plant-dna](https://github.com/thebuggeddev/plant-dna), with our own spin.

### Design references (primitives, not clones)

| Reference | Primitive we borrow | Kytos spin |
|---|---|---|
| Cell Architecture Studio | Stage + sidebar + specimen strip; 3D center; comparison modal | **Run strip**; **vessel stage**; metrics vs **ceiling** comparison |
| Plant DNA | Full-viewport stage; mono editorial type; Three.js sculpture hero | **Observatory instrument panel**; procedural **κύτος** vessel, not DNA helix |
| Both | Detail panels, loading overlays, responsive layout | **Audit flag cards**; provenance footer as instrument readout |

**Identity:** observatory / mission-control metaphor — dark lab palette, phosphor
accents (gene-up, flag-amber, ceiling-cyan). The hollow vessel (κύτος) is the
3D centerpiece: an empty context waiting to be perturbed.

Skip for Milestone 0: gamification (XP, quizzes, flashcards) from Cell Architecture Studio.

### Pages

| Page | Purpose | Milestone 0 |
|---|---|---|
| **Home** | Mission, VCC timeline, latest run hero, Fabric briefing | Ship |
| **Runs** | Experiment index — cards, not rows | Thin / defer polish |
| **Run detail** | Core demo surface | **Ship (P0)** |
| **Critique** | Discussions + pre-registered hypotheses | Link-only |

### Run detail (the load-bearing view)

1. **Hero band** — Fabric briefing loop (or fal still) + run ID + headline metric vs ceiling.
2. **Metrics panel** — Plotly from committed CSVs only (bar vs ceiling).
3. **Audit flags** — lemma-style cards: severity, rule, genes; link to Critique.
4. **Literature rail** — Tavily for flagged entities; collapsible, labeled auxiliary.
5. **Narrative block** — OpenAI digest with **inline source links** to `facts.json`.
6. **Provenance footer** — commit, seed, hashes, reproduce command.

UMAP / distribution strip when Layer B emits them (post-Milestone 0).

Every visual and sentence traces to a committed artifact. Pre-render enrichment
at build time — static site works without API keys at view time.

---

## 4. Data contract — `facts.json`

See [`run-protocol.md`](run-protocol.md) for full schema. Observatory reads
**one file per run**:

```
experiments/<run-id>/
  meta.json
  facts.json
  metrics/
  audit/flags.json
  narrative/report.md
  literature/
  visual/
    hero.png
    share-card.png
    briefing.mp4          ← VEED Fabric output
```

`visual.briefing` in `facts.json` references `visual/briefing.mp4`.

`src/kytos/eval/` assembles `facts.json` from metrics + audit outputs.

---

## 5. Build pipeline

```bash
# 1. Run experiment → metrics + audit (deterministic core)
# 2. Assemble facts.json
python -m kytos.eval.facts --run experiments/k001-mean-shift-baseline

# 3. Enrich (commits outputs for static deploy)
python tools/render_narrative.py   --run experiments/k001-mean-shift-baseline
python tools/enrich_literature.py  --run experiments/k001-mean-shift-baseline
python tools/render_visuals.py     --run experiments/k001-mean-shift-baseline
python tools/render_briefing.py    --run experiments/k001-mean-shift-baseline

# 4. Build Observatory
python frontend/build.py --experiments experiments/ --out frontend/dist/
```

**Rules:**

1. Charts and metrics: **never** from LLM or generative APIs.
2. Enrichment failures: empty `literature/` or fallback `narrative/`; site still builds.
3. All media committed under `visual/`; referenced from `facts.json`.
4. Spend caps on partner API calls per run (poker lesson).

---

## 6. Milestone 0 scope (2026-08-22)

Parallel team split: [`milestone-0-worksplit.md`](milestone-0-worksplit.md).

Ruthless cut for hackathon deadline (19:00 opt-in):

| Priority | Ship | Defer |
|---|---|---|
| P0 | One **Run detail page** with stage layout (strip + center + rail) | Full Runs polish, Critique page |
| P0 | `facts.json` + k001 seed (mock metrics OK) | Real `cell-eval` run |
| P0 | `render_briefing.py` → `visual/briefing.mp4` | LoRA experimentation |
| P0 | `render_visuals.py` → hero still | — |
| P0 | Narrative + literature tools with cached outputs | Weekly digest |
| P0 | `frontend/build.py` → deployable `dist/` | MkDocs debate — custom HTML + Plotly |
| P0 | 2-min Loom on **live URL** | UMAP strip |

One gorgeous run page beats three half-finished pages.

### Progress (2026-08-22, end of day 1)

| Track | Status |
|---|---|
| Core (A) | ✅ `facts.json` assembler (`src/kytos/eval/facts.py`), audit rules + CLI (`src/kytos/audit/`), k001 seeded: metrics CSVs, flags, `facts.json` |
| Enrich (B) | ✅ four `tools/render_*.py` + `tools/README.md` + `obs` extra; degrade-empty verified against k001 (`narrative/report.md` fallback committed); live fal/Tavily/Fabric runs pending API keys |
| Frontend (C) | ✅ `frontend/build.py` → `dist/` (home, runs index, k001 run detail) + Netlify (`netlify.toml`) |
| Integration | ⏳ enrichment with keys → rebuild `dist/` → deploy → 2-min Loom |

### Later (Aug → Nov 2026)

- k001 through harness → `cell-eval run --ceiling`
- Each new run auto-publishes to Observatory
- Leaderboard tracker; audit rules mature; weekly digests
- Final submission: `submission/script.py` → H5AD (Nov 5)

---

## 7. Demo script (2 minutes)

Reorder for hackathon judges (VEED + fal front-loaded):

1. **10s** — Problem: models score well but fail biologically; leaderboard hides why.
2. **25s** — **Fabric briefing**: vessel explains k001; generated from `facts.json`.
3. **35s** — Metrics vs ceiling → audit flag → Tavily literature rail.
4. **25s** — OpenAI digest with source links; provenance + reproduce command.
5. **15s** — Public repo; roadmap to Nov 5; invite critique via Discussions.

Full problem/evidence talking points: [`competitive-landscape.md §6`](competitive-landscape.md#6-presentation-crib-sheet).

---

## 8. Open questions

1. ~~Deploy target for `frontend/dist/`~~ → **Netlify** (`netlify.toml`)
2. Font / palette final choice (avoid cloning Plant DNA's Space Mono verbatim)?
3. fal model for hero still vs Fabric source frame (same image or separate)?
4. Pioneer fine-tune for critique classification — post-hackathon?

*Next: implement Run detail skeleton, `facts.json` assembler, k001 seed, enrichment stubs.*
