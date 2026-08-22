# Kytos (κύτος, "hollow vessel")

Predict how an **unseen cellular context** responds to CRISPRi perturbation,
from its unperturbed basal state alone. Entry for the **2026 Virtual Cell
Challenge** (Arc Institute; NVIDIA, 10x Genomics, Ultima Genomics; $100K grand
prize). Deadline **Nov 5, 2026 23:59 UTC**; test set releases **Oct 22, 2026**.

This README is the entry point. **All prose lives in [`docs/`](docs/)**.

## Docs (start here)

| Doc | What it's for |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | model-stack ADR: Layer A (gene transfer) + Layer B (cell sampler), gates, timeline |
| [`docs/code-organization.md`](docs/code-organization.md) | repo layout, backend & frontend stack, what's deferred |
| [`docs/phase0-environment.md`](docs/phase0-environment.md) | declared packages + install (`uv`) |
| [`docs/run-protocol.md`](docs/run-protocol.md) | experiment run-IDs, `meta.json`, provenance rules |
| [`docs/security.md`](docs/security.md) | secrets policy + caveats |
| [`NOTES.md`](NOTES.md) | the foundation: the task, motivation, catalog learnings |

## Layout at a glance

```
docs/            all prose (knowledge base)
src/kytos/       backend package: data, features, models, eval, audit, serve
submission/      competition harness (official inputs → cell-eval AnnData)
tools/           dev tooling (secrets scanner, etc.)
experiments/     run outputs, one folder per run-id
data/            corpora manifest/staging (raw/ gitignored)
tests/           pytest suite
frontend/        (deferred) static renderer from facts JSON
```

## Quick start

```bash
uv sync                       # install deps (or: uv pip install -r ...)
pre-commit install            # secrets + lint hooks on commit
python -m pytest              # smoke tests
python submission/script.py --basal <basal> --targets <genes> \
  --gene-order <genelist> --out pred.h5ad --meta meta.json
```

Every commit is gated by a **deterministic, offline** secrets scan + `ruff`
lint + `ruff` format (see [`docs/security.md`](docs/security.md)).

## Status (Phase 0)

- [x] Notes reviewed, stack reasoned (architecture ADR)
- [x] Submission harness contract drafted + running (degrades with no deps)
- [x] Repo organized: package-per-concern backend, consolidated `docs/`
- [ ] Install `cell-eval` + `anndata` (uv) → H5AD write path
- [ ] k001 mean-shift baseline → `cell-eval run --ceiling`

## Open decisions

See [`docs/architecture.md §7`](docs/architecture.md): Gate 1 (six-metric
aggregate), Gate 2 (Layer A formulation), Gate 3 (counts-vs-log1p encoding),
Gate 4 (public-overlap of unseen lines).