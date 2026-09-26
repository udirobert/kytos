# specimen-004 "the edge of the map" — script

Companion to `chronicle/specimen-004-edge-of-map/BRIEF.md`.
9:16 · ~30.5s · muted-first · VO over intentional silence beats.

## VO script (four segments, ~53 words)

| seg | t | line | words |
|---|---:|---|---:|
| vo-0 | 0.3 | "This is Kytos — an open effort to predict how cells respond to genetic perturbation." | 15 |
| vo-1 | 5.4 | "Borrowed biology kept winning — until we asked which cells we were actually predicting." | 14 |
| vo-2 | 13.4 | "Three more tries. Three honest failures." | 7 |
| vo-3 | 19.4 | "The ceiling isn't the noise — it's the signature. So we stopped borrowing, and started learning." | 16 |

## Beat map

1. **0–5s — intro.** Series convention: every specimen opens with a mini
   "what is Kytos" card. Kicker: THIS IS KYTOS. Serif title: BUILDING A /
   VIRTUAL CELL. Sub: "predicting how cells respond to genetic perturbation —
   every run in the open." Anchor hero top-center. VO-0 plays.
2. **5–8.2s — recap.** Score ticker animates -0.021 → +0.0596, rank chip
   "RANK #486 / 984", trajectory line draws under the ticker.
   Bigtext: BORROWED BIOLOGY / KEPT WINNING. VO-1 plays; anchor still hero.
3. **8.2–13.2s — the twist.** Anchor shrinks to PiP. Dot field fades in lit
   on the left / dark on the right — the literal edge of the map, labelled
   "K562 TERRITORY ──── UNKNOWN". Three context cards land (A / B / C).
   Labels stamp: A ≈ JURKAT-LIKE · B ≈ RPE1-LIKE? · C = UNRESOLVED.
   Subline: "these are not the cells we borrowed for". Silence — visuals carry.
4. **13.2–19.2s — the wall.** Anchor slides off. Three hard-cut result cards,
   ~1.8s each, muted-warn accent, click SFX per cut: "paired transfer ·
   near-zero cosine" → "per-context scale · +0.031" → "matched corpora · 0/300
   targets". A progress strip (transfer / scaling / corpora) lights each
   step as it lands. VO-2 over the first cut only.
5. **19.2–30.5s — lesson → pivot (merged).** Anchor punches back to hero.
   The lesson opens the scene as a serif line — "The ceiling isn't the
   noise. It's the signature." — synced to VO-3's first half, then dims to
   ~12% as the pivot text lands on VO-3's second half: "We stopped
   borrowing. / We started learning." GPU chips (LOOKUP → MODEL ·
   NEBIUS · L40S · TRAINED PRIOR) and a node-graph that draws itself.
   End card: URL + mission tagline — "someday, a drug's first trial should
   happen in a virtual cell" — and the source line
   "(Kytos Observatory — every run, failures included)".

## Fact sources (committed)

- +0.0596 / rank 486 — experiments/k011-delta-scale-x1p7-validation
- A Jurkat-like / B RPE1-leaning / C unresolved — experiments/k012-lineage-score
- paired transfer fails LOO — experiments/k012-transfer-loo
- +0.0312 — experiments/k013-context-scale-validation
- 0/300 — experiments/k013-lineage-ratios
