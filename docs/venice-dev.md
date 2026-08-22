# Venice AI — local dev narration (privacy)

**Status:** recommended for local enrichment · **Not** a hackathon partner slot

Use [Venice](https://venice.ai) for **run narration** during development so you
do not burn hackathon OpenAI credits or send experiment payloads to OpenAI while
iterating. Venice exposes an **OpenAI-compatible chat API**; Kytos routes
`tools/render_narrative.py` through it when configured.

Hackathon / production narration still uses **OpenAI** (`NARRATION_PROVIDER=openai`
in Netlify env vars). See [`tools/README.md`](../tools/README.md) and
[`.env.example`](../.env.example).

---

## Why Venice for Kytos dev

During Milestone 0 you run enrichment often. Each narration call sends
`facts.json` fields — metrics, audit-flagged genes, hypotheses — to the LLM.
That is not secret credentials, but it **is** unreleased experiment context you
may prefer to keep off third-party training pipelines while hacking locally.

Venice is a practical default because:

1. **Privacy-first inference** — Venice states that normal API requests are
   relayed without storing or logging prompt/response content; models can run in
   **Private** (zero data retention) or stronger **TEE / E2EE** modes. See
   [Venice privacy docs](https://docs.venice.ai/overview/privacy).
2. **OpenAI-compatible** — same `openai` Python client, different
   `base_url` + key; no code fork in our tools.
3. **Preserves hackathon OpenAI budget** — Luma-linked credits stay for
   demo-quality narration, TTS, and the submission narrative.
4. **Explicit provider switch** — when `NARRATION_PROVIDER=venice`, narration
   **never** falls through to a shell `OPENAI_API_KEY` (see
   `tools/_enrich_common.py`).

Venice does **not** replace OpenAI for **TTS** (Fabric briefings) or for
**hackathon partner attribution** — those remain OpenAI + fal + Tavily.

---

## Quick setup

```bash
cp .env.example .env
```

In `.env`:

```bash
NARRATION_PROVIDER=venice

VENICE_INFERENCE_KEY=your_inference_key   # from Venice dashboard
VENICE_BASE_URL=https://api.venice.ai/api/v1
VENICE_MODEL=stealth-ox-alpha             # or another chat model from /models
```

Run enrichment (loads `.env` automatically):

```bash
./tools/run_enrichment.sh experiments/k001-mean-shift-baseline
```

Generated `narrative/report.md` includes a HTML comment noting
`provider=venice` when the LLM path succeeded.

---

## Provider selection (how Kytos decides)

| Condition | Narration backend |
|---|---|
| `NARRATION_PROVIDER=venice` | Venice only (requires `VENICE_INFERENCE_KEY`) |
| `NARRATION_PROVIDER=openai` | OpenAI (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`) |
| Unset, but `VENICE_INFERENCE_KEY` present | Venice (auto) |
| Unset, no Venice key | OpenAI |

Model env vars:

| Provider | Model env | Default |
|---|---|---|
| Venice | `VENICE_MODEL` | `stealth-ox-alpha` |
| OpenAI | `OPENAI_MODEL` | `gpt-4o-mini` |

If Venice is selected but the key is missing or the call fails, tools **degrade**
to the deterministic facts digest and exit 0 — the Observatory still builds.

---

## What still needs OpenAI (or degrades)

| Step | Dev with Venice | Notes |
|---|---|---|
| `render_narrative.py` | Venice | Chat completions only |
| `render_briefing.py` TTS | `OPENAI_TTS_API_KEY` | Direct `api.openai.com`; not Venice, not chat gateways |
| Hackathon demo narration | `NARRATION_PROVIDER=openai` | Set in Netlify for published runs |

Optional: run visuals + narrative with Venice locally, then re-run narrative
once with OpenAI before committing demo artifacts.

---

## Privacy modes (Venice platform)

Venice documents four inference privacy levels. For API dev work, **Private**
(zero retention after the request completes) is usually enough. Stronger options:

| Mode | Summary |
|---|---|
| **Anonymous** | Default proxy; content not stored on Venice servers |
| **Private** | Contract-enforced zero data retention after inference |
| **TEE** | Hardware-isolated enclave; attestation available |
| **E2EE** | Client encrypts prompt; decrypted only inside verified TEE |

List models and privacy flags:

```bash
curl -s https://api.venice.ai/api/v1/models \
  -H "Authorization: Bearer $VENICE_INFERENCE_KEY" | \
  jq '.data[] | {id, privacy: .model_spec.privacy}'
```

Pick a model whose privacy level matches your comfort. Kytos does not implement
E2EE client encryption today — standard chat completions use Venice's normal
API path.

---

## Production / Netlify

Set in **Site → Environment variables**:

```bash
NARRATION_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_TTS_API_KEY=...
TAVILY_API_KEY=...
FAL_KEY=...
```

Do **not** commit `.env`. Inference keys belong in env only
([`docs/security.md`](security.md)).

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Fallback digest, no LLM prose | Missing `VENICE_INFERENCE_KEY`, or HTTP 402 spend limit on inference key |
| Narration uses OpenAI unexpectedly | `NARRATION_PROVIDER=openai` or no Venice key; check `echo $NARRATION_PROVIDER` |
| Briefing has no audio / no mp4 | TTS needs `OPENAI_TTS_API_KEY`; Fabric needs `FAL_KEY` + hero image |
| Gateway 402 on OpenAI | `OPENAI_BASE_URL` chat proxy out of credits; use Venice for dev narration instead |

---

## Related docs

- [`.env.example`](../.env.example) — all partner env var names
- [`tools/README.md`](../tools/README.md) — enrichment pipeline + spend caps
- [`docs/run-protocol.md`](run-protocol.md) — `narrative/report.md` contract
- [`docs/security.md`](security.md) — secrets policy
