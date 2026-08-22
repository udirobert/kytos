# Kytos — Experiment run protocol

Every experiment run gets a **run ID** and a folder. This is the provenance
habit (lemma / orbura / poker): each predicted artifact must be attributable —
config, seed, code hash, and the prediction file all hash-anchored.

The **Observatory** (`docs/observatory.md`) renders each run from `facts.json`,
assembled from the artifacts below.

## Layout

```
experiments/<run-id>/
  meta.json           # machine-readable run record (schema below)
  facts.json          # single render contract for Observatory + enrichment tools
  config.json         # resolved config actually used (post-defaults)
  codehash            # git commit / content hash of the code snapshot
  reproduce/          # ids + weights hashes + seeds needed to re-run
  metrics/            # cell-eval results.csv / agg_results.csv / ceiling csv
  audit/
    flags.json        # lemma-style biological sanity flags
  narrative/
    report.md         # LLM narration from facts + metrics (OpenAI prod; Venice dev)
  verification/
    planted_signal.json   # planted-signal self-test (tools/planted_signal.py)
    narrative_check.json  # digest grounding check (tools/check_narrative.py)
  literature/         # cached Tavily JSON per audit flag (optional)
  visual/             # fal: hero.png, share-card.png, briefing.mp4 (Fabric)
```

## `meta.json` schema

```json
{
  "run_id": "k001-mean-shift",
  "created": "2026-08-22",
  "task": "baseline|ceiling|layerA|layerB|audit",
  "inputs": {"basal_anndata": "…", "gene_list": "…", "expected_genelist": "…"},
  "code": {"commit": "…", "hash": "…"},
  "seed": 0,
  "normalization": "counts|log1p",
  "notes": "free text; not load-bearing"
}
```

## `facts.json` schema

Assembled by `src/kytos/eval/` from metrics + audit outputs. The Observatory
and all enrichment tools (`tools/render_*.py`) read and write relative to this file.

```json
{
  "run_id": "k001-mean-shift-baseline",
  "created": "2026-08-22",
  "headline": "human-readable one-liner for run cards",
  "headline_metrics": {"DESigGenesRecall": 0.0, "pearson_delta": 0.0},
  "ceiling_headroom": {"DESigGenesRecall": 0.0, "pearson_delta": 0.0},
  "audit_flags": [
    {
      "id": "unique-flag-id",
      "severity": "info|warn|error",
      "genes": ["GENE1"],
      "rule": "rule_name",
      "discuss_url": "optional GitHub Discussions URL"
    }
  ],
  "hypotheses_preregistered": ["expected effect before leaderboard peek"],
  "visual": {
    "hero": "visual/hero.png",
    "share_card": "visual/share-card.png",
    "briefing": "visual/briefing.mp4"
  },
  "provenance": {
    "commit": "git sha",
    "seed": 0,
    "code_hash": "content hash"
  }
}
```

Numeric values in `headline_metrics` and `ceiling_headroom` must match
committed CSVs in `metrics/` — never edited by hand after assembly.

## Rules (from catalog hygiene)

1. **LLM narration is generated *from* the facts JSON** (matcha), never
   independently — no claims in reports not present in the metrics files.
2. **Link every review to a `run_id`**, never to a table/session (poker — loose
   joins contaminated analysis at ~75× multiplier).
3. **Pre-register expected effect directions before peeking at the leaderboard**
   (lenitnes). Store in `facts.json` → `hypotheses_preregistered`.
4. **No per-cell-line hand-tuning** to climb a metric; that is metric-gaming.
   Hypotheses must be general across all six contexts (NOTES §4 lemma).
5. **Spend caps**: no unbounded auto-spend on partner APIs. Manually override per run.
6. **Visual assets are committed artifacts** — fal / Fabric output lives in
   `visual/`, referenced from `facts.json`; not hot-linked from ephemeral URLs.
7. **Literature enrichment degrades empty** (famile) — missing Tavily key or API
   failure must not block site build or experiment completion.
8. **Fabric briefings** use `tools/render_briefing.py` (`veed/fabric-1.0` on
   fal): source image + audio from OpenAI TTS; script must trace to `facts.json`.

## First experiment (Phase 0)

**`experiments/k001-mean-shift-baseline/`** — the go-first baseline named in
`NOTES.md §3` and `docs/architecture.md`. Predict the **mean shift from basal
state**, scaled by a context-similarity term, then evaluate with
`cell-eval run --ceiling`.

Deliverables for **k001**:
- `meta.json` with normalization + code hash + seed,
- `results.csv` / `agg_results.csv` and `ceiling_results.csv` (from `run --ceiling`),
- `facts.json` assembled from metrics + audit,
- `narrative/report.md` rendered strictly from facts (OpenAI for demo commits;
  Venice acceptable for local iteration — see [`docs/venice-dev.md`](venice-dev.md)),
- `literature/` for any audit flags (Tavily, optional),
- `visual/hero.png`, `visual/share-card.png` (fal),
- `visual/briefing.mp4` (fal VEED Fabric, optional),
- a one-line conclusion answering *how much does basal-conditioning alone buy*
  (architecture Gate → Layer A/B severity).

**Status (2026-08-22, hackathon day):** k001 is seeded — `meta.json`,
`config.json`, `codehash`, metrics + ceiling CSVs (mock), `audit/context.json`
+ `flags.json`, `facts.json`, and a deterministic fallback `narrative/report.md`
are committed. Live enrichment (OpenAI / Tavily / fal / Fabric) is **in
progress** via `tools/run_enrichment.sh`; as artifacts land they are committed
here and the Observatory redeploys.

**Contract validated (2026-08-22, live):** `cell-eval 0.8.2` is installed in
`.venv-science` (native arm64 3.12.8). The harness's obs contract was verified
against cell-eval source (`target_gene` / `non-targeting`) and fixed in
`submission/script.py`; the fixture `pred.h5ad` is now a real H5AD that passes
`cell-eval prep`. Pending: real Atlas 2025 data → genuine
`cell-eval run --ceiling` numbers replacing the mock CSVs, `literature/`,
`visual/`, `briefing.mp4`, and the one-line basal-conditioning conclusion.

The k001 run page is the **Observatory Milestone 0** demo surface (2026-08-22).
