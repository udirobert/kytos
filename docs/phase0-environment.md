# Kytos — Phase 0 Environment

Declared for the 2026 Virtual Cell Challenge. Install via `uv` (cell-eval's
documented distribution path). Python 3.14.5 is present here; `uv` 0.5.9 is
available.

**Platform note (2026-08-22):** `torch` (pulled by `scvi-tools`/`scanpy`) has
**no Python 3.14 wheel** for this platform — a full `uv sync` currently fails
(`torch==2.13.0` resolution error). The **heavy stack is pinned to Python
3.12** once the science track starts. The Observatory `.venv` (Python 3.12)
already works with just the partner clients (`openai`, `tavily-python`,
`fal-client`) — see [`tools/README.md`](../tools/README.md).

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
# Observatory enrichment venv (Python 3.12 — 3.14 has no torch wheel):
uv venv --python 3.12 .venv
uv pip install openai tavily-python fal-client

# Science track (when cell-eval work starts):
uv pip install -U cell-eval   # in a Python 3.12 env; anndata comes with it
uv pip install -r requirements.txt   # once declared, see src release hygiene
```

## Science venv (2026-08-22, live)

**`.venv-science`** — native **arm64** Python 3.12.8 (downloaded via
`uv python install 3.12`), with `cell-eval 0.8.2` + `anndata` + `scanpy` +
`numba`/`llvmlite` installed and verified. This is the science-track env.

**Gotcha that cost a cycle:** the machine is arm64, but the locally installed
Homebrew Python 3.12 is **x86_64 (Rosetta)** — so `cell-eval`'s `llvmlite`
(numba) dependency had no wheel and failed to build from source (same class as
the earlier tiktoken/torch wheel issues). The native arm64 3.12.8 fixes all of
them. Keep the science stack on `.venv-science`, not the Rosetta `.venv`.

```bash
uv python install 3.12            # native arm64 CPython
uv venv --python 3.12.8 .venv-science
uv pip install --python .venv-science/bin/python -U cell-eval
uv pip install --python .venv-science/bin/python pytest
```

Verify the harness imports cleanly with no packages present (it must degrade,
not crash, when `cell-eval` isn't installed).

## Observatory enrichment (partner clients)

The `.venv` for enrichment tools needs only lightweight API clients — not the
full torch stack:

```bash
uv pip install openai tavily-python fal-client
```

**Local narration:** prefer [Venice AI](https://venice.ai) for chat completions
during development — private inference, OpenAI-compatible API, keeps hackathon
OpenAI credits for demo runs and TTS. Copy `.env.example` → `.env`, set
`NARRATION_PROVIDER=venice` and `VENICE_INFERENCE_KEY`. Full setup:
[`docs/venice-dev.md`](venice-dev.md).

**Production / Netlify:** `NARRATION_PROVIDER=openai` plus hackathon keys for
Tavily, fal, and `OPENAI_TTS_API_KEY` (Fabric briefings).