# Kytos — submission harness

The load-bearing "harness first" layer (`NOTES §4 ratiocine`). This is the one
thing that must be bulletproof before the deadline: it reads the official
inputs and writes a cell-eval-ready prediction.

## Contract

`script.py` reads:

- `--basal` — basal-state expression of cells expressing non-targeting guides
- `--targets` — CRISPRi knockdown gene identifiers (one per line)
- `--gene-order` — canonical gene axis (`expected_genelist`, one per line)

and writes an AnnData (H5AD) with X `[n_cells, n_genes]`, an obs column
`target_gene` (a `non-targeting` row set + one per target gene), and gene
identity on the var axis — the shape `cell-eval` compares against
`adata_real`. The column + control names are **verified against cell-eval
0.8.2's defaults** (`cell_eval/_cli/_const.py`), so
`cell-eval run -ap pred.h5ad -ar real.h5ad` works with zero flags. Override
with `--pert-col` / `--control-pert` if the challenge schema differs.

**Graceful degradation:** with `anndata`/`cell-eval` not yet installed, the
harness writes a JSON placeholder (same gene-order contract) so the pipeline
stays testable offline. A smoke-test run is in `fixtures/out/`.

## Local eval loop (Phase 0 / every submission)

```bash
# once cell-eval + anndata are installed (uv):
cell-eval run -ap fixtures/out/pred.h5ad -ar <real>.h5ad \
  --num-threads 64 --profile full

# ceiling (noise-adjusted per-metric upper bounds) on the baseline:
cell-eval run -ap fixtures/out/pred.h5ad -ar <real>.h5ad --ceiling
```

Test against a **frozen** local `cell-eval run` before ever touching the live
leaderboard. Re-validate every assumption when validation data is re-released
(`poker` format-change lesson).

## Rules

1. No LLM in the prediction path — the numbers come from code, not prose.
2. Keep the metadata contract unchanged until Gate 3 (official gene-list /
   normalization confirmed).
3. Run IDs + `meta.json` + code hash on every artifact (see
   `experiments/README.md`).
4. No per-cell-line hand-tuning — generalize across all six contexts.