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
| **OpenAI** | Run script + digest (prod) — **from `facts.json` only**; TTS for Fabric audio | weft / matcha |
| **Venice** | Same narration path for **local dev** — private inference, saves hackathon OpenAI credits | — ([`venice-dev.md`](venice-dev.md)) |
| **Tavily** | Literature sidebar for audit-flagged genes/pathways; empty on failure | famile |
| **fal** | Hero stills, share cards, **VEED Fabric run briefings** | — |
| **H (Holo)** | Independent Observatory auditor — vision-language model reads the rendered site and verifies it matches `facts.json` | — (see [§3b](#3b-holo-auditor--independent-render-verification)) |

Optional later: **Pioneer** (critique classification).

### VEED Fabric (`veed/fabric-1.0` on fal)

Hosted by VEED — their API is a first-class demo moment, not an afterthought.

**Run briefing pipeline (LIVE 2026-08-22):**

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
demo includes a Fabric-generated briefing as the centerpiece.

### Fabric frontier strategy — the data-driven protagonist (2026-08-22)

Research read: VEED's Fabric launch post + fal's model page. What they are
excited about, in their own words: **production volume** (8¢/s exists so you
generate *many* videos), **any image with preserved character** ("the animation
is derived from your specific input" — mascots, illustrations, 3D renders), and
**video personalization** (same character, different states/scripts). The fal
side challenge names **a workflow** and **genmedia CLI** as the "advanced"
signals.

The median submission will be "an avatar pitches my product." Our answer:
**the vessel is the only mascot whose appearance is computed, not chosen** —
fill = ceiling headroom, cracks = audit warnings, colors = severity. That makes
our Fabric briefings a **time series of one character's health across the
78 days**: the protagonist literally embodies the evidence.

| Move | Status | Why it matters |
|---|---|---|
| **Briefing series framing** — "Briefing #1 of ~12" stamped on the run page | ✅ done (2026-08-22) | signals a weekly cadence, not a one-off demo prop |
| **Dr. Kytos presents** — the anchor (a named correspondent, not the vessel) speaks the broadcast; the vessel stays the instrument that shows where biology says we're wrong | ✅ live (`tools/render_presenter.py`, 2026-08-23) | Fabric maps phonemes to **facial keypoints** — a faceless vessel wastes the model; the anchor's face lip-syncs the newsroom script |
| **The cell anchor** — the subject given a face (a friendly 3D cell with a glowing nucleus, inside the vessel-as-instrument) as the Fabric source frame | 🧪 superseded by Dr. Kytos presenter | the vessel is the instrument; the anchor is the presenter |
| **The newsroom broadcast** — Tavily field research (`newsroom/research.json`) woven into a deterministic broadcast script the anchor speaks: opening, headline, audit self-own, "what the field is saying", sign-off | ✅ live (`enrich_newsroom.py`) | the briefing becomes a *product* (a news show), not a demo prop; extends the 78-day cadence naturally |
| **The vessel testifies** — briefing speaks the grounded OpenAI digest incl. its own audit self-own | ✅ live | the character's honesty is the product |
| **The sung sign-off** — ElevenLabs Music generates a short "Run #N anthem" (lyrics grounded in facts.json); the anchor breaks into song at the end | ✅ live (`render_anthem.py`, 2026-08-22) | nobody at a hackathon sings a scientific briefing; the 22s anthem is the demo's memorable close |
| **Volume workflow** — `facts.json → narrative → newsroom → TTS → Fabric → committed mp4` in one command | ✅ live (`render_briefing.py`) | VEED's "built for production volume" thesis, true for us |
| **genmedia CLI demo moment** — one-liner in the Loom | 🧪 attempted | fal side challenge's "advanced" box |
| **LoRA on the cell identity** — consistent character across all runs | 📅 this week | side challenge's "LoRA" box; makes the 78-day time-lapse coherent |
| **Weekly cadence automation** | 📅 this week | ~12 briefings between now and Nov 5 — the series is the product |

**Cadence pitch (the demo closer):** *"Every run of a 78-day public experiment
gets a talking briefing, auto-generated from the same committed facts. This is
briefing #1 — come back and watch the vessel fill, crack, or heal."*

---

## 3b. Holo auditor — independent render verification (Computer-use Agents)

Our entire thesis is "show when a model is biologically wrong." But who verifies
that what the Observatory renders matches the committed `facts.json`? Right now,
nobody. **H's Computer-use Agents** fill that gap.

**What it does:** `tools/holo_audit.py` uses Playwright to screenshot the deployed Observatory run page and sends it to Holo's VLM (`holo3-1-35b-a3b`) which reads visible values (vessel fill %, audit flag counts, run ID, headline) and diffs its reading against the committed `facts.json`. Any mismatch means the rendered page does not match the data contract — the audit catches a render bug.

**How it works:**

```
https://kytosapp.netlify.app/runs/k001/  (live deployed site)
  → Playwright screenshots the rendered page
  → VLM (holo3-1-35b-a3b via OpenAI-compatible API) reads visible values
  → answer_schema (Pydantic) → validated typed JSON
  → diff against facts.json
  → PASS / FAIL report (same pattern as planted_signal.py)
```

**Why Holo specifically:** Holo's vision (March 2026) states "models have
learned to think, but the next era of AI belongs to the systems that learn to
act." The Holo3.1 vision model (holo3-1-35b-a3b) is their flagship VLM — capable of reading complex UI layouts and returning structured, schema-validated answers. This is deeper than passive screen-reading: the VLM doesn't just see a
screenshot — it reads structured values from it, validated against a Pydantic schema (`answer_schema`). Non-conforming
answers are rejected and retried automatically.

**Fallback:** if the VLM API is unavailable (no `HAI_API_KEY` or API failure), the tool falls back to a deterministic digest check: compares committed `facts.json` against the rendered page text. This is the original approach — no vision model, just text comparison.

**Hard rule:** Holo audits the render, never the science. It checks that the
site shows what the data says — not whether the data is biologically correct
(that's the audit layer's job). It degrades to a skip if `HAI_API_KEY` is unset
or the API is unreachable; it never blocks the build.

---

## 3. Experience design — visual first

Quality bar: full-bleed 3D vessel hero, editorial typography, glassmorphism
evidence panels — inspired by [cell-architecture-studio](https://github.com/cclank/cell-architecture-studio)
and [plant-dna](https://github.com/thebuggeddev/plant-dna), with our own spin.

### Design references (primitives, not clones)

| Reference | Primitive we borrow | Kytos spin |
|---|---|---|
| Cell Architecture Studio | Stage + sidebar + specimen strip; 3D center; comparison modal | **Run strip**; **vessel stage**; metrics vs **ceiling** comparison |
| Plant DNA | Full-viewport stage; mono editorial type; Three.js sculpture hero | **Real-time 3D κύτος vessel** — glass with transmission/refraction, animated liquid fill, emissive crack halos, rising bubbles, floor reflection, bloom post-processing |
| Both | Detail panels, loading overlays, responsive layout | **Glass evidence cards** with scroll-reveal; instrument data strip |

**Identity:** observatory / mission-control metaphor — dark lab palette, phosphor
accents (gene-up, flag-amber, ceiling-cyan). The hollow vessel (κύτος) is the
3D centerpiece: an empty context waiting to be perturbed.

**The 3D vessel instrument** (`frontend/static/vessel3d.js`, 1162 lines):

The vessel is a real-time Three.js scene, not a flat SVG. It renders from the
same `facts.json` data as everything else — zero API calls at view time.

| Visual element | Data binding |
|---|---|
| Glass vessel | LatheGeometry from κύτος flask profile; MeshPhysicalMaterial with transmission, IOR 1.5, clearcoat |
| Liquid fill level | Mean ceiling headroom (`ceiling_headroom` averaged across metrics) |
| Liquid surface wave | Procedural ripple (two-frequency sine, per-frame vertex displacement) |
| Rising bubbles | Transmissive spheres inside the liquid, wobble + reset |
| Amber cracks | Warn/error audit flags — TubeGeometry along CatmullRom curves, emissive glow halos that pulse |
| Cyan droplets | Info audit flags — emissive spheres with scale-pulsing halos, floating above the liquid |
| Ambient particles | Custom circular sprite (canvas texture, additive blending) drifting upward |
| Floor reflection | Metalness 0.9 floor with caustics spotlight projecting the glow |
| Bloom | UnrealBloomPass — emissive liquid and droplets glow against the dark background |
| Camera | OrbitControls (auto-rotate + drag), mouse parallax, scroll-driven pull-back on home page |

**SVG fallback:** if WebGL is unavailable, `vessel3d.js` returns early and the
SVG vessel (baked at build time) stays visible. `site.js` animates the SVG fill
after a 2s timeout.

**Tech stack:** Three.js r169 via import map (jsDelivr CDN), RoomEnvironment for
glass reflections, EffectComposer pipeline (RenderPass → UnrealBloomPass →
OutputPass). No bundler — ES module loaded directly in the browser.

Skip for Milestone 0: gamification (XP, quizzes, flashcards) from Cell Architecture Studio.

### Pages

| Page | Layout | Vessel |
|---|---|---|
| **Home** | Full-bleed 3D vessel fills the viewport; headline + lede + CTA float over it with radial gradient scrim; glass data readout strip (fill %, audit, days left) pinned at bottom; scroll hint | Full-screen background, scroll-driven camera pull-back |
| **Runs** | Card grid — each card shows severity dot + fill % badge + headline + metrics | — |
| **Run detail** | Full-bleed 3D vessel hero (min-height 100vh) with title + metric summary + data strip overlay; evidence panels flow in a centered 760px column below with scroll-reveal | Full-screen background, auto-rotate + parallax |
| **Critique** | Links to GitHub Discussions; pre-registered hypotheses per run | — |

### Run detail (the load-bearing view)

1. **Full-bleed vessel hero** — 3D κύτος vessel fills the viewport; run ID, headline,
   metric summary, and instrument data strip (fill / audit / info) float over it.
2. **Metrics panel** — Plotly from committed CSVs only (bar vs ceiling).
3. **Audit flags** — lemma-style cards: severity, rule, genes; link to Critique.
4. **Literature rail** — Tavily for flagged entities; collapsible, labeled auxiliary.
5. **Biomedical NER** — Pioneer GLiNER2 entity chips per flagged gene (fine-tuned LoRA
   when trained; base model or regex fallback otherwise); label-colored chips, aggregate
   stats in hero strip.
6. **Narrative block** — OpenAI digest with **inline source links** to `facts.json`.
7. **Provenance footer** — commit, seed, hashes, reproduce command.

All evidence panels are glassmorphism cards (`backdrop-filter: blur`, translucent
background) that fade in via IntersectionObserver as they enter the viewport.

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
cp .env.example .env   # once; Venice for local narration — docs/venice-dev.md
./tools/run_enrichment.sh experiments/k001-mean-shift-baseline
# or run tools individually (see tools/README.md)

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

### Progress (2026-08-22, hackathon day)

| Track | Status |
|---|---|
| Core (A) | ✅ `facts.json` assembler (`src/kytos/eval/facts.py`), audit rules + CLI (`src/kytos/audit/`), k001 seed — committed |
| Enrich (B) | ✅ four `tools/render_*.py` + one-shot `tools/run_enrichment.sh` + `env.example`; degrade-empty verified against k001; **live API run in progress** (venv unblocked: Python 3.12 + partner clients) |
| Frontend (C) | ✅ `frontend/build.py` → `dist/` (home, runs index, k001 run detail); Playwright-verified desktop + mobile, zero console errors; briefing video autoplay; Netlify (`netlify.toml`) |
| Deploy (B) | ✅ Netlify (`netlify.toml`) — auto-builds `frontend/dist/` on push; connect repo in Netlify dashboard |
| Pioneer (C) | ✅ `tools/pioneer_ner.py` — **fine-tuned GLiNER2 LoRA deployed** (`kytos-bio-ner-v1_2`, 18 silver-label samples from k001 Tavily literature); base inference + regex fallback; Observatory **Biomedical NER** panel live on k001 |
| Demo primitives (B) | ✅ data-bound vessel instrument (fill = ceiling headroom, cracks = audit flags), audit confession banner, metric→CSV drill-down, planted-signal self-test (`tools/planted_signal.py`), [`demo-script.md`](demo-script.md) |
| UX polish (B) | ✅ instrument-panel metaphor: live VCC timeline rail + countdown to Nov 5, vessel fill animation on load, run-strip severity dots + scroll-snap, flag severity badges, breadcrumb, copy-to-clipboard provenance, `prefers-reduced-motion` support; mobile overflow fixed (grid `min-width:0`, narrative/provenance wrapping) — Playwright-verified desktop + mobile, zero console errors |
| 3D vessel (C) | ✅ **Three.js real-time 3D κύτος vessel** — glass with transmission/refraction, animated liquid fill, rising bubbles, emissive crack halos, cyan droplets, reflective floor, UnrealBloomPass, mouse parallax, scroll-driven camera, auto-rotate + drag; SVG fallback if WebGL unavailable (`frontend/static/vessel3d.js`, 1162 lines) |
| Full-bleed immersive layout (C) | ✅ home + run detail pages rebuilt as full-viewport vessel hero with overlaid glass content; evidence panels flow in centered column with scroll-reveal (IntersectionObserver); glass data readout strip; runs index cards show severity dot + fill % badge; **home hero uses 3-phase guided flow** (claim → argument → evidence) — each phase shows 3 things, advancing closes the previous; content-hash cache-busting on `site.js` prevents stale-JS after deploys |
| Holo auditor (C) | ✅ `tools/holo_audit.py` — Playwright screenshots of the deployed Observatory sent to Holo VLM (`holo3-1-35b-a3b`); VLM reads values and diffs against `facts.json`; degrades to skip without `HAI_API_KEY`; same PASS/FAIL pattern as `planted_signal.py` |
| Integration | ⏳ rebuild `dist/` after enrichment → redeploy → 2-min Loom |

#### Pioneer biomedical NER (side challenge) — 2026-08-22

Fine-tune is **live** on k001:

| Step | Status | Notes |
|---|---|---|
| Base inference | ✅ | `fastino/gliner2-base-v1` on all 6 literature files |
| `/generate/ner/label-existing` | ❌ | Platform returns empty `{}` per input (even docs examples) — escalated workaround |
| JSONL upload + preview | ✅ | Hand-crafted + silver-label rows validate with non-empty `entities` |
| Training pipeline | ✅ | 18 Tavily snippets → silver labels → `kytos-bio-ner-silver` → LoRA 5 epochs (~98s) |
| Deployed model | ✅ | `kytos-bio-ner-v1_2` · job `4225fc3e-3839-42fb-9cfb-e41d7c08dfe2` |
| Observatory UI | ✅ | Run detail **Biomedical NER** panel + entity count in hero strip |

Commands:

```bash
# one-time train (skips if model already deployed)
python tools/pioneer_ner.py --train

# inference on a run's literature/*.json → writes *.entities.json
python tools/pioneer_ner.py --run experiments/k001-mean-shift-baseline
```

Training strategy in code (in order): reuse deployed model → label-existing → silver
labels from base GLiNER2 + regex fallback → upload JSONL → synthetic `/generate`
(last resort).

### Shipped since Milestone 0 (2026-08-22)

- **k002 — first real `cell-eval` 0.8.2 run.** VCC 2025 validation (H1 hESC,
  98,927 cells, 50 targets; public Arc bucket, sha256-checked) through the
  actual submission harness → mean-shift prediction → `ceiling/targets` +
  `de/targets` → adapter import. Floor results: DE sig-genes recall 0.0 vs
  ceiling 0.494; pearson_delta mathematically undefined (constant prediction)
  vs ceiling 0.667; audit clean. The mirror image of k001: invisible to the
  audit, legible to the metric. Both preregistered hypotheses confirmed.
  Scoring matrix subsampled (200 cells/pert + 3,000 controls, seed 0) —
  disclosed in meta.json and on the page; full-depth run queued as k003.
- **Undefined-metric honesty end to end.** NaN → empty CSV cell → JSON null
  → "undefined"/"not reported" rendering across chart, pillars, comparison,
  home pill. Metric-name aliasing bridges cell-eval's schema to our facts.
- **Narrative grounding checker** (`tools/check_narrative.py`, deterministic,
  offline): digest numbers must trace to facts.json, no debug-annotation
  leaks (`(facts:…)` — root-caused in the generator prompt), per-gene
  directionality claims allowed only for genes downstream of the flagged
  pathway. Caught a Venice hallucination (invented ISG15/IFIT1/MX1/OAS1
  directions) the day it shipped. Third Trust card on every run page.
- **Autonomy loop** (`.github/workflows/observatory.yml`): push touching
  experiments/tools/src/frontend (+ weekly cron) → test gate → per-run
  enrichment → build smoke → bot commits artifacts back. Degrades gracefully
  without secrets.
- k001 critique link 404 fixed; runs-header atmosphere containment fixed;
  literature rail scrubbed of scrape residue and deduped.

### Later (Aug → Nov 2026)

- k003 = full-depth cell-eval scoring (the deterministic checker matrix
  already in place; just needs overnight GPU-free time)
- Each new run auto-publishes to Observatory (workflow above; secrets needed
  for enrichment steps in CI)
- Leaderboard tracker; audit rules mature; weekly digests
- Final submission: `submission/script.py` → H5AD (Nov 5)

---

## 7. Demo script (2 minutes)

**Canonical script:** [`demo-script.md`](demo-script.md) — merged VEED/Fabric
front-load + self-own + planted-signal + 78-day closer. No PowerPoint; live site
only.

Beat order: hook (10s) → Fabric autoplay (20s) → self-own (25s) → provenance
(35s) → partner rails (25s) → planted-signal (15s) → GitHub closer (10s).

Build-in-public posts for hackathon day: [`build-in-public.md`](build-in-public.md).

Presentation talking points: [`competitive-landscape.md §6`](competitive-landscape.md#6-presentation-crib-sheet).

---

## 9. Frontier UI & Agentic Architecture (Shipped 2026-08-22)

The Observatory is built with a modular, template-driven design system optimized for scientific scrutiny and agentic transparency:

### 1. Jinja2 Component-Driven Templating
* **Environment:** [`frontend/observatory/templates.py`](../frontend/observatory/templates.py) with structured templates under [`frontend/observatory/templates/`](../frontend/observatory/templates/).
* **Modularity:** Monolithic string concatenation replaced with clean layouts (`base.html`, `home.html`, `about.html`, `runs_index.html`, `run_detail.html`) and reusable partials (`matrix.html`, `journey.html`, `disclosure.html`, `agent_trace.html`).

### 2. Multi-Run Comparison Matrix
* **Cross-Experiment Scorecard:** `/runs/` renders an interactive comparative scorecard comparing models (`k001` mock baseline vs `k002` real mean-shift vs `k003` Layer A) across all 6 `cell-eval` metrics, ceiling headroom bars, and biological audit statuses.

### 3. Interactive Volcano Plot & DE Explorer
* **Biological Effect Exploration:** Embedded Plotly scatter plot ($\log_2\text{FC}$ vs. $-\log_{10}p$-value) categorizing unperturbed genes, CRISPRi targets, and audit-flagged violations with responsive tooltips.

### 4. Dual View Mode Switcher
* **Audience Adaptability:** Header toggle between **🎙️ Broadcast Mode** (video briefing + 3D vessel) and **🔬 Deep Science Mode** (auto-expanded metrics, volcano plots, and raw CSV traces). Persists via `localStorage` and deep links with `#mode=science`.

### 5. First-Class No-WebGL Fallback (Rated 9/10)
* **Zero Degraded Gaps:** Immediate WebGL probe with 1.2s timeout fallback.
* **Interactive SVG Vessel:** Data-bound 2D SVG with hoverable/clickable cracks and organelles that trigger `.vessel-callout` tooltips and auto-scroll to audit sections.
* **Keyboard Fallbacks:** Keys `m` (membrane opacity) and `c` (crack halo focus) work seamlessly in SVG mode.
* **Luminous Gradient Aesthetics:** Replaced flat panels with multi-stop dark blue-glass gradients and cyan highlights.

### 6. Beautiful UI Agentic Investigation Trace
* **Living Lab Notebook:** Visualizes Dr. Kytos’s autonomous pipeline execution (`cell-eval` metric evaluation, `kytos.audit` invariant checks, `tavily` literature search, and `narrative` synthesis) as an AI-native step-by-step trace with status indicators and execution timings.

### 7. Fragment-Assembly Vessel Callout
* **Tooltips that assemble like the vessel founds itself:** when a crack/organelle is hovered (3D-raycast and SVG-fallback paths), the `.vessel-callout` doesn't just fade in — a **pure-CSS fragment field** marches across the glass, scatters outward, "goo-merges" through a mid-dissolve blur, then dissolves to zero as the legible signal body hardens beneath it. The motif borrows the coalescing-fragments idea from Codrops' *PixelGooeyTooltip* without its GSAP/SVG-filter deps.
* **Zero new dependencies, zero template churn:** driven by a `.vessel-callout::after` pseudo-element + a 520ms `@keyframes vessel-shard-in`; wired via a single `frag-showing` class toggled in JS (both 3D and SVG callout paths stay at parity).
* **Graceful by default:** pointer-transparent, entry-only, theme-agnostic `border-radius: inherit`, no-op under `prefers-reduced-motion` (plain fade), and never touches the tooltip's own opacity/position transition — so it is an enhancement, not a prerequisite.

---

## 10. Open questions

1. ~~Deploy target for `frontend/dist/`~~ → **Netlify** (`netlify.toml`) — decided 2026-08-22
2. ~~Jinja2 template migration~~ → Completed across all 4 page types (`home`, `about`, `runs`, `run_detail`).
3. ~~Interactive DE volcano plot~~ → Shipped in Audit & metrics panel.
4. ~~No-WebGL fallback parity~~ → Upgraded to 9/10 interactive SVG parity.
5. Pioneer fine-tune for critique classification — post-hackathon? (NER fine-tune shipped for side challenge.)

