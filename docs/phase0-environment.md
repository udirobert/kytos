# Kytos — Phase 0 Environment

Declared for the 2026 Virtual Cell Challenge. Install via `uv` (cell-eval's
documented distribution path). Python 3.14.5 is present here; `uv` 0.5.9 is
available.

## Core inference/env stack

| Package | Why |
|---|---|
| `anndata` | cell × gene matrices everywhere; the cell-eval I/O type |
| `scvi-tools` (`scvi`) | single-cell normalization + latent conditioning utility |
| `scanpy` | AnnData I/O, preprocessing, QC, gene-rank / NN-graph plumbing |
| `torch` | Layer A (gene-level transfer) and Layer B (cell sampler) training |
| `h5py`, `hdf5plugin` | H5AD / array read hardware for large corpora |

## Eval / harness

| Package | Why |
|---|---|
| `cell-eval` | the official scoring suite (metrics, `run`, `prep`, `score`, `ceiling`). Official docs recommend `uv pip install -U cell-eval` |
| `pdex` | DE computation cell-eval uses (referenced in `_evaluator.py`) |

## Iteration

| Package | Why |
|---|---|
| `pandas`, `numpy`, `scipy` | data plumbing |
| `torchmetrics` | array-metric checks (mse / mae / pearson) early smoke-tests |
| `polars` | DE-frame handling (cell-eval uses polars DataFrames) |
| `seaborn` + `matplotlib` | audit / run report plots |

## Not yet (Phase 2+)

`hf-deep`, `huggingface_hub`, `datasets`, *flow-matching checkpoints* — add when
committing to Layer B at scale; not part of the Phase-0 baseline that must fit
T4/16GB.

## Notes on normalization

cell-eval upstream `pdex` defaults to `is_log1p=True` for continuous input and
`False` for `allow_discrete` counts (per `_build_pdex_kwargs`). The exact
phase-0 choice of **counts vs log-normalized** submission encoding is an open
decision (Gate 3 in `docs/architecture.md`) — the first real corpus pass must
lock it against what `cell-eval prep` expects, using the `tutorials/vcc`
reference or a frozen `cell-eval run`.

## Install (first action of Phase 0)

```bash
uv pip install -U cell-eval
uv pip install -r requirements.txt   # once declared, see src release hygiene
```

Verify the harness imports cleanly with no packages present (it must degrade,
not crash, when `cell-eval` isn't installed).