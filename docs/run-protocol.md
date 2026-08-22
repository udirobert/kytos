# Kytos — Experiment run protocol

Every experiment run gets a **run ID** and a folder. This is the provenance
habit (lemma / orbura / poker): each predicted artifact must be attributable —
config, seed, code hash, and the prediction file all hash-anchored.

## Layout

```
experiments/<run-id>/
  meta.json        # machine-readable run record (schema below)
  config.json      # resolved config actually used (post-defaults)
  codehash         # git commit / content hash of the code snapshot
  reproduce/       # any ids + weights hashes + seeds needed to re-run
  metrics/         # cell-eval results.csv / agg_results.csv / ceiling csv
  report.md        # LLM-narration ONLY, rendered from facts in metrics/
```

## `meta.json` schema

```json
{
  "run_id": "k001-mean-shift",
  "created": "2026-08-21",
  "task": "baseline|ceiling|layerA|layerB|audit",
  "inputs": {"basal_anndata": "…", "gene_list": "…", "expected_genelist": "…"},
  "code": {"commit": "…", "hash": "…"},
  "seed": 0,
  "normalization": "counts|log1p",
  "notes": "free text; not load-bearing"
}
```

## Rules (from catalog hygiene)

1. **LLM narration is generated *from* the facts JSON** (matcha), never
   independently — no verbosed claims in reports not present in the metrics
   files.
2. **Link every review to a `run_id`**, never to a table/session (poker — loose
   joins contaminated analysis at ~75× multiplier).
3. **Pre-register expected effect directions before peeking at the leaderboard**
   (lenitnes). A run whose audit checks are open can never be claimed.
4. **No per-cell-line hand-tuning** to climb a metric; that is metric-gaming.
   Hypotheses must be general across all six contexts (NOTES §4 lemma).
5. **Spend caps**: no unbounded auto-spend. Manually override per run.

## First experiment (Phase 0)

**`experiments/k001-mean-shift-baseline/`** — the go-first baseline named in
`NOTES.md §3.1` and `docs/architecture.md`. Predict the **mean shift from
basal state**, scaled by a context-similarity term, then evaluate with
`cell-eval run --ceiling`.

Deliverables for **k001**:
- `meta.json` with normalization + code hash + seed,
- `results.csv` / `agg_results.csv` and `ceiling_results.csv` (from `run --ceiling`),
- prose (`.md` report) rendered strictly from those CSVs,
- a one-line conclusion answering *how much does basal-conditioning alone buy*
  (architecture Gate → Layer A/B severity).