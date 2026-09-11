<!-- SPECIMEN 3 v2 — one concept: "borrowed biology beats invented biology".
Two-track format: VO (spoken, ~40 words, ~160wpm) + SHOT (visual track).
Structure: COLD OPEN (context for everyone) -> PAYOFF (our result) -> SOURCE.
Glossary seed: CRISPRi — turning a gene's volume down without cutting the gene.
Pack: short-pack-002 · Clip 5 · 2026-09-11 · ~22s.
Renders 9:16 (X feed) + 16:9 (site/YouTube embed). -->

# k006 — KYTOS NEWSROOM (SHORT: borrowed biology)

## VO script (verbatim — 40 words)

Turn off one gene in a human cell — now predict the other eighteen
thousand. We borrowed a catalog of real knockdowns from one cell type, and
tested it on one it had never seen. Borrowed biology beat invented biology.

## Shot list

| t (s) | VO beat | Visual | Notes |
|---|---|---|---|
| 0.0–3.0 | "Turn off one gene in a human cell —" | Black frame → a single gene glyph dims out on a dark field; big text: **TURN OFF ONE GENE** | Muted-autoplay legible; text does the work |
| 3.0–6.0 | "now predict the other eighteen thousand." | The field floods with a dense grid of gene dots; text: **PREDICT THE OTHER 18,000** | Scale contrast: 1 dot → 18k dots |
| 6.0–9.0 | — (beat of silence) | Leaderboard scroll / "1,200+ teams tried" flashes | Context cut — why this is hard |
| 9.0–15.0 | "We borrowed a catalog of real knockdowns from one cell type, and tested it on one it had never seen." | Coverage bar sweeps to 272/300; labels K562 → H1 hESC with an arrow | The transfer, visualized literally |
| 15.0–19.0 | — (beat) | Score ticker animates **-0.948 → -0.021**; trajectory line draws underneath | The payoff — numbers in motion |
| 19.0–22.0 | "Borrowed biology beat invented biology." | Aphorism lands full-frame; then end card: **(Source: Replogle et al., genome-scale Perturb-seq, Cell 2022)** + `kytosapp.netlify.app` | Source spoken aloud once + on card |

## Audio notes

- VO: OpenAI TTS `tts-1` voice `shimmer` (pack convention; correspondent-grade).
- Two deliberate silence beats (6–9s, 15–19s) let the visuals carry — the clip
  must work muted.
- Optional: Dr. Kytos anchor as a small corner overlay on the payoff beat for
  continuity with pack-001. Skip if it fights the ticker.

## Facts used (all committed)

- 272/300 targets covered by Replogle signatures — `experiments/k006-replogle-prior-validation/meta.json`
- Score -0.948 → -0.021 — `facts.json` headline_metrics, k003 → k006
- 18,533 genes — `meta.json` input.n_genes (say "eighteen thousand", not the exact count)
- Rank 534/883 — on the end card if it survives to publish; re-verify before lock
