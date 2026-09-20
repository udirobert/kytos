# Kytos — submission harness

Status: **UPDATED 2026-09-20** — the output contract below remains the target,
but references to `cell-eval 0.8.2` are legacy compatibility notes. The
identified official 2026 scorer is `cell-eval2`/`vcc2026`; it is not yet
installed or proven equivalent to production scoring.

The load-bearing "harness first" layer (`NOTES §4 ratiocine`). This is the one
thing that must be bulletproof before the deadline: it reads the official
inputs and writes a scorer-compatible prediction.

## Contract

`script.py` reads:

- `--basal` — basal-state expression of cells expressing non-targeting guides
- `--targets` — CRISPRi knockdown gene identifiers (one per line)
- `--gene-order` — canonical gene axis (`expected_genelist`, one per line)

and writes an AnnData (H5AD) with X `[n_cells, n_genes]`, an obs column
`target_gene` (a `non-targeting` row set + one per target gene), and gene
identity on the var axis — the scorer-facing shape compared against
`adata_real`. The column + control names are **verified against legacy
`cell-eval 0.8.2` defaults** (`cell_eval/_cli/_const.py`), so the legacy
`cell-eval run -ap pred.h5ad -ar real.h5ad` path works with zero flags. That
legacy compatibility is not official 2026 scorer equivalence; re-check the
`cell-eval2` contract before treating offline scores as production-relevant.
Override with `--pert-col` / `--control-pert` if the challenge schema differs.

**Graceful degradation:** with `anndata`/eval dependencies not yet installed,
the harness writes a JSON placeholder (same gene-order contract) so the pipeline
stays testable offline. A smoke-test run is in `fixtures/out/`.

## Legacy local eval loop (Phase 0 / every submission)

```bash
# once legacy cell-eval 0.8.2 + anndata are installed (uv):
cell-eval run -ap fixtures/out/pred.h5ad -ar <real>.h5ad \
  --num-threads 64 --profile full

# ceiling (noise-adjusted per-metric upper bounds) on the baseline:
cell-eval run -ap fixtures/out/pred.h5ad -ar <real>.h5ad --ceiling
```

These legacy checks are useful for schema and harness bugs, but they are not
official 2026 scores. Test against a **frozen** scorer environment before ever
touching the live leaderboard, and re-validate every assumption when validation
data is re-released (`poker` format-change lesson).

## Rules

1. No LLM in the prediction path — the numbers come from code, not prose.
2. Keep the metadata contract unchanged until Gate 3 (official gene-list /
   normalization confirmed).
3. Run IDs + `meta.json` + code hash on every artifact (see
   `experiments/README.md`).
4. No per-cell-line hand-tuning — generalize across all three held-out contexts.