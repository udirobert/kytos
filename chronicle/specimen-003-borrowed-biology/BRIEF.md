# BRIEF — specimen-003 "borrowed biology"

workflow: general-video
flow: companion
mode: autonomous (intent already settled in conversation)

## Message

Turn off one gene in a human cell — now predict the other 18,000. Kytos
borrowed a catalog of real knockdowns from one cell type and tested it on
one it had never seen. Borrowed biology beat invented biology.

## Audience

X/Twitter feed: science-curious + AI/dev crowd first, comp-bio second.
Must work muted (captions carry) and cold (first 3s explain the game).

## Deliverable

- ~22s motion-graphics clip, narration over silence beats
- Aspect: 9:16 primary (1080×1920); 16:9 variant later once look locks
- Output: MP4 for docs/chronicle/media/specimen-003-borrowed-biology/

## Structure (locked in docs/chronicle/scripts/specimen-003-borrowed-biology.md)

1. 0–3s   Cold open: one gene dims. "TURN OFF ONE GENE"
2. 3–6s   Scale flip: dot field floods. "PREDICT THE OTHER 18,000"
3. 6–9s   Context cut: "1,200+ teams tried" leaderboard flash (silence)
4. 9–15s  The transfer: coverage bar sweeps to 272/300, K562 → H1 hESC
5. 15–19s Payoff: score ticker -0.948 → -0.021, trajectory draws, rank 534
6. 19–22s Aphorism lands + end card (Source: Replogle Perturb-seq + site URL)

## Design system (matches kytosapp.netlify.app)

- BG #0a0a0f · panel #12121a · line #262634
- Ink #ebebf2 · muted #8c8c9e · accent #2dd4bf · warn #f59e0b
- Inter for display type, IBM Plex Mono for numbers/labels
- Flat, technical, honest — no glow spam, no particle soup

## Facts (all committed in repo)

- 272/300 targets real signatures, 28 fallback — k006 meta.json
- Scores: -0.948 (k003) → -0.304 → -0.149 → -0.021 (k006), rank 534/883
- 18,533 genes, 360,000 cells — k006 meta.json input

## Audio

- VO: TTS tts-1/shimmer on the 40-word script (added at assembly)
- Two silence beats (6–9s, 15–19s) are intentional — visuals carry
- No music bed for the specimen (keep the confession tone; evaluate after)

## Out of scope

- No talking head (Fabric) in v2 — motion graphics carry; anchor overlay
  is an optional later experiment
- No claims beyond committed metadata
