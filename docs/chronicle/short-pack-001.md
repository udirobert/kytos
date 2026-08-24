# Short Pack 001 — "1,200 Teams, One Lesson" (VCC 2025 Post-Mortem)

Status: **DRAFT OUTLINE** · Owner: udingethe · Date: 2026-08-23
Series: VCC 2026 Chronicle · Lane: Dr. Kytos (anchor) + Holmes (metric forensics)

Pilot for the Chronicle plan — see
[`vcc-2026-chronicle-plan.md`](../vcc-2026-chronicle-plan.md).
Format: **shorts-first** — ~8 clips of 10–20s each (audience prefers short;
the pipeline already renders 8s-class clips). One long-form **text archive**
is the durable artifact; the clips are translations of it.

---

## Logline (the one idea)

1,200 teams raced to predict what 300 gene knockouts would do to a single
human cell line. ~300 finished. Almost none beat the naive baseline on the
"obvious" metric. The lesson: **the metric that looked most scientific told
you the least.**

## Format

- **Text-on-Observatory (archive, long-form)**: full transcript + data links +
  citations. This is the durable, citable product.
- **8 × short clips (10–20s, 9:16 + 16:9)**: one lesson per clip; vessel +
  one chart + voiceover. Dr. Kytos anchors; Holmes takes the metric forensics
  ("he investigates the instrument, not the cells").
- **Subtitles**: English VTT/SRT from the transcript (bilingual later, gated).

## Clip pack (the 8 single-lesson clips)

| # | Hook (≤15 words) | Lesson | Data on screen | Src |
|---|---|---|---|---|
| 1 | "1,200 teams. 300 finished. Here's the one thing they learned." | The challenge worked as designed: it measured the field's floor | counts 5,000→1,200→300 | [wrap-up] |
| 2 | "The trapdoor metric" | PDS was scale-sensitive: as predictions grow, PDS → sign-cosine-like; it rewards pattern over magnitude | scale-factor curve | [arXiv:2511.16954] |
| 3 | "The biologist's metric" | DES (up/down gene set) is what biologists actually read; winners used DEG frequency as feature + statistical baselines | DES vs PDS bars | [wrap-up] |
| 4 | "Everyone lost on MAE — by design" | Raw transcriptome error nearly impossible below the mean baseline → excluded from optimization | MAE: mean-baseline | [wrap-up] |
| 5 | "The hybrid lesson" | "Purely AI didn't beat statistical baselines" — the winners: deep + classical + biological priors | BM_xTVC hybrid schema | [wrap-up] |
| 6 | "The $100k surprise" | The Generalist Prize went to a flow-matching generative model (Altos / PRiMeFlow), not the top-3 → broader panel wins | 7-metric radar | [arXiv:2604.13986] |
| 7 | "A baseline you can't measure" | Even an *honest* constant predictor (our k002) is *undefined* on Pearson Δ — the metric has no floor-feeling | k002 "undefined" | our facts |
| 8 | "The harder test is live right now" | Zero-shot: 6 unseen lines, no training set, 6 metrics. Same lesson, no help | VCC 2026 date rail | [vcc 2026] |

## The corridor (for the long-form text, and as clip 2–4 background)

| Metric | What it measures | Post-2025 known issue |
|---|---|---|
| **PDS** | Are predicted effects distinguishable? (L1 nearest-neighbor) | **Scale-sensitive** → sign-cosine-like as magnitude grows |
| **DES** | Is the up/down gene set right? | The biologist's metric; won by DEG-freq features |
| **MAE** | Raw transcriptome error | Almost everyone **worse than mean-baseline** → effectively excluded |

## Measurement loop (the experimental part)

- Ship the **8 clips as one experiment** (2–3/week is too slow; one pack,
  one pulse).
- The gate (per plan §6): **≥50 external engagements across the pack OR
  ≥1 substantive reply from a non-us team** in 2 weeks. The **marginal cost
  ≤ 4h** counts every hour.
- The metric that matters for **L2 (cast)**: an answer to *"did anyone ask to
  see more?"* — that's the signal that scales, not views.

## Verification checklist (before we call this grounded)

- [ ] Fetch arXiv:2511.16954 v1 HTML — pull the exact "scale factor + PDS"
      curves to cite on-screen; quote the cos-condition (passage read,
      top hit on "perturbation discrimination score" 🔎 confirmed).
- [ ] Read PRiMeFlow (arXiv:2604.13986) abstract + intro; capture
      `go-with-the-flow` memory ("flow matching across latent + gene space").
- [ ] Cell commentary (Roohani et al., Cell 2025) — the "Turing test"
      framing and the 300k/300 numbers; exact phrase:
      `pmid:40578317`/`doi:10.1016/j.cell.2025.06.008` (confirmed via index).
- [ ] Arc wrap-up (Dec 6, 2025) — verify "effective exclusion of MAE",
      the Generalist-Prize history, PDS-behavior paragraph.
- [ ] Arc Virtual Cell Atlas — link + size for the archive page (no data pull).
- [ ] BioMap (BM_xTVC) paper status — cite team by name, "forthcoming" if
      none public.

## Delivery notes

- "The challenge worked — it told us where the field is. That's what a
  benchmark is for." Forensic, not defeatist.
