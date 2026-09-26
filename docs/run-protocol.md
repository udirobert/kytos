# Kytos — Experiment run protocol

Status: **ACTIVE** · Updated **2026-09-20**

Every experiment run gets a **run ID** and a folder. The run record must make
three things independently auditable:

1. **Execution status** — did the code run, stop safely, get blocked, produce
   predictions, compute official scores, or get submitted?
2. **Data validity** — were the axes, units, effect representation, controls,
   panel, splits, and scorer appropriate for the question?
3. **Scientific outcome** — what was observed, what interpretation is
   supported, and what competing explanations remain?

A blocked run is not a negative model result. A completed run is not
automatically a valid test of its stated hypothesis.

The **Observatory** (`docs/observatory.md`) renders each run from `facts.json`,
assembled from the artifacts below.

## Required record for every future experiment

Before launch, record:

- **Question and hypothesis** — the exact claim under test.
- **Baseline and intervention** — what stays fixed and what changes.
- **Inputs** — datasets, contexts, targets, controls, source paths, versions.
- **Axes and units** — gene labels/order, cell splits, raw counts versus
  normalized values, and the effect representation (`additive_log1p`,
  mean-log shift, bulk-log shift, per-cell moments, pooled moments, etc.).
- **Splits** — fit/evaluation cells, held-out targets/contexts, and hashes.
- **Code and configuration hashes** — revision or content hash plus resolved
  config.
- **Scorer contract** — scorer package/revision, preset, DE backend, metric
  list, control handling, normalization, panel, and reference-anchor version.
- **Cost estimate** — expected resources and spend boundary.

After execution, record:

- **Execution status** — `completed`, `stopped_safely`, or `blocked`, plus
  boolean flags for `produced_predictions`, `computed_official_scores`, and
  `submitted`.
- **Observed result** — immutable metrics/diagnostics and artifact hashes.
- **Interpretation** — what the evidence supports.
- **Competing explanations** — implementation, data, scorer, representation,
  and sampling confounds not ruled out.
- **Decision** — what changed operationally because of this run.
- **Revisit evidence** — what specific evidence would reopen a paused
  hypothesis.
- **Actual cost** — billed amount if known; otherwise `null`/unknown. Never
  substitute an estimate for a charge.

## Layout

```
experiments/<run-id>/
  meta.json           # machine-readable run record (schema below)
  facts.json          # single render contract for Observatory + enrichment tools
  config.json         # resolved config actually used (post-defaults)
  codehash            # git commit / content hash of the code snapshot
  reproduce/          # ids + weights hashes + seeds needed to re-run
  metrics/            # scorer outputs and diagnostics
  audit/
    flags.json        # lemma-style biological sanity flags
  splits/             # cell/target/context split manifests and hashes
  narrative/
    report.md         # narration generated from facts + metrics only
  verification/
    planted_signal.json   # planted-signal self-test (tools/planted_signal.py)
    narrative_check.json  # digest grounding check (tools/check_narrative.py)
  literature/         # cached Tavily JSON per audit flag (optional)
  visual/             # fal: hero.png, share-card.png, briefing.mp4 (Fabric)
```

## `meta.json` schema

