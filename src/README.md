# src/ — the backend package (`kytos`)

Importable as `kytos` (src-layout, see `pyproject.toml`). Split by concern:

- `data/`     — corpus loaders + gene-space alignment
- `features/` — basal-derived context conditioning
- `models/`   — Layer A (gene-level transfer) + Layer B (cell sampler)
- `eval/`     — cell-eval wrappers, run-IDs, metric aggregation
- `audit/`    — biological sanity layer
- `serve/`    — deferred thin API (post-challenge)

See [`docs/code-organization.md`](../docs/code-organization.md) for the layout
and stack rationale.
