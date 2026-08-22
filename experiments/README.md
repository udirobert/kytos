# Kytos — experiments

Run outputs live here, one folder per run ID. See
[`docs/run-protocol.md`](../docs/run-protocol.md) for the run layout, the
`meta.json` and `facts.json` schemas, and the provenance/hygiene rules.

The **Observatory** ([`docs/observatory.md`](../docs/observatory.md)) renders
each run as a visual public page from `facts.json` plus committed `visual/`
(incl. VEED Fabric `briefing.mp4`), `narrative/`, and `literature/` artifacts.

To add a new run after reading the protocol, create `experiments/<run-id>/`,
assemble `facts.json`, run enrichment tools, and commit all artifacts alongside
prediction outputs.

**Run registry:**

- `k001-mean-shift-baseline` — Observatory Milestone 0 demo (2026-08-22); probe data.
- `k002-vcc2025-validation-mean-shift` — first **real** `cell-eval` 0.8.2 run
  (2026-08-22): VCC 2025 validation (H1 hESC, 98,927 cells, 50 targets),
  mean-shift floor. DE sig-genes recall 0.0 vs ceiling 0.494; pearson_delta
  mathematically undefined (constant prediction) vs ceiling 0.667; audit clean.
  Scoring matrix subsampled (200 cells/pert + 3,000 controls, seed 0) —
  full-depth run pending k003.

```bash
# Dev A — assemble deterministic artifacts
python -m kytos.audit --run experiments/k001-mean-shift-baseline
python -m kytos.eval.facts --run experiments/k001-mean-shift-baseline
```
