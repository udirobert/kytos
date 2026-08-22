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
degrade. To enable the API paths:

```bash
uv sync --extra obs     # installs openai, tavily-python, fal-client
export OPENAI_API_KEY=...   # narrative + briefing TTS
export TAVILY_API_KEY=...   # literature
export FAL_KEY=...          # visuals + briefing (FABRIC)
```

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
