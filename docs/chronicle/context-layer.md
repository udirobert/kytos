# Context Layer — the design that carries a short

Status: **PROTOTYPED (2026-08-23)** — `/shorts/` is live in the Observatory
build (per-short page + plain-words card + glossary tooltips + source card +
deep-science `<details>`), powered by `frontend/observatory/shorts.py`,
`docs/chronicle/shorts.json` + `glossary.json`, and media under
`docs/chronicle/media/<slug>/`.

Status (pre-prototype): **DRAFT** · Product design for how non-scientist viewers understand a
10–20s Kytos short without turning it into a 2-minute explainer.
Chain: [`short-pack-001.md`](short-pack-001.md) (the clips) ·
[`glossary.md`](glossary.md) (the terms).

## 1. The problem

A viewer who isn't a scientist sees "A louder metric is not a truer one" and
has no pointer to: what a PDS is, what "2025 challenge" means, which paper
this is, or why they should trust us. We cannot stuff that into 40 spoken
words. So the **understanding lives in the product, not the clip**.

## 2. The three rungs (a short is never alone)

Every short ships with all three. A clip without rung 2 and rung 3 is not
shippable (see §6 gate).

| Rung | Piece | Where | Length |
|---|---|---|---|
| 1 | The clip | the aphorism + metaphor + source readout | ~15s, 40 words |
| 2 | **Plain-words card** | one paragraph: what it *is*, who did it, why it matters — plain English | 3–5 sentences, always open |
| 3 | The source | DOI / facts link, the full text archive, the glossary term | archive page |

## 3. Rung-2 template (concrete)

The plain-words card answers, in order:

1. **What is** the thing (in lay terms, e.g. "a score for 'can you tell gene
   A's effect apart from gene B's?'")
2. **Who / when** (the 2025 challenge, 1,200 teams, 300 knockouts…; the paper
   is by whom — **provenance / authority moment**)
3. **The twist** (the finding in one Frier-esque sentence)
4. **Why it matters now** (what the 2026 challenge changed, or what we do
   because of it)
5. **Source line** (DOI / arXiv / link, always clickable)

Glossary tooltip on a key term (limited one per card).

### Annotated specimen (trapdoor clip)

> **In plain words:** In 2025, 1,200 teams scored to predict what happens
> when you switch off one stored gene in a single human cell type. They were
> graded on a score called PDS — "can you tell switching gene A apart from
> switching gene B?" And here's the kick thesis  I think, the **3rd-place
> team's analysis** showed that PDS has a **volume knob**: a louder guess —
> even a wrong one — scored higher than a quieter correct one. The
> scoreboard was measuring confidence, not truth. That's why the 2026
> challenge is trying a different, 6-metric panel.
>
> **Term:** `PDS` = can you tell one perturbation's effect apart from
> another's?
> **Source:** arXiv:2511.16954 ([link]) — plus, who it is:
> the 3rd-place team, "Effects…"

## 4. The surfaces (where rungs render)

1. **Short page** (`/shorts/<slug>/`): video @16:9 + cardboard; r2 open by
   default; r3 below: DOI, run link, full text, prev/next pack.
2. **Broadcast / Deep Science** — reuse the existing view-mode switch on the site:
   Broadcast = r2 default; Deep Science = r3 + formulas + verbose citations.
   The shorts page is the first thing that genuinely needs both modes.
3. **Social** — fixed 3-line caption template: aphorism line · plain-words
   line · link to /shorts/<slug>/.
4. **Home "Chronicle" rail** — latest short with its r2 card, not a bare video.
5. **Glossary page / tooltip service** — same manager; hover/focus tooltip,
   click-through to the definition.

## 5. The context-completeness gate

Before a short ships:

- [ ] r1 clip: script shape (FACT→METAPHOR→MEANING→SOURCE) + ≤40 words
- [ ] r2 card: the 5-part plain paragraph exists, in-plain, no jargon leak
- [ ] glossary entry committed for the carry term(s)
- [ ] r3: at least one canonical link (DOI/arXiv) + who-wrote-it accreditation
- [ ] runs on Broadcast, runs on Deep Science

Meta: the r2 card is **authoring** content (us), not LLM; r1 stays the
single-fact spine. Reject edits that break the "no ungrounded claim" rule.

## 6. Craft notes

- The metaphor is the glue that lets the card stay short: if there isn't a
  metaphor that survives r1→r2, the clip is bad, not the soft.
- Body "science nerd labels" out of r2 entirely: no P-value jargon, no
  workflow; ALL of it lives in r3.
- Every r2 starts with the SHARED skeleton: "In 2025, [number] teams …"
  so pack-together viewers get continuity across cards.