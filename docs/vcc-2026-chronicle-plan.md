# VCC 2026 — Observatory Chronicle Plan

Status: **DRAFT for review** · Owner: udingethe · Date: 2026-08-23

This doc turns the brainstorm ("the Observatory as the chronicler of the
Virtual Cell Challenge, with an open-source PD cast, translation, and dubbing")
into a decision: what we build, what we hold, what we gate on, and the stack
that carries it.

Companion docs: [`observatory.md`](observatory.md) (product surface),
[`code-organization.md`](code-organization.md) (stack), [`run-protocol.md`](run-protocol.md)
(data contract).

---

## 0. TL;DR — the recommendation

Treat the vision as **three stacked bets**, and bet only on the first two:

| Ladder | What it is | Verdict |
|---|---|---|
| **L0 · Lab notebook** | The per-run site, vessel, audit flags, bulletins | ✅ Already real — keep, unchanged |
| **L1 · Chronicle** | Public digests of the challenge: weekly field reports + **short packs** | ✅ **Build now, shorts-first** |
| **L2 · Cast layer** | PD characters as desks, translation, dubbing, global tier | ⏸ **Gate on evidence; probe, don't commit** |

**The plan in one sentence:** ship the **2025 post-mortem short pack** (~8 ×
10–20s clips + a long-form text archive) in ~3 weeks as the pilot; if it
clears the gates (below), run a weekly Kytos/Holmes field-report cadence
through the validation phase; keep the cast and multi-language layer as a
gated probe with measurable go/no-go criteria; never let broadcast hours
displace model hours in the Oct 22 – Nov 5 window.

---

## 1. Context — the real calendar

The 2026 Virtual Cell Challenge went live **Aug 20, 2026** (validation data +
leaderboard). Hard dates, from the Arc announcement:

- **Now – Oct 22**: validation phase — live leaderboard, ≤2 submissions/day
- **Oct 22**: final test set released (3 unseen cell lines), leaderboard goes dark
- **Nov 5**: final submissions due (23:59 UTC)
- **Mid-late Nov**: winners announced — then the post-mortems, the archive,

~11 weeks, three acts:

- **Act I · The Survey** (now – Oct 22): the field is readable. Live metrics,
  weekly reports, public analysis — including our self-audits.
- **Act II · The Passage** (Oct 22 – Nov 5): silent leaderboard. The strongest
  story beat — "we are not being counted; hypotheses only." Tie to the test
  set release broadcast.
- **Act III · The Reckoning** (Nov →): post-hoc analysis of *any* publicly
  released results, the anatomy of our submission, the archive.

**The market is real and countable:** VCC 2025 drew ~5,000 registered across
114 countries; 1,200 teams submitted; 300 made final submissions. Arc's own
wrap-up called the "community arguing in public" *one of the best parts of the
challenge*. No one has a chronicler.

---

## 2. The three ladders — what changes where

### L0 — Lab notebook (as-is)

The existing Observatory: run pages, κύτος vessel instrument, audit flags,
narrative, provenance. **Nothing changes.** It is the trust surface everything
else renders credible.

### L1 — Chronicle (build)

Public-facing editorial artifact **per event**, not per run. **Shorts-first:**
the audience prefers 10–20s clips and the pipeline already renders 8s-class
short clips (bulletins, presenter), so L1 ships as **short packs**:

- **Field reports** (weekly, cheap): digest of where the field stands, our
  own runs, metric forensics — text-first, one 10–20s clip max (or zero).
  Reuses the existing `enrich_newsroom.py` → newsroom digest pipeline.
- **Short packs** (the flagship unit): ~8 × 10–20s clips, one lesson each,
  vessel + one chart + voiceover; 9:16 + 16:9 variants; VTT subtitles.
- **The archive**: the long-form text, transcript, data links + citations —
  the durable, citable artifact that outlives the clips.

### L1 research layer — Firecrawl Research Index (added 2026-08-23)

For grounding the chronicle, **Firecrawl Research Index**
(`/v2/search/research/papers`) is a purpose-built paper search: ~43M
abstracts (PubMed/bioRxiv/medRxiv/arXiv, majority life sciences), canonical
`arxiv:`/`doi:`/`pmid:`/`pmcid:` IDs, **passage-level reads** to verify a
claim inside a paper, and citation expansion (similar / citers / references).
Free, no key required.

**Probe result (2026-08-23):** found the exact VCC papers we cite —
`arxiv:2511.16954` (PDS scale paper, top hit), `pmid:40578317` (Cell
Turing-test commentary, `doi:10.1016/j.cell.2025.06.008`), flow-matching env
— and read a passage inside 2511.16954. It replaces hand-searching in episode
scripts; it's a **scholarly layer separate from Tavily** (web).

- **Verdict: use it** — as `tools/research_lit.py` (small, degrade-empty tool
  like our siblings). No key needed to start.
- **Rule**: grounds the **script** (citations on clip + archive) and can
  feed the run-page **literature rail** as a second source; never invents
  metrics; fails to empty.
- **Caveat**: brand-new (launched Aug 2026), recall@10 is self-reported —
  good as an assisting layer, not a sole source of truth.

### L2 — Cast + languages (gated probe)

- **Cast lanes** — each character implements a *stance*, not a mascot:
  Dr. Kytos (anchor; ours; CC0), Sherlock Holmes (audit/forensics lane),
  Dr. Jekyll/Mr. Hyde (confession lane), Victor Frankenstein (creation lane),
  Prof. Challenger (claims-under-stress lane), Capt. Nemo (the deep —
  the unseen cell lines), the 2026 PD class (public tier, e.g. Betty Boop).
- **Translation/dubbing** — subtitles (cheap, static) vs dubbing (per-language
  TTS + re-render). Dubbing is a **cost amplifier**, not a product feature:
  gate it, never default it.

---

## 3. Why this shape — the evidence

### For the chronicle (L1)

1. **Niche chroniclers compound.** Two Minute Papers: one person, weekly,
   paper-literate, niche — the model that a "virtual-cell challenge" niche
   could support. No one currently occupies that niche for cell modeling.
2. **First-mover by trust, not IP.** PD characters are free (by design), so
   the moat must be *our* canonical identity — the "Observatory" name, the
   data-traceability, the pipeline — and time in the seat.
3. **Narrative engagement has support — for the working community.**
   Narrative framing raises engagement and memory of scientific content
   (Dahlstrom 2014, *PNAS*). For a technical tier already "in it", that
   converts attention →.

### Against the broad-cast layer (L2), per evidence

1. **"Value ≠ capture" (Thiel, lesson 1).** Altmetrics show weak correlation
   between social attention and cited impact (Priem et al. 2012;
   Thelwall et al. 2013). If the only "capture" is an audience, the audience
   doesn't convert to the thing that wins the prize... so define capture
   explicitly ($, papers, or a platform moat) or don't build the stage.
2. **The public tier is underproven.** Decades of science-communication
   research (Bauer, Allum & Miller 2007; Scheufele & Nisbet 2009 — the
   "deficit model" is dead): transport does not produce attitude/behavior
   change in distant publics. The *competitor community* tier is the one the
   evidence supports; the *global public* tier is the least supported.
3. **Synthetic-stigma is a real, present tax.** Post-2023 label studies
   consistently find "generated/automated" content is trusted less even when
   accurate. Lip-synced avatars are the crux: the fun may *cost* credibility
   — the site's honest-by-design (badges, audit links, provenance) is the
   mitigation, and it is strongest on L1, not L2.
4. **Conflict of interest doubles.** Player + broadcaster. Narrative
   transport trades credibility for engagement (Dahlstrom, *idem*). A
   "confession" episode about our own mistakes is credible *because* our
   audit surface exists — again, that's an L1 asset.
5. **Time-sharing risk against the actual prize.** The Oct 22 – Nov 5
   passive window is where the model needs hours. A weekly broadcast clocks
   against that. Budget it explicitly (see §7).

### The Paul Graham + Peter Thiel read

- **Graham**: "start with the problem, not the brand" *(How to Get Startup
  Ideas, 2005)* — we are in the race and needed the notebook; that's the
  canonical self-located problem. He'd push to **start small**: digest the
  2025 data *our* teams as the first customer, count engagement, then scale
  (Do Things that Man's Own Gas — "Do, then talk", 2013).
- **Thiel**: "what important truth do you believe that few agree with?" —
  the one that says **the field's story-teller position is vacant and cheap
  to occupy until someone claims it**. But also idly: "competition is for
  losers" — avoid head-to-head sports-casting and compete at *documentation
  quality*, and "definite optimism" — the finite plan (three acts, gates)
  is a competitive edge.
- **Both counsel against the diffuse "global vibes broadcast"**: it's the
  one ladder where neither evidence nor economics is on our side for now.

---

## 4. Pilot — the 2025 post-mortem (first short pack)

**Why the 2025 post-mortem first:** the full 2025 dataset (incl. held-out
test) is public via the Arc Virtual Cell Atlas; none of it is "our data" —
it's the *only* topic where we can be thoroughly forensic without framing /
overclaiming anything about our own model.

Spec (v1): **8 × 10–20s clips + one long-form text archive** (single
one-and-only `ideas` artifact, not a 10-min film). Every clip = one lesson,
vessel + one chart + voiceover. Full beat sheet:
[`chronicle/short-pack-001.md`](chronicle/short-pack-001.md).

---

## 5. Cadence & effort budget (hard rules)

| Artifact | Cadence | Effort ceiling |
|---|---|---|
| Field report digest | weekly (Fri) | ≤1h, auto-assembled, text-first |
| Short pack (flagship unit) | ~1 per 2–3 weeks | ≤ half a day, starts from digest |
| 2025 post-mortem short pack | **one-time, in next 3 weeks** | ≤ 4h marginal |

> **Hard rule: a week without a model improvement beats a week as a
> newsletter.** The content pipeline is the place to spend leftover hours —
> never the model's.

---

## 6. Gates (evidence-based, written down)

Gate is not "did it ship" — it's "did it *do anything*".

1. **L1 go** — the 2025 post-mortem short pack: ≥50 external engagements
   across the pack OR ≥1 substantive reply from a non-us team, and marginal
   cost ≤4h (counting every hour, including ours).
2. **L2 probe** — only after L1 passes: build ONE confessional (Dr. Jekyll/Hyde)
   episode from our real audit data (the kind that writes itself). Success =
   engagement ≥ L1 median *and* you (owner) still want to do it every other
   week.
3. **L2 scale** — a second cast lane opens only if the first proved
   engagement *and* at least one external contributor asked to join.
4. **Dubbing** — only subtitles until Act III. If an episode earns ≥ 30% of
   its reach from non-English speakers, *then* translate it (subs), and *then*
   measure, and only then consider a dubbed flagship.
5. **The passage rule** — the entire week of Oct 22 and Nov 5 is **model
   weeks**. No episode production; archive/redirect content only.

---

## 7. Guardrails (the version of the site we keep)

1. **Neutrality**: we only analyze what is public or aggregate. We never
   claim to know others' scores; if a chart includes our own runs it says
   "ours".
2. **The cast is not the content**: a character without data gets no
   episode. The vessel "testifies", the character "interprets** — never*
   vice versa.
3. **PD hygiene**: own renders only (no film costumes/logos); hold the
   *canon* (Kytos identity, CT0 release) as the actual asset.
4. **Honest-by-design overrides fun**: the confession banner, "probe · mock
   data", undefined metrics, audit links — the anti-slop surface. These are
   features, not bugs; they are the antidote to the synthetic-stigma tax.
5. **Schedules are dialect**: the "confession" episodes only cover our own
   run's real flags (k001/k002 both have honest stories to tell).

---

## 8. The stack behind all of this — is it still Python?

**Yes.** The entire support system stays Python + bash + git + Netlify. The
reason: this is a **batch pipeline over committed artifacts**, and every
beam of it already exists in Python — and the project rulebook
(`docs/code-organization.md`) says one language, one env manager, no new
servers during the challenge. Nothing in the chronicle plan changes the
shape of the system.

### What exists today (mapped)

| Concern | Today | Ships the plan? |
|---|---|---|
| Facts + artifacts contract | `src/kytos/eval/facts.py`, `run-protocol.md` | ✅ the data spine |
| Newsroom digest | `tools/enrich_newsroom.py` (Tavily → research.json) | ✅ base of field reports |
| **Research grounding** | **Firecrawl Research Index** (`/v2/search/research/papers`, no key needed) | ✅ new `tools/research_lit.py` — scholarly layer for scripts/citations; separate from Tavily (web) |
| Script → TTS → video | `tools/render_presenter.py` (OpenAI TTS + fal veed/fabric) | ✅ short-pack renderer core |
| Briefing/visuals | `tools/render_briefing.py`, `render_visuals.py` | ✅ |
| Site | `frontend/build.py` (Jinja2 static gen) — **no server** | ✅ archive/transcript pages |
| CI/CD | GitHub Actions + Netlify (`netlify.toml`) | ✅ cadence cron |
| Verify | `pytest` (94), ruff, `holo_audit.py`, `check_narrative.py` | ✅ gate checks |

### What the chronicle adds (still Python)

1. **`tools/render_episode.py`** — the orchestrator, **shorts-first**: one
   script per clip under `newsroom/short-pack-N/` (markdown in git = source
   of truth) → scene parser → TTS → optional Fabric lip-sync → ffmpeg
   assembly per clip (b-roll: vessel chips, metric bars) → VTT/SRT subtitles
   → 9:16 + 16:9 variants → publishes into an `episodes/` index → triggers
   `frontend/build.py`. Degrades (like every tool here) to ASCII transcript
   + still if any leg breaks.
2. **Subtitles only** for i18n: LLM translate → VTT. No lip-sync cost.
3. **Weekly cron** in GH Actions for field reports; a manual "make short pack"
   trigger for flagships.

### Why Python wins, honestly

- It's the only runtime that already has: the data contract, the audit layer,
  the renderer, 94 tests, the secrets policy.
- The pipeline is **off-line and batch**: no request-traffic, no queueing,
  no concurrency — nothing Python doesn't do trivially.
- JS already owns the browser (three.js vessel, site.js). No Node toolchain
  at repo root (a stated rule), no server (FastAPI explicitly deferred to
  post-challenge per code-organization.md).

### Where Python stops being the answer (decision points, noted, not solved)

- **GPU-heavy lip-sync *in-house*** (e.g. if fal Fabric became untenable) —
  that's a model-serving task, possibly GPU-native tooling, not a site task.
- **The L3 "let other teams adopt the cast" platform** — multi-tenant
  accounts, uploads, billing: that is a *product with servers*, which would
  legitimately reopen "FastAPI now?" — intentionally deferred (gate 2).
- **Heavy media distribution** (Act III archive growth past the 4 MB committable
  cap) — Netlify Large Media / R2 via URL redirects, which touches the git
  model but not the languages.

Net: no language change; the plan is Python + markdown + ffmpeg + the
existing facts contract.

---

## 9. Suggested first week (if approved)

1. Write the **8-clip short pack** scripts
   (`newsroom/short-pack-001/`) — grounded per clip via Firecrawl Research
   Index passages + wrap-up + participant papers — ~60 min.
2. `tools/render_episode.py` skeleton (reuses `render_presenter.py` internals —
   ~half a day); batch-render the 8 clips + VTT.
3. Ship the pack as text-archive-on-Observatory + 8 shorts (9:16 + 16:9)
   + VTT subtitles across 2 platforms (X + LinkedIn); watch the gates.

---

## 10. Research & sources

- Arc Institute — "The Virtual Cell Challenge 2026" (Aug 20, 2026) and
  "Virtual Cell Challenge Wrap-Up" (Dec 2025): timeline, metrics, participants,
  public-analysis note.
- Arc Virtual Cell Atlas — 2025 dataset with held-out test, public download.
- Dahlstrom 2014, *PNAS* — narrative effects on memory/engagement vs
  credibility trade.
- Bauer, Allum & Miller 2007; Scheufele & Nssbet 2009 — deficit-model critique
- Priem et al. 2012; Thelwall et al. 2013 — attention ≠ citations.
- 2023–25 "AI-generated" label-trust studies — synthetic-content discount.
- Graham, "How to Get Startup Ideas" (2005); "Do Things that Work" (2013).
- Thiel, Zero to One (2014) — capture vs. checkpoint, niche monopoly,
  definite optimism.