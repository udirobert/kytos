# Short Pack 002 — "The Climb" (VCC 2026, our own runs)

Status: **DRAFT OUTLINE** · Owner: udingethe · Date: 2026-09-11
Series: VCC 2026 Chronicle · Lane: Dr. Kytos (anchor) — same bright anchor as specimen-002
Format: shorts-first, same clip shape as pack-001 v2 (FACT → METAPHOR → MEANING → SOURCE, ≤40 words, ~15s)

---

## Logline (the one idea)

Four submissions, three dollars of compute, one leaderboard climb:
-0.948 → -0.304 → -0.149 → -0.021. **The model didn't get smarter — the
evidence did.** Each run swapped a weaker prior for a truer one.

## Why now

Pack 001 was post-mortem — someone else's challenge. Pack 002 is ours, and
it only became writable when k006 published: the first score that means
something (-0.021, rank 534/883, pds 0.265). The run log already reads like
clip scripts; this pack transcribes it honestly, dead ends included.

## Clip pack (6 single-lesson clips)

| # | Hook (≤15 words) | Lesson | Data on screen | Src |
|---|---|---|---|---|
| 1 | "We scored dead last on purpose." | A pipeline that runs is not a model that works; the -0.948 floor proved the plumbing | k003 sparse slice, pds 0.000 | k003 facts |
| 2 | "Real cells, still invisible." | 360k real control cells bought dispersion (-0.304) but zero discrimination — every target identical | cell count + pds ~0 | k004-resample facts |
| 3 | "The first whisper." | A hand-tuned knockdown prior made pds positive for the first time (0.002) | pds crossing zero | k004-layer-a-b facts |
| 4 | "The run we never submitted." | The 2025 Atlas covers 4 of 300 targets — coverage, not priors, was the bottleneck | 4/300 coverage bar | k005 facts |
| 5 | "272 of 300." | Borrowed biology beat invented biology: Replogle K562 signatures moved to H1 hESC | trajectory + coverage bar + scorecard | k006 facts + meta |
| 6 | "What three dollars buys." | All four submissions ran on Modal Functions for ~$0.75 each — the lab bill is a coffee | cost_estimate_usd column | meta.json ×4 |

## The corridor (narrative through-line)

Each run replaced a weaker prior with a truer one:

| Run | Prior | Score | What it proved |
|---|---|---|---|
| k003 | sparse mean-shift slice | -0.948 | plumbing works; discrimination zero by construction |
| k004-resample | real control cells, shared | -0.304 | dispersion is necessary, not sufficient |
| k004-layer-a-b | hand-tuned knockdown | -0.149 | pds can be positive without learned signatures |
| k005 | 2025 Atlas | unbuilt* | built+verified, never submitted — 4/300 coverage |
| k006 | Replogle K562 GWPS | -0.021 | real signatures at 91% coverage move everything |

\* k005 is the honest dead end — built, prepped, shelved. Its clip is the
credibility beat: we publish the miss too.

## Measurement loop

Pack 001's gate was never tested (1 of 8 clips shipped). Pack 002 ships
**specimen-first**: render clip 5 alone, post it with the OG card + RSS
loop, then decide the rest on signal.

- Gate: **≥1 substantive external reply or ≥30 engagements in 2 weeks** on
  the specimen before rendering clips 1–4 + 6.
- Distribution surfaces already live: per-run OG card, tweet-intent link,
  `feed.xml`, run log. The clip lands on a page that already tells the story.

## Verification checklist (before calling the specimen grounded)

- [x] k006 scores from `meta.json` — overall -0.021, rank 534, pds 0.265,
      coverage 272/300, fallbacks 28 (verified vs `vcc status` output)
- [x] Fallback gene list — computed on Modal from Replogle obs index,
      stored in `meta.json` (28 genes, committed)
- [ ] Replogle citation — confirm the exact paper ref for the caption card
      (Replogle et al., genome-scale Perturb-seq, Cell 2022)
- [ ] Cost figures — sum `cost_estimate_usd` across k003–k006 meta.json
      for clip 6 (roughly $3; verify, don't round up)
- [ ] Leaderboard total — "534 of 883" was the count at publish time; re-check
      before locking captions

## Clip shape — inherits pack-001 v2

FACT → METAPHOR → MEANING → SOURCE, ≤40 words, glossary seed per clip.
Specimen: `scripts/specimen-003-borrowed-biology.md`.

Glossary seeds by clip: control cells → perturbation discrimination →
CRISPRi → coverage → Perturb-seq → Modal/compute-cost.

## Pipeline

`docs/chronicle/short-pack-002.md`
→ `docs/chronicle/scripts/specimen-003-*.md` (source of truth)
→ `chronicle/specimen-003-borrowed-biology/` (HyperFrames composition;
  anchor-hosted graphics — see below)
→ `docs/chronicle/media/<slug>/` (video + poster + captions.vtt)
→ `shorts.json` entry → rebuild → `/shorts/<slug>/`

Spend per clip: TTS calls only (~$0.01). Cap: <4MB video (commit cap).

### Anchor format decision (2026-09-11)

Specimen-003 v2 uses the **anchored-graphics hybrid**: the Dr. Kytos
video is a persistent layer inside the HyperFrames composition — it is
moved, shrunk to PiP, slid off for data beats, and punched back for the
landing. VO is placed as timed `<audio>` elements.

**Do NOT lip-sync future clips via Fabric.** It works (specimen-003
`assets/anchor.mp4` is proof) but costs ~$2/clip for marginal benefit —
a non-lip-synced host reading over motion graphics carries the same
information at ~1% of the cost. Preferred anchors going forward, in
order:

1. A static/looping Dr. Kytos clip (idle animation, subtle motion —
   e.g. a short Fabric/greenscreen loop reused across clips, or a
   gently animated still).
2. The specimen-002/003 Fabric output reused as b-roll where a face
   helps (it's licensed footage we already own).
3. Fabric only if a clip truly needs synced speech on camera — flag the
   cost first.
