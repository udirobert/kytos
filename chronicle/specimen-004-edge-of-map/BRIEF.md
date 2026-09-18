# BRIEF — specimen-004 "the edge of the map"

workflow: general-video
flow: companion
mode: autonomous (intent already settled in conversation)

## Message

Borrowed biology kept winning — until we asked which cells we were
actually predicting. Three honest attempts later, the answer is in:
the lookup has a ceiling. So we stopped borrowing and started learning.

## Audience

X/Twitter feed: science-curious + AI/dev crowd first, comp-bio second.
Must work muted (captions carry) and cold (first 3s explain the game).
Sequel to specimen-003 — same design system, same honesty contract:
negative results are shown, not hidden.

## Deliverable

- ~30.5s motion-graphics clip, narration over silence beats
- Aspect: 9:16 primary (1080×1920)
- Output: MP4 for docs/chronicle/media/specimen-004-edge-of-map/

## Structure (locked in docs/chronicle/scripts/specimen-004-edge-of-map.md)

0. 0–5s   Intro (series convention): "THIS IS KYTOS / BUILDING A
          VIRTUAL CELL" — what Kytos is, what we're trying to do.
          Anchor hero.
1. 5–8.2s Recap hook: score ticker climbs -0.021 → +0.0596, rank 486.
          "BORROWED BIOLOGY KEPT WINNING". Anchor still hero.
2. 8.2–13.2s  The twist: edge-of-map dot field + three context cards
          land — A≈JURKAT (0.65), B≈RPE1 (0.37), C=? — "these are not
          the cells we borrowed for". Anchor PiP.
3. 13.2–19.2s The wall: three fast-cut negative results — transfer
          cosine 0.13 · per-context scale +0.031 · "0/300 panel
          targets" — progress strip + click SFX per cut.
4. 19.2–30.5s Lesson → pivot (merged): the aphorism opens the scene
          synced to VO-3, dims as "we stopped borrowing / we started
          learning" lands. GPU chips + node-graph. Anchor hero again.
          End card: URL + mission tagline "someday, a drug's first
          trial should happen in a virtual cell".

## Design system (matches kytosapp.netlify.app + specimen-003)

- BG #0a0a0f · panel #12121a · line #262634
- Ink #ebebf2 · muted #8c8c9e · accent #2dd4bf · warn #f59e0b
- Inter for display type, IBM Plex Mono for numbers/labels,
  Instrument Serif for aphorisms
- Flat, technical, honest — no glow spam, no particle soup
- Anchor host layer reused from specimen-003 (muted loop, no new
  lip-sync generation — recorded preference: lip-sync is expensive for
  low value)

## Facts (all committed in repo)

- +0.0596 overall, rank 486 — k011-delta-scale-x1p7 champion
- x2.0 +0.0566 rank 515 — scale curve bent, optimum ~1.7
- Lineage: A Jurkat-like 0.649 / B RPE1 0.369 / C hESC 0.379 unresolved
  — k012-lineage-score (top-2000 discriminative genes)
- Paired transfer LOO cosine 0.126 — k012-transfer-loo (negative)
- Per-context scale +0.0312 rank 560 — k013-context-scale (negative)
- 0/300 panel targets in essential screens (RPE1/Jurkat) — k013-lineage-ratios
- Figshare GWPS is K562-only — no public corpus covers the panel in a
  matched lineage
- Track 2: Nebius GPU, conditional-MLP baseline first — docs/track2-nebius-setup.md

## Audio

- VO: OpenAI TTS `tts-1` voice `shimmer` (series voice) — four segments
  on their beats (~53 words total)
- One click SFX per wall cut (13.2 / 15.2 / 17.2)
- Silence beats under the negative-results montage are intentional
- No music bed for the specimen (keep the confession tone)

## Out of scope

- No new anchor footage / lip-sync generation — reuse specimen-003's
  muted loop or ship motion-graphics only
- No claims beyond committed metadata
