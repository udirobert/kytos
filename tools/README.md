# tools/ — development + Observatory enrichment tooling

Pre-render enrichment for the **Observatory** (Developer B track). Each tool
reads **only** the run's committed `facts.json` (see
[`docs/run-protocol.md`](../docs/run-protocol.md)) and writes artifacts back
into `experiments/<run-id>/`. None of them touch the inference path.

| Tool | Partner | Output | Spend cap (per run) |
|---|---|---|---|
| `render_narrative.py` | OpenAI (gpt-4o-mini) | `narrative/report.md` | 1 LLM call |
| `enrich_literature.py` | Tavily | `literature/<gene>.json` | ≤ 5 searches |
| `render_visuals.py` | fal (flux/dev) | `visual/hero.png`, `visual/share-card.png` | 2 image gens |
| `render_briefing.py` | OpenAI TTS + fal `veed/fabric-1.0` | `visual/briefing.mp4` (+ `briefing-audio.mp3`) | 1 TTS + 1 Fabric |

## Rules (hard)

1. **Read `facts.json` only** — never invent metrics or claims; narrative cites
   facts fields inline.
2. **Degrade empty, never block** — missing API key, missing client, or API
   failure ⇒ write fallback/no artifacts and **exit 0**. The site must build
   with zero API keys at view time.
3. **Update `facts.json` visual paths only on success** (`render_visuals.py`,
   `render_briefing.py`).
4. **Spend caps** (poker lesson): one-shot calls, no retries; budgets above.

## Usage

```bash
# after Developer A seeds experiments/<run-id>/ (facts.json present):
python tools/render_narrative.py   --run experiments/k001-mean-shift-baseline
python tools/enrich_literature.py  --run experiments/k001-mean-shift-baseline
python tools/render_visuals.py     --run experiments/k001-mean-shift-baseline
python tools/render_briefing.py    --run experiments/k001-mean-shift-baseline   # needs render_visuals first
```

Then Developer C builds the site:

```bash
python frontend/build.py --experiments experiments/ --out frontend/dist/
```

## Environment

Partner clients are imported **lazily** — the tools run with zero deps and
degrade. Copy [`.env.example`](../.env.example) → `.env` at the repo root and
fill in keys (`.env` is gitignored):

```bash
cp .env.example .env
# edit .env, then:
./tools/run_enrichment.sh
```

Or export manually — see [`.env.example`](../.env.example).

**Dev narration:** set `NARRATION_PROVIDER=venice` and `VENICE_INFERENCE_KEY` in
`.env` to avoid burning hackathon OpenAI credits locally. Venice uses an
OpenAI-compatible API (`VENICE_BASE_URL`, `VENICE_MODEL`). TTS for Fabric
briefings still requires `OPENAI_TTS_API_KEY` (direct OpenAI) or fal-only hero
without video.

**Production / hackathon:** set `NARRATION_PROVIDER=openai` and `OPENAI_API_KEY`
in Netlify env vars (never commit).

**One-shot pipeline** (audit → facts → all enrichers → facts refresh):

```bash
./tools/run_enrichment.sh experiments/k001-mean-shift-baseline
```

**Hackathon note:** If `OPENAI_BASE_URL` points at a chat-only gateway (e.g.
gitlawb), narration works there but **TTS requires `OPENAI_TTS_API_KEY`** from
the Luma OpenAI credits (direct `api.openai.com`). Top up gateway credits if
you see `insufficient_credits`.

`--run` accepts either a path or `experiments/<run-id>` relative to the repo
root.

## Notes

- `render_briefing.py` derives its spoken script from the committed
  `narrative/report.md` (or a facts.json digest), so the video's words trace to
  facts fields — LLM narration only, never independent claims.
- Fabric input payload (`image_url`, `audio_url`, `resolution`) follows the fal
  `veed/fabric-1.0` schema; verify against fal docs when you first run with a
  key.
- Test coverage lives in `tests/test_enrich.py` (degrade paths, stdlib only).
