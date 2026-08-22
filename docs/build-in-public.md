# Build-in-public — hackathon day posts

Status: **ACTIVE** · Started: **2026-08-22**

Companion to [`demo-script.md`](demo-script.md). Post as milestones land; edit
timestamps if the day slips.

**Links (keep consistent):**

- Live: https://kytosapp.netlify.app
- Repo: https://github.com/udirobert/kytos
- Run #1: https://kytosapp.netlify.app/runs/k001-mean-shift-baseline/

---

## Post 1 — Now (~12:30): idea + WIP

**Goal (hackathon day):** Get on **host + partner radar** — lead with
{Tech: Europe} × VEED, London, gratitude. VCC/problem depth comes *after*
the hackathon frame, or in follow-ups for the wider audience.

### Draft C — sponsor-first thread (**post this now**)

**1/**
```
London. {Tech: Europe} × @VEED_io Summer Lock-In — one room, >10k€ in prizes,
OpenAI + fal + Pioneer + Tavily + h in the stack.

Grateful to be building here today. Shipping in public until the 19:00 cutoff —
I'll thread updates as we land features.
```

**2/**
```
Our hackathon bet: science runs shouldn't end in a CSV.

We're building Kytos Observatory — every experiment publishes metrics, audit
flags, literature, and a **video run briefing** generated from committed facts.

Gen media as the main feature, not a logo in the README.
```

**3/**
```
The VEED moment (@VEED_io × @fal):

facts.json → OpenAI script (grounded, cites fields) → TTS → fal hero frame
→ veed/fabric-1.0 → briefing.mp4 on the run page.

Same numbers the site shows. Same flags. Turned into a run explainer you can
watch — not a slide deck about them.
```

**4/**
```
Partner stack (min. 3 ✓):

• @fal — hero stills + Fabric pipeline (core feature)
• @OpenAI — grounded narrative + TTS
• @tavilyai — literature for audit-flagged genes

Numbers by code. Prose by LLM. Video by Fabric. Never the other way around.
```

**5/**
```
Run #1 is already live (WIP): our baseline fails its own biological audit —
housekeeping genes +2.10 log2FC, mixed-direction pathway flags.

We flagged ourselves. The Observatory catches us before the leaderboard does.

https://kytosapp.netlify.app/runs/k001-mean-shift-baseline/
```

**6/**
```
Open source from hour one:

https://github.com/udirobert/kytos

Building in London today → 2-min Loom demo → submit before 19:00.

Reply here as Fabric clips + enrichment land. Feedback welcome — especially
from the VEED / fal / Tavily teams in the room.
```

**Attach to 3 or 5:** screenshot or short clip of run page / briefing loop.

**Tags:** @VEED_io (required). Add @fal, @tavilyai when posting tweets 3–4.
Optional: quote-tweet or @ {Tech: Europe} if they have a handle you use in-room.

**Discord:** drop the thread link in https://discord.gg/brSqTjJVdh when live.

---

### Draft B — problem-first thread (VCC / research audience — save for later)

**1/**
```
The Virtual Cell Challenge asks models to predict how entire cell states shift
when you knock down a single gene.

18,000 dimensions. Zero-shot across unseen cell lines. $100K on the line.
A live leaderboard for 78 days.

The scoreboard shows one number. Biology fails in thousands of ways it doesn't.
```

**2/**
```
Arc Institute ran the first challenge in 2025. The takeaway wasn't "we solved
the virtual cell."

It was: no single metric captures model quality.

Top teams rationally optimized the highest-weighted scores — PDS, DES — while
MAE stopped influencing who won. Metric gaming, not biology.

Arc added a Generalist Prize. Expanded 2026 to six aggregate metrics.
```

**3/**
```
The literature agrees the models aren't ready — even when they score well:

• Nature Methods 2025: deep perturbation models still don't consistently beat
  simple linear baselines

• Genome Biology 2025: single-cell foundation models don't reliably beat
  simpler methods; fine-tuning hides it

• ICML 2025: embedding gains collapse under distribution shift — exactly the
  2026 zero-shot setting
```

**4/**
```
Arc's 2026 brief to entrants, verbatim:

"know when a model is wrong for biological rather than numerical reasons"

But official infra gives you: leaderboard + cell-eval scores.

Not: "your housekeeping genes shifted 2 log2FC and your interferon pathway
points in opposite directions — and everyone can see it."

That gap is what we're building into.
```

**5/**
```
Kytos (κύτος) — Observatory for the Virtual Cell Challenge.

Every run we publish:
→ six-metric scores + noise-adjusted ceiling
→ deterministic biological audit flags (separate from the score)
→ literature for flagged genes
→ provenance + reproduce commands
→ VEED Fabric video briefings from committed facts

Numbers by code. Prose by LLM. Never the other way around.
```

**6/**
```
Run #1 is live. It's our own baseline.

It fails our own audit: ACTB +2.10 log2FC, mixed-direction interferon response.

We flagged ourselves on purpose. If the layer can't catch our planted failures,
it's theater.

https://kytosapp.netlify.app/runs/k001-mean-shift-baseline/
```

**7/**
```
Building this in public today at {Tech: Europe} × @VEED_io hackathon — then
every week until Nov 5.

Repo: https://github.com/udirobert/kytos

I'll reply here as enrichment + demo land. Critique the audit rules — that's
the point.
```

**Attach to 1 or 6:** run detail screenshot (confession banner + flags).

**Optional alt opener (single tweet if not threading):**
```
18,000-gene perturbation predictions. $100K prize. 78-day live leaderboard.

Arc expanded to 6 metrics because teams gamed the scoreboard in 2025.

Still no public layer that says: "your model looks good numerically but broke
biology."

Building that today — in public →
```

---

### Draft A — build log thread ( quieter reach)

**Goal:** Hook + transparency. Invite people to watch the day, not claim "done."

#### Option A — single tweet (~280 chars)

```
Building in public at {Tech: Europe} × VEED hackathon today.

Kytos (κύτος): a public Observatory for the Virtual Cell Challenge — every run
publishes scores, biological audit flags, literature, and VEED Fabric briefings.

Run #1 already fails its own audit. Live (WIP): https://kytosapp.netlify.app

Thread as we ship →
```

### Option B — thread (recommended)

**1/5**
```
Building in public at @VEED_io × {Tech: Europe} hackathon today.

Problem: virtual cell models climb leaderboards while failing biology — Arc's
2026 challenge expanded to six metrics because narrow scoring invites gaming
the metric, not the biology.

We're building the layer that catches that — in public, for 78 days.
```

**2/5**
```
Kytos (κύτος, "hollow vessel") = Observatory for the @ArcInstitute Virtual
Cell Challenge.

Every experiment run publishes:
• cell-eval metrics vs ceiling
• deterministic biological audit flags
• literature (Tavily) + grounded narrative (OpenAI)
• VEED Fabric run briefings (fal)

Numbers by code. Prose by LLM. Never the other way around.
```

**3/5**
```
Run k001 is our own baseline — and it already fails our audit:
housekeeping genes +2.10 log2FC, mixed-direction interferon response.

We flagged ourselves. That's the product.

Live (hackathon WIP): https://kytosapp.netlify.app/runs/k001-mean-shift-baseline/
```

**4/5**
```
Stack (hackathon partners): OpenAI · Tavily · fal (incl. veed/fabric-1.0)

Repo + docs: https://github.com/udirobert/kytos

Today: landing enrichment artifacts → 2-min demo → submit by 19:00.
```

**5/5**
```
Follow along today — I'll post as Fabric briefings, literature, and the Loom
land.

Critique welcome: audit rules + pre-registered hypotheses are in the repo.
This is run #1 of 78 (final submission Nov 5).
```

### Screenshot for post 1

Best frame: **run detail** with audit confession visible (two warn flags). If
vessel instrument renders well, use that. Avoid empty literature rail if you
can wait until Tavily artifacts are committed — or caption honestly: "literature
rail filling in this afternoon."

---

## Post 2 — ~15:00: enrichment landed

```
Update: k001 enrichment pipeline ran — Tavily literature for flagged genes,
OpenAI narrative from facts.json only (every sentence cites its field).

Still wiring VEED Fabric briefing (fal). Site rebuilds on every push.

https://kytosapp.netlify.app/runs/k001-mean-shift-baseline/
```

Attach: literature rail or narrative block screenshot.

---

## Post 3 — ~17:00: Fabric live (if mp4 exists)

```
VEED Fabric moment: run k001 now has a video briefing generated from committed
facts — script (OpenAI) → TTS → fal image → veed/fabric-1.0.

Science comms meets gen media. Same artifacts the site shows; not a slide deck.

[attach 10–15s clip or GIF of briefing loop]
```

Tag @VEED_io only if you're comfortable and the clip looks good.

---

## Post 4 — ~18:30: submitted

```
Submitted {Tech: Europe} × VEED hackathon.

2-min walkthrough: [Loom URL]

Built in one day, shipping for 78 more: Kytos Observatory for the Virtual Cell
Challenge. Run #1 fails its own audit — on purpose.

Repo: https://github.com/udirobert/kytos
Live: https://kytosapp.netlify.app
```

---

## Post 5 — evening (optional)

```
Hackathon day wrap: what shipped, what we'd redo, run #2 next.

[1–3 bullets: e.g. planted-signal self-test, degrade-empty enrichment, mock
metrics → real cell-eval next week]
```

---

## Tone rules

1. **Honest WIP** — "live skeleton" beats "launching today" if Fabric isn't up yet.
2. **Self-own** — k001 failing audit is the hook; lean into it.
3. **No metric inflation** — mock k001 metrics are a ceiling probe, not leaderboard claims.
4. **One CTA** — live URL or repo, not both fighting in the same sentence.
5. **Thread updates** — reply to post 1 rather than orphan tweets so the day reads as one story.
