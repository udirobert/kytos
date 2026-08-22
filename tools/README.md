# tools/ — development + Observatory enrichment tooling

Pre-render enrichment for the **Observatory** (Developer B track). Each tool
reads **only** the run's committed `facts.json` (see
[`docs/run-protocol.md`](../docs/run-protocol.md)) and writes artifacts back
into `experiments/<run-id>/`. None of them touch the inference path.

| Tool | Partner | Output | Spend cap (per run) |
|---|---|---|---|
| `render_narrative.py` | OpenAI (prod) or **Venice** (local dev) | `narrative/report.md` | 1 LLM call |
| `check_narrative.py` | — (deterministic, offline) | `verification/narrative_check.json` | 0 |
| `enrich_literature.py` | Tavily | `literature/<gene>.json` | ≤ 5 searches |
| `render_visuals.py` | fal (flux/dev) | `visual/hero.png`, `visual/share-card.png` | 2 image gens |
| `render_briefing.py` | OpenAI TTS + fal `veed/fabric-1.0` | `visual/briefing.mp4` (+ `briefing-audio.mp3`) | 1 TTS + 1 Fabric |
| `holo_audit.py` | **H / Holo** | `holo_screenshot.png`, `holo_audit.json` | 1 VLM call |
| `prep_vcc2025_validation.py` | — (.venv-science) | `data/raw/vcc2025/` norm-log h5ads + targets/gene axis + `prep_manifest.json`; `--purge-source` frees the 6.9GB source after a hash check | 0 |
| `build_audit_context.py` | — (.venv-science) | `audit/context.json` from prediction h5ad | 0 |

## Rules (hard)

1. **Read `facts.json` only** — never invent metrics or claims. Grounding is
   enforced by `check_narrative.py`: every number and per-gene direction claim
   in the digest must trace to facts.json (result renders as a Trust panel
   card on the run page).
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
python tools/holo_audit.py         --run experiments/k001-mean-shift-baseline   # independent UI verification
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

### Narration: Venice (dev) vs OpenAI (prod)

| Mode | When | Env |
|---|---|---|
| **Venice** | Local iteration; unreleased metrics/genes stay off OpenAI | `NARRATION_PROVIDER=venice`, `VENICE_INFERENCE_KEY` |
| **OpenAI** | Hackathon demo, Netlify builds, committed demo artifacts | `NARRATION_PROVIDER=openai`, `OPENAI_API_KEY` |

Venice uses an OpenAI-compatible chat API (`VENICE_BASE_URL`, `VENICE_MODEL`).
When `NARRATION_PROVIDER=venice`, narration **does not** use a shell
`OPENAI_API_KEY` — only Venice credentials.

**Privacy:** Venice documents zero retention for normal inference and stronger
TEE/E2EE modes on select models. See [`docs/venice-dev.md`](../docs/venice-dev.md).

**TTS for Fabric briefings** still requires `OPENAI_TTS_API_KEY` (direct
OpenAI) or skip video and ship hero stills only.

**Hackathon note:** Always use `api.openai.com` directly for both narration
and TTS — no third-party gateways. The OpenAI SDK auto-reads
`OPENAI_BASE_URL` from the environment; if set to a chat-only gateway, TTS
will 404. The code guards against this (`openai_tts_client` rejects
non-openai.com base URLs) but it's cleaner to never set `OPENAI_BASE_URL`
at all.

**One-shot pipeline** (audit → facts → all enrichers → facts refresh):

```bash
./tools/run_enrichment.sh experiments/k001-mean-shift-baseline
```

`--run` accepts either a path or `experiments/<run-id>` relative to the repo
root.

## Notes

### Holo audit (H / Holo — computer-use agent)

`holo_audit.py` is an **independent render-verification audit**: it screenshots
the built Observatory run page via Playwright, sends the screenshot to Holo's
VLM (vision-language model), asks it to read visible values (vessel fill %,
audit flag counts, run ID, headline), then diffs Holo's reading against the
committed `facts.json`. Any mismatch means the rendered page does not match
the data contract — the agent caught a render bug.

This is an AI agent that audits the auditor — our thesis is "show when a model
is biologically wrong"; Holo extends that to "show when our UI is wrong."

| Aspect | Detail |
|---|---|
| API | Holo `holo3-1-35b-a3b` (OpenAI-compatible, `https://api.hcompany.ai/v1/`) |
| Key | `HAI_API_KEY` (free tier, no credit card) |
| Deps | `openai`, `playwright` (+ `playwright install chromium`) |
| Degrade | Missing key/Playwright/API → skip, exit 0 |
| Live URL | `--url https://kytosapp.netlify.app/runs/k001-mean-shift-baseline/` |

```bash
python tools/holo_audit.py --run experiments/k001-mean-shift-baseline
# or audit the live deployed site:
python tools/holo_audit.py --run experiments/k001-mean-shift-baseline --url https://kytosapp.netlify.app/runs/k001-mean-shift-baseline/
```

### Other notes

- `render_briefing.py` derives its spoken script from the committed
  `narrative/report.md` (or a facts.json digest), so the video's words trace to
  facts fields — LLM narration only, never independent claims.
- Fabric input payload (`image_url`, `audio_url`, `resolution`) follows the fal
  `veed/fabric-1.0` schema; verify against fal docs when you first run with a
  key.
- Test coverage lives in `tests/test_enrich.py` (degrade paths, stdlib only).