- The honest-self-own beat (#7) is **ours**: k002's pearson_delta is
  *undefined* — a 20-second confession. This clip is the one that proves the
  "confession lane" can be real, not narrative.
- No new faces until the L2 gate passes: Kytos + Holmes audio-only (or
  Holmes as a text-card / alternate voice — decide when we spec
  `render_episode.py`).

## Pipeline (outline → clips)

`docs/chronicle/short-pack-001.md`
 → `newsroom/short-pack-001/` (a script per clip in one dir — source of truth)
 → `tools/render_episode.py` (reuses `render_presenter.py`; TTS → Fabric if a
 face; b-roll = vessel + metric bars; VTT per clip; 9:16 + 16:9 variants)
 → GH Actions manual trigger → Netlify → social (2 rotating platforms to
 test: X + LinkedIn, measure).

## Clip shape — AGREED v2 (2026-08-23)

Refinements after specimen review:

1. **One concept per short, hard cap.** ~40 words spoken max (≈15s at
   ~160wpm). No second idea, no run-on fallout.
2. **Keep FACT → METAPHOR → MEANING → SOURCE**, but tighten each beat to
   one short line.
3. **Less editorial.** Drop the "we publish…" manifesto voice; the aphorism
   carries the stance observationally ("a louder metric is not a truer one"
   — not "we publish the signal").
4. **SOURCE rendered in the caption card** as "(Source: …)" + spoken once
   aloud; never dangles without a link.
5. **Glossary, compounding.** Each short seeds one glossary entry: term →
   plain-language definition. Caption card carries
   "· Glossary: PDS — perturbation discrimination score". The glossary is a
   growing artifact (see Glossary section below).

Specimen 2-tight (15s, 39 words, bright anchor) demonstrates v2 — see
`~/Downloads/kytos-specimen-bright/specimen-002-trapdoor.mp4` and
`docs/chronicle/scripts/specimen-002-trapdoor-tight.md`.

Anchor default is now **bright** (`visual/drkytos-african-2.png`) and
`render_presenter.py` gained `--script` so chronicle scripts never touch a
run's canonical `newsroom/script.md`.

## Glossary — growing artifact

A term → plain-language definition, one per short, accumulating over time.
Exported from `docs/chronicle/glossary.md` as the canonical list (later: a
static Observatory page). Format per entry:

| Term | Digestible definition | First appears in |
|---|---|---|
| PDS (perturbation discrimination score) | Can you tell one perturbation's effect apart from another's? | specimen-002 (trapdoor) |

The voice rule: define with a question or a kitchen metaphor, never jargon-on-
jargon. Every entry links to the short that introduced it.

## Clip shape — AGREED (2026-08-23)

Every short follows **FACT → METAPHOR → MEANING → SOURCE**:

1. **FACT** — a committed, linkable claim (from `facts.json`, a paper, the
   wrap-up). No claims beyond the source.
2. **METAPHOR** — one image that translates the mechanism ("a microphone
   built for volume, not truth"). One, never two.
3. **MEANING** — the aphorism. This is the retellable line — the unit that
   travels ("A louder metric is not a truer one.").
4. **SOURCE** — named aloud (paper/broadcast) + exact citation in the VTT/
   transcript card.

Specimen 2 (*the trapdoor metric*, 20s) demonstrates the shape end-to-end —
see `/tmp/kytos-specimen/metaphor/` and
`~/Downloads/kytos-specimen-bright/specimen-002-trapdoor.mp4`. The source
readout renders as "(Source: arXiv:2511.16954)" in the caption card.

Pace note: 54 words → 20s (≈160 wpm). Slightly slow for a short; next
experiment trims to ~45 words / ≤15s and lifts delivery tempo.

## Context layer — PROTOTYPED (2026-08-23)

The three-rung context layer is now a live surface in the Observatory:
- `/shorts/` — the Chronicle index (poster grid)
- `/shorts/specimen-002-trapdoor/` — the trapdoor short: video + captions +
  **In plain words** card + **New words** tooltips + **Where this comes from**
  (arXiv + who-wrote-it) + **Deep science** `<details>`.
- Data: `docs/chronicle/shorts.json` (manifest) + `glossary.json` (tooltip
  source) + `docs/chronicle/media/<slug>/` (video/poster/captions).
- Renderer: `frontend/observatory/shorts.py` + `templates/short.html` +
  `templates/shorts_index.html`; wired into `frontend/build.py` + sitemap.

To add a short: add a manifest entry + media folder, rebuild, done.

## Specimen status (2026-08-23)

Rendered **one specimen clip first** (13.6s, confession / clip #7 equivalent)
through the real pipeline — see `/tmp/kytos-specimen/` for the mp4 + poster +
VTT + review card. The pack's other 7 clips are **not** built until we agree
on what the specimen establishes (look/feel/length/captions/overlays).

Pipeline bugs the specimen burned out (all fixed in source):
`render_presenter.py` had no `__main__` entrypoint (silent no-op),
`obs` extras were absent from the default venv, and `strip_markdown` leaked
multi-line HTML-comment + heading text into the spoken script.

Next iteration candidates (pick after review): vessel chip + metric-bar
overlay, burned-in captions, 9:16 vertical, title card, voice/length tweak.

## Refs (primary)

1. Arc Institute — Virtual Cell Challenge 2025 Wrap-Up (Dec 6, 2025)
   https://arcinstitute.org/news/virtual-cell-challenge-2025-wrap-up
2. Effects of Distance Metrics and Scaling on the PDS — arXiv:2511.16954
   https://arxiv.org/abs/2511.16954
3. PRiMeFlow (the Generalist model) — arXiv:2604.13986
   https://arxiv.org/html/2604.13986v1
4. Roohani et al., "Virtual Cell Challenge: toward a Turing test for the
   virtual cell", Cell 2025 — pmid:40578317
5. Arc Virtual Cell Atlas — https://github.com/ArcInstitute/arc-virtual-cell-atlas