```json
{
  "run_id": "k022-pipeline-audit",
  "created": "2026-09-20",
  "task": "baseline|ceiling|signature|generator|diagnostic|audit",
  "question": "exact question under test",
  "hypothesis": "predeclared expectation",
  "baseline": "frozen comparison artifact/run",
  "intervention": "single intended change",
  "inputs": {
    "basal_anndata": "…",
    "source_effects": "…",
    "gene_list": "…",
    "expected_genelist": "…"
  },
  "axes": {
    "gene_axis": "source and cardinality",
    "target_axis": "source and cardinality",
    "context_axis": "source and cardinality",
    "missing_features": ["explicitly recorded"]
  },
  "effect_space": "additive_log1p|mean_log_shift|bulk_log_shift|moments|other",
  "normalization": "counts|log1p|other",
  "splits": {"fit": "…", "evaluation": "…", "hash": "…"},
  "code": {"commit": "…", "hash": "…"},
  "scorer": {
    "package": "cell-eval2",
    "revision": "…",
    "preset": "vcc2026",
    "de_backend": "…",
    "metrics": ["…"],
    "panel": "…",
    "anchors": "…"
  },
  "execution": {
    "status": "completed|stopped_safely|blocked",
    "produced_predictions": false,
    "computed_official_scores": false,
    "submitted": false
  },
  "cost": {"estimate_usd": 0.0, "actual_usd": null},
  "seed": 0,
  "result": "immutable observed result",
  "interpretation": "supported reading",
  "competing_explanations": ["…"],
  "decision": "operational consequence",
  "revisit_evidence": ["…"],
  "notes": "free text; not load-bearing"
}
```

Legacy `meta.json` files do not need to be rewritten just to satisfy this
schema. Add a dated interpretation note in `experiments/README.md` instead of
silently changing old artifacts.

## `facts.json` schema

Assembled by `src/kytos/eval/` from metrics + audit outputs. The Observatory
and all enrichment tools (`tools/render_*.py`) read and write relative to this
file.

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

The metric names in the example above (`DESigGenesRecall`, `pearson_delta`)
are from the legacy `cell-eval` suite; `vcc2026` runs record the six official
metric names from the scorer contract (see `docs/architecture.md` §3).

Numeric values in `headline_metrics` and `ceiling_headroom` must match
committed metric files — never edited by hand after assembly. If a metric is
proxy-only or from a legacy scorer, say so in both `facts.json` and the
registry.

## Rules (from catalog hygiene)

1. **LLM narration is generated *from* the facts JSON** (matcha), never
   independently — no claims in reports not present in the metrics files.
2. **Link every review to a `run_id`**, never to a table/session (poker — loose
   joins contaminated analysis at ~75× multiplier).
3. **Pre-register expected effect directions before peeking at the leaderboard**
   (lenitnes). Store in `facts.json` → `hypotheses_preregistered`.
4. **No per-context metric hand-tuning** to climb a metric; that is
   metric-gaming. Hypotheses must be general across the evaluation panel.
5. **Spend caps**: no unbounded auto-spend on partner APIs. Manually override
   per run, and leave unknown billing explicitly unknown.
6. **Visual assets are committed artifacts** — fal / Fabric output lives in
   `visual/`, referenced from `facts.json`; not hot-linked from ephemeral URLs.
7. **Literature enrichment degrades empty** (famile) — missing Tavily key or
   API failure must not block site build or experiment completion.
8. **Fabric briefings** use `tools/render_briefing.py` (`veed/fabric-1.0` on
   fal): source image + audio from OpenAI TTS; script must trace to
   `facts.json`.
9. **Historical artifacts are immutable** — preserve saved scores and outputs;
   correct interpretation by adding dated notes, not by editing history.
10. **No silent feature normalization** — missing genes, targets, or contexts
    are recorded or fail closed; do not strip suffixes or infer equivalence
    from spelling alone.

## Promotion rules

- A synthetic no-op parity test is not real-data parity.
- A legacy or proxy metric is not an official 2026 score.
- A three-target diagnostic is not a panel-level result.
- A count-level diagnostic is not a signature-level result unless the effect
  representation matches the generator contract.
- A submission requires the active strategy's Gate E: frozen artifact,
  comparison to k011, declared expected component changes, and approval.

## Historical note — first experiment (Phase 0)

**`experiments/k001-mean-shift-baseline/`** — the go-first baseline named in
`NOTES.md §3` and the original architecture draft. It predicted the mean shift
from basal state, scaled by a context-similarity term, then evaluated with the
legacy `cell-eval` harness.

The committed k001 run page remains the **Observatory Milestone 0** demo
surface (2026-08-22). Its mock CSVs, legacy metrics, and enrichment state are
historical artifacts, not evidence for the current 2026 scorer contract.
